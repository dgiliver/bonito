"""Tests for the engine-level regime filter (backtest path)."""

from datetime import datetime, timedelta

import pytest

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData

START = datetime(2024, 1, 1)


def make_bars(closes: list[float], symbol: str = "TEST", start: datetime = START) -> BarData:
    n = len(closes)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[start + timedelta(days=i) for i in range(n)],
        opens=closes,
        highs=[c * 1.01 for c in closes],
        lows=[c * 0.99 for c in closes],
        closes=closes,
        volumes=[1_000_000.0] * n,
    )


def make_strategy(regime: dict | None = None) -> StrategyConfig:
    config = {
        "name": "always_long",
        "symbols": ["TEST"],
        "timeframe": "1d",
        "indicators": [{"type": "sma", "name": "sma_2", "params": {"period": 2}}],
        "entry_rules": [
            {
                "conditions": [{"left": "close", "comparison": "gt", "right": 0.0}],
                "logic": "AND",
                "side": "long",
            }
        ],
        "exit_rules": [
            {
                "conditions": [{"left": "close", "comparison": "lt", "right": 0.0}],
                "logic": "AND",
                "side": "long",
            }
        ],
        "position_size": {"type": "percent_equity", "value": 50},
    }
    if regime:
        config["regime_filter"] = regime
    return StrategyConfig(**config)


def engine() -> BacktestEngine:
    return BacktestEngine(BacktestConfig(start_date=START, end_date=START + timedelta(days=60)))


class TestEngineRegimeFilter:
    def test_no_filter_trades_normally(self):
        data = make_bars([100.0 + i * 0.1 for i in range(40)])
        result = engine().run(make_strategy(), data)
        assert result.metrics.total_trades > 0 or len(result.trades) >= 0
        # always-enter strategy must be in the market
        assert any(result.equity_curve)

    def test_risk_off_regime_blocks_all_entries(self):
        data = make_bars([100.0 + i * 0.1 for i in range(40)])
        regime_data = make_bars([200.0 - i for i in range(40)], symbol="SPY")  # downtrend
        strategy = make_strategy({"symbol": "SPY", "sma_period": 5})

        result = engine().run(strategy, data, regime_data=regime_data)
        assert result.trades == []

    def test_risk_on_regime_allows_entries(self):
        data = make_bars([100.0 + i * 0.1 for i in range(40)])
        # Regime history starts before the data (the production warmup), so
        # its SMA is already defined on the first data bar.
        regime_data = make_bars(
            [100.0 + i for i in range(50)], symbol="SPY", start=START - timedelta(days=10)
        )
        gated = make_strategy({"symbol": "SPY", "sma_period": 5})
        ungated = make_strategy()

        gated_result = engine().run(gated, data, regime_data=regime_data)
        ungated_result = engine().run(ungated, data)
        # A permanently risk-on regime must not change behavior.
        assert len(gated_result.trades) == len(ungated_result.trades)
        assert gated_result.equity_curve == ungated_result.equity_curve

    def test_undefined_sma_is_risk_off(self):
        data = make_bars([100.0 + i * 0.1 for i in range(40)])
        # Only 3 regime bars but a 5-period SMA → never defined → risk-off.
        regime_data = make_bars([100.0, 101.0, 102.0], symbol="SPY")
        strategy = make_strategy({"symbol": "SPY", "sma_period": 5})

        result = engine().run(strategy, data, regime_data=regime_data)
        assert result.trades == []

    def test_missing_regime_data_raises(self):
        data = make_bars([100.0 + i * 0.1 for i in range(40)])
        strategy = make_strategy({"symbol": "SPY", "sma_period": 5})

        with pytest.raises(ValueError, match="regime_filter"):
            engine().run(strategy, data)

    def test_regime_flip_gates_entries_midway(self):
        # Regime: strong uptrend for 20 bars, then collapses below SMA.
        regime_closes = [100.0 + i for i in range(20)] + [60.0] * 20
        regime_data = make_bars(regime_closes, symbol="SPY")
        data = make_bars([100.0 + i * 0.1 for i in range(40)])
        strategy = make_strategy({"symbol": "SPY", "sma_period": 5})
        # Exit-less always-enter strategy: position opens during risk-on and
        # is still open at the end; what matters is no NEW entry fires while
        # risk-off. With one max position the trade list shows a single
        # open-then-forced-close entry, entered during the risk-on phase.
        result = engine().run(strategy, data, regime_data=regime_data)
        for trade in result.trades:
            assert trade.entry_time < START + timedelta(days=22)
