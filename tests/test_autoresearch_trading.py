"""Tests for the pure functions in bonito.research.autoresearch_trading.

Covers split_data, validate_no_lookahead, and apply_kill_filters — the three
pure (non-LLM, non-I/O) functions in the autoresearch loop. The LLM mutation
call, the main `run()` loop, and file I/O (load_seed_strategy/save_best/etc.)
are out of scope: they require mocking the Anthropic client and DuckDB store,
which is a different testing concern than the pure data/validation logic here.
"""

import math
from datetime import datetime, timedelta

import pytest

from bonito.backtest.models import BacktestResult, OrderSide, PerformanceMetrics, Trade
from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    IndicatorType,
    Rule,
    RuleCondition,
    StrategyConfig,
)
from bonito.data.models import BarData
from bonito.research.autoresearch_trading import (
    MAX_INDICATORS,
    apply_kill_filters,
    split_data,
    validate_no_lookahead,
)
from bonito.trading.validation import MAX_DRAWDOWN, MAX_SHARPE, MIN_TRADES_PER_YEAR


def make_bar_data(n: int = 30, start: datetime = datetime(2023, 1, 1)) -> BarData:
    """n consecutive daily bars starting at `start`, monotonically rising close."""
    dates = [start + timedelta(days=i) for i in range(n)]
    closes = [100.0 + i for i in range(n)]
    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=dates,
        opens=closes,
        highs=[c + 1 for c in closes],
        lows=[c - 1 for c in closes],
        closes=closes,
        volumes=[1000.0] * n,
    )


def make_strategy(
    indicators: list[IndicatorConfig] | None = None,
    conditions: list[RuleCondition] | None = None,
) -> StrategyConfig:
    indicators = indicators if indicators is not None else []
    conditions = conditions or [RuleCondition(left="close", comparison=Comparison.GT, right=100)]
    return StrategyConfig(
        name="test",
        symbols=["TEST"],
        indicators=indicators,
        entry_rules=[Rule(conditions=conditions)],
    )


def make_metrics(total_trades: int = 10) -> PerformanceMetrics:
    """Stub PerformanceMetrics — apply_kill_filters/window_metrics() recompute
    trades/sharpe/drawdown from result.trades/equity_curve directly, so the
    values on this object itself are never read by the functions under test."""
    return PerformanceMetrics(
        total_return=0.1,
        annualized_return=0.1,
        sharpe_ratio=1.0,
        sortino_ratio=1.0,
        max_drawdown=0.05,
        max_drawdown_duration_days=5,
        total_trades=total_trades,
        winning_trades=max(total_trades - 1, 0),
        losing_trades=min(total_trades, 1),
        win_rate=0.6,
        profit_factor=1.5,
        average_win=0.02,
        average_loss=-0.01,
        largest_win=0.05,
        largest_loss=-0.03,
        avg_exposure=0.5,
        calmar_ratio=2.0,
    )


def make_trades(dates: list[datetime], count: int) -> list[Trade]:
    """`count` short round-trip trades spaced 3 days apart, all winners."""
    trades = []
    for i in range(count):
        entry = dates[5 + i * 3]
        exit_ = dates[6 + i * 3]
        trades.append(
            Trade(
                symbol="AAPL",
                side=OrderSide.BUY,
                entry_time=entry,
                entry_price=100.0,
                exit_time=exit_,
                exit_price=101.0,
                quantity=10.0,
                pnl=10.0,
                pnl_percent=0.01,
            )
        )
    return trades


def make_result(
    equity_curve: list[float], dates: list[datetime], trades: list[Trade]
) -> BacktestResult:
    n = len(dates)
    return BacktestResult(
        strategy_name="test",
        symbol="AAPL",
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=equity_curve[0],
        final_capital=equity_curve[-1],
        metrics=make_metrics(len(trades)),
        trades=trades,
        equity_curve=equity_curve,
        equity_dates=dates,
        drawdown_curve=[0.0] * n,
        total_commission=0.0,
        total_slippage=0.0,
    )


def min_trades_for(dates: list[datetime]) -> int:
    """Minimum trade count window_metrics/kill_verdict requires to pass,
    for a window spanning `dates[0]` to `dates[-1]`."""
    years = (dates[-1] - dates[0]).days / 365.25
    return math.ceil(MIN_TRADES_PER_YEAR * years)


