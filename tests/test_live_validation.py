"""Tests for strategy validation (bonito.trading.validation)."""

from datetime import datetime, timedelta

from bonito.backtest.models import BacktestResult, OrderSide, PerformanceMetrics, Trade
from bonito.backtest.strategy import StrategyConfig
from bonito.trading.validation import (
    WindowMetrics,
    kill_verdict,
    strategy_hash,
    window_metrics,
)

START = datetime(2024, 1, 1)


def make_result(
    equity: list[float],
    trades: list[Trade] | None = None,
    start: datetime = START,
) -> BacktestResult:
    dates = [start + timedelta(days=i) for i in range(len(equity))]
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


class TestWindowMetrics:
    def test_full_window_total_return(self):
        result = make_result([100, 110, 121])
        m = window_metrics(result, START, START + timedelta(days=2))
        assert abs(m.total_return - 0.21) < 1e-9

    def test_window_slices_equity(self):
        # Equity doubles in the first half, flat in the second.
        result = make_result([100, 150, 200, 200, 200])
        m = window_metrics(result, START + timedelta(days=2), START + timedelta(days=4))
        assert m.total_return == 0.0

    def test_drawdown_peak_resets_at_window_start(self):
        # Full curve peaks at 200 then falls to 150 (25% DD), but inside the
        # window [day2, day4] the peak is 160 → DD = 10/160 = 6.25%.
        result = make_result([100, 200, 150, 160, 150])
        m = window_metrics(result, START + timedelta(days=2), START + timedelta(days=4))
        assert abs(m.max_drawdown - 10 / 160) < 1e-9

    def test_trades_counted_by_exit_date(self):
        trades = [make_trade(0, 1, 5.0), make_trade(2, 3, -2.0), make_trade(3, 4, 1.0)]
        result = make_result([100] * 5, trades)
        m = window_metrics(result, START + timedelta(days=3), START + timedelta(days=4))
        assert m.trades == 2
        assert abs(m.win_rate - 0.5) < 1e-9

    def test_empty_window(self):
        result = make_result([100, 110])
        m = window_metrics(result, START + timedelta(days=30), START + timedelta(days=40))
        assert m.trades == 0
        assert m.total_return == 0.0
        assert m.sharpe == 0.0

    def test_flat_days_excluded_from_sharpe(self):
        # One trade held days 0-2 with volatile returns; days 3+ flat with no
        # position. Sharpe must come from the held days only (nonzero).
        equity = [100, 110, 105, 105, 105, 105]
        result = make_result(equity, [make_trade(0, 2, 5.0)])
        m = window_metrics(result, START, START + timedelta(days=5))
        assert m.sharpe != 0.0


class TestKillVerdict:
    def base_metrics(self, **overrides) -> WindowMetrics:
        defaults = {
            "start": START,
            "end": START + timedelta(days=365),
            "years": 1.0,
            "trades": 20,
            "win_rate": 0.5,
            "total_return": 0.1,
            "sharpe": 1.0,
            "max_drawdown": 0.10,
        }
        defaults.update(overrides)
        return WindowMetrics(**defaults)

    def test_passes_clean_metrics(self):
        assert kill_verdict(self.base_metrics()) == []

    def test_too_few_trades_scales_with_window(self):
        # 7 trades/year required: 1-year window needs 7, 2-year needs 14.
        assert kill_verdict(self.base_metrics(trades=6)) != []
        assert kill_verdict(self.base_metrics(trades=7)) == []
        assert kill_verdict(self.base_metrics(trades=13, years=2.0)) != []
        assert kill_verdict(self.base_metrics(trades=14, years=2.0)) == []

    def test_excessive_drawdown(self):
        reasons = kill_verdict(self.base_metrics(max_drawdown=0.30))
        assert any("DD" in r for r in reasons)

    def test_suspicious_sharpe(self):
        reasons = kill_verdict(self.base_metrics(sharpe=3.5))
        assert any("Sharpe" in r for r in reasons)

    def test_multiple_failures_all_reported(self):
        reasons = kill_verdict(self.base_metrics(trades=1, max_drawdown=0.5, sharpe=4.0))
        assert len(reasons) == 3


class TestStrategyHash:
    def make_strategy(self, **overrides) -> StrategyConfig:
        base = {
            "name": "a",
            "symbols": ["TEST"],
            "entry_rules": [
                {
                    "conditions": [{"left": "close", "comparison": "gt", "right": 1.0}],
                    "logic": "AND",
                    "side": "long",
                }
            ],
        }
        base.update(overrides)
        return StrategyConfig(**base)

    def test_cosmetic_fields_ignored(self):
        a = self.make_strategy(name="a", description="x")
        b = self.make_strategy(name="b", description="y")
        assert strategy_hash(a) == strategy_hash(b)

    def test_behavioral_change_changes_hash(self):
        a = self.make_strategy()
        b = self.make_strategy(stop_loss={"type": "percent", "value": 0.05})
        assert strategy_hash(a) != strategy_hash(b)
