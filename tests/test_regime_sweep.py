"""Tests for cross-regime robustness reporting (bonito.research.regime_sweep)."""

import math
from datetime import datetime, timedelta

from bonito.backtest.models import BacktestResult, OrderSide, PerformanceMetrics, Trade
from bonito.data.models import BarData
from bonito.research.regime_sweep import (
    LOW_SAMPLE_TRADES,
    Regime,
    cagr,
    full_history_regime,
    regime_report,
)

START = datetime(2020, 1, 1)


def make_result(equity: list[float], trades: list[Trade] | None = None) -> BacktestResult:
    dates = [START + timedelta(days=i) for i in range(len(equity))]
    zero_metrics = PerformanceMetrics(
        total_return=0,
        annualized_return=0,
        sharpe_ratio=0,
        sortino_ratio=0,
        max_drawdown=0,
        max_drawdown_duration_days=0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0,
        profit_factor=0,
        average_win=0,
        average_loss=0,
        largest_win=0,
        largest_loss=0,
        avg_exposure=0,
        calmar_ratio=0,
    )
    return BacktestResult(
        strategy_name="test",
        symbol="TEST",
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=equity[0],
        final_capital=equity[-1],
        metrics=zero_metrics,
        trades=trades or [],
        equity_curve=equity,
        equity_dates=dates,
        drawdown_curve=[0.0] * len(equity),
        total_commission=0.0,
        total_slippage=0.0,
    )


def make_trade(entry_day: int, exit_day: int, pnl: float) -> Trade:
    return Trade(
        symbol="TEST",
        side=OrderSide.BUY,
        entry_time=START + timedelta(days=entry_day),
        entry_price=100.0,
        exit_time=START + timedelta(days=exit_day),
        exit_price=100.0 + pnl,
        quantity=1.0,
        pnl=pnl,
        pnl_percent=pnl / 100.0,
        position_side="long",
    )


def make_bars(closes: list[float], start: datetime = START) -> BarData:
    n = len(closes)
    return BarData(
        symbol="BENCH",
        timeframe="1d",
        timestamps=[start + timedelta(days=i) for i in range(n)],
        opens=closes,
        highs=[c * 1.01 for c in closes],
        lows=[c * 0.99 for c in closes],
        closes=closes,
        volumes=[1_000_000.0] * n,
    )


class TestCagr:
    def test_one_year_is_unchanged(self):
        assert abs(cagr(1.0, 1.0) - 1.0) < 1e-9

    def test_two_years_compounds(self):
        assert abs(cagr(1.0, 2.0) - (math.sqrt(2) - 1)) < 1e-9

    def test_total_wipeout_is_negative_one(self):
        assert cagr(-1.0, 5.0) == -1.0

    def test_zero_years_is_zero(self):
        assert cagr(0.5, 0.0) == 0.0


class TestFullHistoryRegime:
    def test_spans_the_data(self):
        bars = make_bars([100.0] * 10)
        regime = full_history_regime(bars)
        assert regime.start == bars.timestamps[0]
        assert regime.end == bars.timestamps[-1]


class TestRegimeReport:
    def test_one_row_per_regime_in_order(self):
        result = make_result([100.0] * 20)
        regimes = [
            Regime(name="first", start=START, end=START + timedelta(days=5)),
            Regime(name="second", start=START + timedelta(days=10), end=START + timedelta(days=15)),
        ]
        rows = regime_report(result, regimes)
        assert [r.regime for r in rows] == ["first", "second"]

    def test_cagr_matches_helper(self):
        result = make_result([100.0, 200.0])
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=1))]
        row = regime_report(result, regimes)[0]
        assert abs(row.cagr - cagr(row.metrics.total_return, row.metrics.years)) < 1e-9

    def test_low_sample_flag_set_below_threshold(self):
        trades = [make_trade(i, i, 1.0) for i in range(3)]
        result = make_result([100.0] * 10, trades)
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=9))]
        row = regime_report(result, regimes)[0]
        assert row.metrics.trades == 3
        assert row.low_sample is True

    def test_low_sample_flag_clear_above_threshold(self):
        trades = [make_trade(i, i, 1.0) for i in range(LOW_SAMPLE_TRADES + 5)]
        result = make_result([100.0] * 10, trades)
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=9))]
        row = regime_report(result, regimes)[0]
        assert row.low_sample is False

    def test_passed_matches_empty_reasons(self):
        # Too few trades over a long window trips the kill filter.
        result = make_result([100.0] * 800)
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=799))]
        row = regime_report(result, regimes)[0]
        assert row.reasons
        assert row.passed is False

    def test_no_benchmark_means_none_fields(self):
        result = make_result([100.0, 110.0])
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=1))]
        row = regime_report(result, regimes, benchmark_data=None)[0]
        assert row.benchmark_total_return is None
        assert row.benchmark_cagr is None

    def test_benchmark_return_matches_buy_and_hold(self):
        result = make_result([100.0, 110.0])
        bench = make_bars([50.0, 55.0, 60.5])  # +10% then +10%
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=1))]
        row = regime_report(result, regimes, benchmark_data=bench)[0]
        assert abs(row.benchmark_total_return - 0.10) < 1e-9
        assert abs(row.benchmark_cagr - cagr(0.10, row.metrics.years)) < 1e-9

    def test_benchmark_out_of_range_is_none(self):
        result = make_result([100.0, 110.0])
        bench = make_bars([50.0, 55.0], start=START + timedelta(days=365 * 5))
        regimes = [Regime(name="r", start=START, end=START + timedelta(days=1))]
        row = regime_report(result, regimes, benchmark_data=bench)[0]
        assert row.benchmark_total_return is None
        assert row.benchmark_cagr is None