class TestSplitData:
    """split_data is date-based (not index-count-based): boundaries are
    inclusive on the END of each side — train is [start, train_end], val is
    (train_end, val_end] — so the two splits never overlap a single bar."""

    def test_produces_non_overlapping_train_and_val_sets(self):
        data = make_bar_data(n=30)
        train, val = split_data(data, train_end="2023-01-15", val_end="2023-01-25")

        assert len(train) == 15
        assert len(val) == 10
        assert train.timestamps[-1] < val.timestamps[0]

    def test_boundary_date_belongs_to_train_not_val(self):
        """The train_end date itself is included in train, excluded from val."""
        data = make_bar_data(n=30)
        train, val = split_data(data, train_end="2023-01-15", val_end="2023-01-25")

        assert train.timestamps[-1] == datetime(2023, 1, 15)
        assert val.timestamps[0] == datetime(2023, 1, 16)

    def test_val_end_date_is_included_in_val(self):
        data = make_bar_data(n=30)
        _, val = split_data(data, train_end="2023-01-15", val_end="2023-01-25")
        assert val.timestamps[-1] == datetime(2023, 1, 25)

    def test_dates_beyond_val_end_are_excluded_entirely(self):
        """Holdout (anything after val_end) is excluded from both splits."""
        data = make_bar_data(n=30)
        train, val = split_data(data, train_end="2023-01-15", val_end="2023-01-25")
        total_used = len(train) + len(val)
        assert total_used < len(data)

    def test_no_training_data_raises_value_error(self):
        data = make_bar_data(n=30)
        with pytest.raises(ValueError, match="No training data"):
            split_data(data, train_end="2020-01-01", val_end="2023-01-25")

    def test_no_validation_data_raises_value_error(self):
        data = make_bar_data(n=30)
        with pytest.raises(ValueError, match="No validation data"):
            split_data(data, train_end="2023-01-15", val_end="2023-01-15")


class TestValidateNoLookahead:
    """Returns None for a clean strategy, an error string for the first
    violation found (indicator period/length, then rule condition lookback)."""

    def test_clean_strategy_returns_none(self):
        strategy = make_strategy(
            indicators=[
                IndicatorConfig(type=IndicatorType.SMA, name="sma_10", params={"period": 10})
            ],
            conditions=[RuleCondition(left="close", comparison=Comparison.GT, right="sma_10")],
        )
        assert validate_no_lookahead(strategy, data_length=100) is None

    def test_indicator_period_exceeding_data_length_is_rejected(self):
        """Genuine look-ahead: an SMA(200) cannot be computed on 50 bars of history
        without looking past what's actually available — this is the real check
        at autoresearch_trading.py's `period > data_length` line."""
        strategy = make_strategy(
            indicators=[
                IndicatorConfig(type=IndicatorType.SMA, name="sma_200", params={"period": 200})
            ],
        )
        result = validate_no_lookahead(strategy, data_length=50)
        assert result is not None
        assert "sma_200" in result
        assert "200" in result
        assert "50" in result

    def test_indicator_length_param_exceeding_data_length_is_rejected(self):
        """Some indicators (e.g. pandas-ta) use the `length` key instead of `period`."""
        strategy = make_strategy(
            indicators=[IndicatorConfig(type="adx", name="adx_long", params={"length": 100})],
        )
        result = validate_no_lookahead(strategy, data_length=50)
        assert result is not None
        assert "adx_long" in result

    def test_rule_condition_lookback_exceeding_data_length_is_rejected(self):
        """Real violation of the *second* check: a was_above condition whose
        lookback window reaches further back than the available data."""
        strategy = make_strategy(
            conditions=[
                RuleCondition(left="close", comparison=Comparison.WAS_ABOVE, right=100, lookback=60)
            ],
        )
        result = validate_no_lookahead(strategy, data_length=50)
        assert result is not None
        assert "60" in result
        assert "50" in result

    def test_exit_rule_lookback_is_also_checked(self):
        """Exit rules go through the same loop as entry rules (entry_rules + exit_rules)."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=100)])
            ],
            exit_rules=[
                Rule(
                    conditions=[
                        RuleCondition(
                            left="close", comparison=Comparison.WAS_BELOW, right=100, lookback=60
                        )
                    ]
                )
            ],
        )
        result = validate_no_lookahead(strategy, data_length=50)
        assert result is not None
        assert "60" in result

    def test_indicator_with_no_period_or_length_does_not_false_positive(self):
        """params without 'period'/'length' default to 0, which never exceeds
        data_length — confirms the `or 0` fallback doesn't spuriously reject."""
        strategy = make_strategy(
            indicators=[IndicatorConfig(type="vwap", name="vwap", params={})],
        )
        assert validate_no_lookahead(strategy, data_length=50) is None


