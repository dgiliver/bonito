"""Tests for short selling functionality (F020)."""

from datetime import datetime, timedelta

import numpy as np

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    IndicatorType,
    PositionSizeConfig,
    PositionSizeType,
    Rule,
    RuleCondition,
    StopLossConfig,
    StopLossType,
    StrategyConfig,
    TakeProfitConfig,
    TakeProfitType,
)
from bonito.data.models import BarData


def create_test_data(
    prices: list[float],
    start_date: datetime | None = None,
) -> BarData:
    """Create test bar data from a list of close prices."""
    n = len(prices)
    start = start_date or datetime(2023, 1, 1)
    timestamps = [start + timedelta(days=i) for i in range(n)]

    # Create OHLC from close prices with small variations
    closes = np.array(prices)
    opens = closes * 0.999
    highs = closes * 1.005
    lows = closes * 0.995
    volumes = np.full(n, 1000000.0)

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=highs.tolist(),
        lows=lows.tolist(),
        closes=closes.tolist(),
        volumes=volumes.tolist(),
    )


class TestRuleSideField:
    """Test the side field on Rule model."""

    def test_rule_default_side_is_long(self):
        """Rules should default to long side."""
        rule = Rule(
            conditions=[RuleCondition(left="close", comparison=Comparison.GT, right="sma_20")]
        )
        assert rule.side == "long"

    def test_rule_can_be_short(self):
        """Rules can be set to short side."""
        rule = Rule(
            conditions=[RuleCondition(left="rsi_14", comparison=Comparison.GT, right=80)],
            side="short",
        )
        assert rule.side == "short"

    def test_rule_side_in_prompt(self):
        """Short rules should be indicated in strategy prompt."""
        strategy = StrategyConfig(
            name="Short Test",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14})
            ],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="rsi_14", comparison=Comparison.GT, right=80)],
                    side="short",
                )
            ],
        )
        prompt = strategy.to_prompt_description()
        assert "[SHORT]" in prompt


class TestShortPnLCalculation:
    """Test P&L calculation for short positions."""

    def test_short_profit_when_price_falls(self):
        """Short position should profit when price falls."""
        # Price falls from 100 to 90 - should be profitable
        prices = [100, 100, 100, 95, 90, 90, 90, 90, 90, 90]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short on High Price",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)],
                    side="short",
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.LTE, right=91)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        # Should have positive P&L since price fell
        assert result.trades[0].pnl > 0
        assert result.trades[0].position_side == "short"

    def test_short_loss_when_price_rises(self):
        """Short position should lose when price rises."""
        # Price rises from 100 to 110 - should lose money
        prices = [100, 100, 100, 105, 110, 115, 115, 115, 115, 115]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short Loss Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)],
                    side="short",
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=114)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        # Should have negative P&L since price rose
        assert result.trades[0].pnl < 0
        assert result.trades[0].position_side == "short"


class TestShortStopLoss:
    """Test stop loss behavior for short positions."""

    def test_short_stop_triggers_on_price_rise(self):
        """Short stop loss should trigger when price rises above stop level."""
        # Price rises from 100 to 110 - 10% stop should trigger
        prices = [100, 100, 100, 102, 105, 108, 111, 115, 115, 115]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short Stop Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)],
                    side="short",
                )
            ],
            exit_rules=[],  # No exit rules - rely on stop
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05),  # 5% stop
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        # Should exit on stop loss
        assert result.trades[0].exit_reason == "stop_loss"

    def test_short_stop_does_not_trigger_on_price_fall(self):
        """Short stop loss should NOT trigger when price falls (that's profit)."""
        # Price falls from 100 to 90 - stop should not trigger
        prices = [100, 100, 100, 98, 95, 92, 90, 88, 88, 88]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short No Stop Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)],
                    side="short",
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.LTE, right=89)])
            ],
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05),
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        # Should exit on signal, not stop
        assert result.trades[0].exit_reason == "signal"
        assert result.trades[0].pnl > 0  # Profitable


class TestShortTrailingStop:
    """Test trailing stop behavior for short positions."""

    def test_short_trailing_stop_tracks_low(self):
        """Short trailing stop should track lowest price, not highest."""
        # Price falls from 100 to 85, then rises - trailing stop should protect gains
        prices = [100, 100, 100, 95, 90, 85, 88, 92, 96, 100]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short Trailing Stop Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)],
                    side="short",
                )
            ],
            exit_rules=[],
            stop_loss=StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.10),  # 10% trail
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        # Should exit on trailing stop when price rises from low
        assert result.trades[0].exit_reason == "stop_loss"
        # Exit price should be around 85 * 1.10 = 93.5 or higher
        # Since we entered around 100 and exited around 93.5, should still have some profit
        # But the key is it protected us from the full reversal to 100


class TestShortTakeProfit:
    """Test take profit behavior for short positions."""

    def test_short_take_profit_triggers_on_price_fall(self):
        """Short take profit should trigger when price falls below target."""
        # Price falls from 100 to 85 - 10% TP should trigger
        prices = [100, 100, 100, 95, 92, 88, 85, 85, 85, 85]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short TP Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)],
                    side="short",
                )
            ],
            exit_rules=[],
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.10),  # 10% TP
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        assert result.trades[0].exit_reason == "take_profit"
        assert result.trades[0].pnl > 0


class TestMixedLongShortStrategies:
    """Test strategies with both long and short rules."""

    def test_long_and_short_rules_work_together(self):
        """Strategy with both long and short entry rules should work."""
        # Oscillating price to trigger both long and short entries
        prices = [100, 95, 90, 85, 90, 95, 100, 105, 110, 105, 100, 95]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Long/Short Strategy",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                # Long when price low
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.LTE, right=86)],
                    side="long",
                ),
                # Short when price high
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=109)],
                    side="short",
                ),
            ],
            exit_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=94)],
                    logic="OR",
                )
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=50),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Should have trades
        assert len(result.trades) >= 1


class TestTradeModelSideField:
    """Test the position_side field on Trade model."""

    def test_long_trade_has_long_position_side(self):
        """Long trades should have position_side='long'."""
        prices = [100, 95, 90, 85, 90, 95, 100, 105]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Long Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.LTE, right=91)],
                    side="long",
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        assert result.trades[0].position_side == "long"

    def test_short_trade_has_short_position_side(self):
        """Short trades should have position_side='short'."""
        prices = [100, 105, 110, 115, 110, 105, 100, 95]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Short Test",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=114)],
                    side="short",
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.LTE, right=96)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        assert result.trades[0].position_side == "short"


class TestBackwardCompatibility:
    """Ensure existing long-only strategies still work."""

    def test_existing_long_strategy_still_works(self):
        """Existing strategies without side field should default to long."""
        prices = [100, 95, 90, 85, 90, 95, 100, 105]
        data = create_test_data(prices)

        # Old-style strategy without side field
        strategy = StrategyConfig(
            name="Legacy Long",
            symbols=["TEST"],
            indicators=[],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.LTE, right=91)]
                    # No side field - should default to "long"
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GTE, right=99)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100),
        )

        config = BacktestConfig(
            start_date=data.timestamps[0],
            end_date=data.timestamps[-1],
            initial_capital=10000,
            commission=0,
            slippage=0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        assert result.trades[0].position_side == "long"
        assert result.trades[0].pnl > 0  # Should profit from price rise