class TestApplyKillFilters:
    """Each sub-test isolates exactly one of apply_kill_filters' real
    criteria: too-many-indicators (local, MAX_INDICATORS=3), then the three
    delegated to validation.kill_verdict() — min trades/year, max drawdown,
    Sharpe ceiling. A clean case must pass all of them simultaneously."""

    def test_passing_strategy_returns_none(self):
        dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(252)]
        # Realistic noisy-but-positive equity curve: moderate Sharpe, moderate drawdown.
        import numpy as np

        rng = np.random.default_rng(42)
        daily_returns = rng.normal(0.0008, 0.01, len(dates) - 1)
        equity = [100_000.0]
        for r in daily_returns:
            equity.append(equity[-1] * (1 + r))

        trades = make_trades(dates, min_trades_for(dates) + 2)
        result = make_result(equity, dates, trades)
        strategy = make_strategy(
            indicators=[
                IndicatorConfig(type=IndicatorType.SMA, name="sma_10", params={"period": 10})
            ]
        )

        assert apply_kill_filters(result, strategy, dates[0], dates[-1]) is None

    def test_too_many_indicators_is_killed_before_running_metrics(self):
        """MAX_INDICATORS=3 — a 4th indicator fails immediately, independent
        of the backtest result's trades/drawdown/Sharpe."""
        dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(252)]
        equity = [100_000.0 + i for i in range(len(dates))]
        trades = make_trades(dates, min_trades_for(dates) + 2)
        result = make_result(equity, dates, trades)

        too_many = [
            IndicatorConfig(type=IndicatorType.SMA, name=f"sma_{p}", params={"period": p})
            for p in (5, 10, 15, 20)
        ]
        assert len(too_many) > MAX_INDICATORS
        strategy = make_strategy(indicators=too_many)

        reason = apply_kill_filters(result, strategy, dates[0], dates[-1])
        assert reason is not None
        assert "too_many_indicators" in reason

    def test_too_few_trades_per_year_is_killed(self):
        """Below MIN_TRADES_PER_YEAR (rate-based, via kill_verdict)."""
        dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(252)]
        equity = [100_000.0 + i for i in range(len(dates))]
        required = min_trades_for(dates)
        assert required > 1, "test assumption: a 1-year window requires >1 trade"
        trades = make_trades(dates, 1)  # well under the per-year minimum
        result = make_result(equity, dates, trades)
        strategy = make_strategy()

        reason = apply_kill_filters(result, strategy, dates[0], dates[-1])
        assert reason is not None
        assert "trades" in reason

    def test_excessive_drawdown_is_killed(self):
        """Above MAX_DRAWDOWN (0.25) via kill_verdict — a sharp 30% drop."""
        dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(252)]
        equity = [100_000.0] * 100 + [70_000.0 + i * 50 for i in range(len(dates) - 100)]
        trades = make_trades(dates, min_trades_for(dates) + 2)
        result = make_result(equity, dates, trades)
        strategy = make_strategy()

        reason = apply_kill_filters(result, strategy, dates[0], dates[-1])
        assert reason is not None
        assert "DD" in reason

        # Confirm the drawdown actually exceeds the threshold this test claims to exercise.
        peak = max(equity)
        trough = min(equity[100:])
        assert (peak - trough) / peak > MAX_DRAWDOWN

    def test_sharpe_above_ceiling_is_killed(self):
        """Above MAX_SHARPE (3.0) via kill_verdict — an unrealistically smooth,
        monotonic equity curve (the overfitting signature)."""
        dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(252)]
        equity = [100_000.0 * (1.0008**i) for i in range(len(dates))]
        trades = make_trades(dates, min_trades_for(dates) + 2)
        result = make_result(equity, dates, trades)
        strategy = make_strategy()

        reason = apply_kill_filters(result, strategy, dates[0], dates[-1])
        assert reason is not None
        assert "Sharpe" in reason
        assert f">{MAX_SHARPE:.1f}" in reason
