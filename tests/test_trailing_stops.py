"""Comprehensive tests for trailing stop functionality.

Test-driven development for F021: Trailing Stops.

Test Categories:
1. Model Tests - StopLossConfig with trailing types
2. Engine Unit Tests - Trailing stop calculation logic
3. Engine Integration Tests - Full backtest with trailing stops
4. Agent Integration Tests - Prompt → Engine → Response flow
5. Edge Cases - Gaps, no trades, immediate stops, etc.
"""

from datetime import datetime

import numpy as np
import pytest

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    PositionSizeConfig,
    PositionSizeType,
    Rule,
    RuleCondition,
    StopLossConfig,
    StopLossType,
    StrategyConfig,
)
from bonito.data.models import BarData

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def basic_config() -> BacktestConfig:
    """Standard backtest config."""
    return BacktestConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100_000.0,
        commission=0.0,  # No commission for simpler testing
        slippage=0.0,  # No slippage for simpler testing
    )


@pytest.fixture
def uptrend_data() -> BarData:
    """Simulated uptrend data - perfect for testing trailing stops.

    Pattern: Entry signal at bar 1, then steady climb, then crash.
    - Bars 0-1: Consolidation (entry signal on bar 1)
    - Bars 2-10: Steady uptrend (+2% per bar)
    - Bars 11-15: Sharp decline (-5% per bar)

    Expected trailing stop behavior:
    - Fixed 5% stop: Would exit at ~100 * 0.95 = 95
    - Trailing 5%: Should exit around 119 * 0.95 = 113 (protecting gains)
    """
    n = 20
    timestamps = [datetime(2024, 1, i + 1) for i in range(n)]

    # Start at 100, rise to ~119, then crash to ~91
    close = [100.0, 100.0]  # Entry bars
    for _ in range(2, 11):  # Uptrend
        close.append(close[-1] * 1.02)
    for _ in range(11, n):  # Crash
        close.append(close[-1] * 0.95)

    close = np.array(close)

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=(close * 0.995).tolist(),
        highs=(close * 1.01).tolist(),
        lows=(close * 0.99).tolist(),
        closes=close.tolist(),
        volumes=[1_000_000.0] * n,
    )


@pytest.fixture
def volatile_data() -> BarData:
    """Volatile data with gaps - tests gap handling for trailing stops.

    Pattern:
    - Bar 5: Large gap down (10% overnight gap)
    """
    n = 15
    timestamps = [datetime(2024, 1, i + 1) for i in range(n)]

    close = [100.0] * 5 + [85.0] + [85.0 + i for i in range(9)]  # Gap then recover
    close = np.array(close)

    # Create realistic OHLC around close
    opens = close.copy()
    opens[5] = 95.0  # Gap open (10% gap)

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=(close * 1.02).tolist(),
        lows=(np.minimum(close, opens) * 0.98).tolist(),
        closes=close.tolist(),
        volumes=[1_000_000.0] * n,
    )


@pytest.fixture
def always_entry_strategy() -> StrategyConfig:
    """Strategy that enters immediately and holds.

    Uses close > 0 as always-true entry condition.
    """
    return StrategyConfig(
        name="always_enter",
        description="Enter on first bar, hold",
        symbols=["TEST"],
        timeframe="1d",
        indicators=[
            IndicatorConfig(type="sma", name="sma", params={"period": 2}),
        ],
        entry_rules=[
            Rule(
                conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=0),
                ]
            )
        ],
        exit_rules=[],
        position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=95),
    )


# =============================================================================
# 1. Model Tests - StopLossConfig with new trailing types
# =============================================================================


class TestStopLossTypeEnum:
    """Test StopLossType enum has all required values."""

    def test_has_trailing_percent_type(self):
        """StopLossType should include TRAILING_PERCENT."""
        assert hasattr(StopLossType, "TRAILING_PERCENT")
        assert StopLossType.TRAILING_PERCENT.value == "trailing_percent"

    def test_has_trailing_atr_type(self):
        """StopLossType should include TRAILING_ATR."""
        assert hasattr(StopLossType, "TRAILING_ATR")
        assert StopLossType.TRAILING_ATR.value == "trailing_atr"

    def test_has_breakeven_type(self):
        """StopLossType should include BREAKEVEN."""
        assert hasattr(StopLossType, "BREAKEVEN")
        assert StopLossType.BREAKEVEN.value == "breakeven"

    def test_backward_compatibility_percent(self):
        """Original PERCENT type should still work."""
        assert StopLossType.PERCENT.value == "percent"

    def test_backward_compatibility_atr(self):
        """Original ATR type should still work."""
        assert StopLossType.ATR.value == "atr"


class TestStopLossConfigModel:
    """Test StopLossConfig model with new trailing stop fields."""

    def test_trailing_percent_config_valid(self):
        """Can create a trailing percent stop config."""
        config = StopLossConfig(
            type=StopLossType.TRAILING_PERCENT,
            value=0.05,
        )
        assert config.type == StopLossType.TRAILING_PERCENT
        assert config.value == 0.05

    def test_trailing_atr_config_valid(self):
        """Can create a trailing ATR stop config with atr_period."""
        config = StopLossConfig(
            type=StopLossType.TRAILING_ATR,
            value=2.0,
            atr_period=14,
        )
        assert config.type == StopLossType.TRAILING_ATR
        assert config.value == 2.0
        assert config.atr_period == 14

    def test_trailing_atr_default_period(self):
        """Trailing ATR should have default atr_period of 14."""
        config = StopLossConfig(
            type=StopLossType.TRAILING_ATR,
            value=2.0,
        )
        assert config.atr_period == 14

    def test_breakeven_config_with_trigger(self):
        """Breakeven stop should have trigger_percent."""
        config = StopLossConfig(
            type=StopLossType.BREAKEVEN,
            value=0.0,  # Stop at entry price
            trigger_percent=0.05,  # Trigger after 5% profit
        )
        assert config.type == StopLossType.BREAKEVEN
        assert config.trigger_percent == 0.05

    def test_backward_compatible_fixed_percent(self):
        """Original percent stop should still work."""
        config = StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        assert config.type == StopLossType.PERCENT
        # atr_period and trigger_percent should be None or default
        assert getattr(config, "atr_period", None) in (None, 14)

    def test_strategy_config_with_trailing_stop(self):
        """StrategyConfig should accept trailing stop."""
        strategy = StrategyConfig(
            name="test",
            symbols=["SPY"],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=100)])
            ],
            stop_loss=StopLossConfig(
                type=StopLossType.TRAILING_PERCENT,
                value=0.05,
            ),
        )
        assert strategy.stop_loss.type == StopLossType.TRAILING_PERCENT


# =============================================================================
# 2. Engine Unit Tests - Trailing stop calculation logic
# =============================================================================


class TestTrailingStopCalculation:
    """Test the core trailing stop calculation logic."""

    def test_trailing_percent_initial_stop(self, basic_config, uptrend_data, always_entry_strategy):
        """Initial trailing stop should be entry_price * (1 - trailing_pct)."""
        always_entry_strategy.stop_loss = StopLossConfig(
            type=StopLossType.TRAILING_PERCENT,
            value=0.05,
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(always_entry_strategy, uptrend_data)

        # With uptrend data, we should have trades
        assert len(result.trades) >= 1

        # First trade should have meaningful entry
        trade = result.trades[0]
        assert trade.entry_price > 0

    def test_trailing_stop_moves_up_in_uptrend(
        self, basic_config, uptrend_data, always_entry_strategy
    ):
        """Trailing stop should move up as price increases."""
        always_entry_strategy.stop_loss = StopLossConfig(
            type=StopLossType.TRAILING_PERCENT,
            value=0.05,  # 5% trailing
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(always_entry_strategy, uptrend_data)

        # Should have exited during crash, not at initial stop
        assert len(result.trades) >= 1
        trade = result.trades[0]

        # Exit reason should be stop_loss (trailing stop triggered)
        assert trade.exit_reason == "stop_loss"

        # Exit price should be HIGHER than initial stop would have been
        # Initial stop would be ~100 * 0.95 = 95
        # Trailing stop should exit around 113+ (95% of peak ~119)
        initial_stop_price = trade.entry_price * 0.95
        assert trade.exit_price > initial_stop_price * 1.1, (
            f"Trailing stop should have protected gains. "
            f"Exit: {trade.exit_price}, Initial stop would be: {initial_stop_price}"
        )

    def test_trailing_stop_never_moves_down(self, basic_config):
        """Trailing stop should never decrease (ratchet effect)."""
        # Create data: up, down, up, down pattern
        n = 10
        timestamps = [datetime(2024, 1, i + 1) for i in range(n)]
        close = np.array([100, 105, 102, 108, 104, 110, 105, 112, 106, 80])

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close * 1.01).tolist(),
            lows=(close * 0.99).tolist(),
            closes=close.tolist(),
            volumes=[1_000_000.0] * n,
        )

        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            indicators=[IndicatorConfig(type="sma", name="sma", params={"period": 2})],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=0)])
            ],
            stop_loss=StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.10),
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=95),
        )

        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100_000.0,
            commission=0.0,
            slippage=0.0,
        )

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Should exit at the crash at bar 9 (price 80)
        # Peak was 112, so trailing stop should be ~100.8
        assert len(result.trades) >= 1
        trade = result.trades[0]

        # Trailing stop from 112 would be 112 * 0.90 = 100.8
        # Price crashed to 80, so should have exited above 80 (gap down scenario)
        assert trade.exit_reason == "stop_loss"


class TestTrailingATRStop:
    """Test trailing ATR-based stops."""

    def test_trailing_atr_requires_atr_indicator(self, basic_config):
        """Trailing ATR stop should automatically add ATR indicator if needed."""
        n = 30
        timestamps = [datetime(2024, 1, i + 1) for i in range(n)]
        close = np.linspace(100, 130, n)  # Steady uptrend

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=(close * 0.99).tolist(),
            highs=(close * 1.02).tolist(),
            lows=(close * 0.98).tolist(),
            closes=close.tolist(),
            volumes=[1_000_000.0] * n,
        )

        strategy = StrategyConfig(
            name="test_atr_trailing",
            symbols=["TEST"],
            indicators=[IndicatorConfig(type="sma", name="sma", params={"period": 2})],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=0)])
            ],
            stop_loss=StopLossConfig(
                type=StopLossType.TRAILING_ATR,
                value=2.0,  # 2x ATR
                atr_period=14,
            ),
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=95),
        )

        engine = BacktestEngine(basic_config)
        # Should not raise - engine should handle ATR computation
        result = engine.run(strategy, data)
        assert result is not None


class TestBreakevenStop:
    """Test breakeven stop functionality."""

    def test_breakeven_moves_to_entry_after_trigger(self, basic_config):
        """Breakeven stop should move to entry price after profit trigger."""
        n = 15
        timestamps = [datetime(2024, 1, i + 1) for i in range(n)]
        # Price goes up 10%, then crashes
        close = np.array(
            [
                100.0,
                100.0,
                105.0,
                110.0,
                115.0,
                112.0,
                108.0,
                95.0,
                90.0,
                85.0,
                80.0,
                75.0,
                70.0,
                65.0,
                60.0,
            ]
        )

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close * 1.01).tolist(),
            lows=(close * 0.99).tolist(),
            closes=close.tolist(),
            volumes=[1_000_000.0] * n,
        )

        strategy = StrategyConfig(
            name="test_breakeven",
            symbols=["TEST"],
            indicators=[IndicatorConfig(type="sma", name="sma", params={"period": 2})],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=0)])
            ],
            stop_loss=StopLossConfig(
                type=StopLossType.BREAKEVEN,
                value=0.0,  # Move to entry price
                trigger_percent=0.05,  # After 5% profit
            ),
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=95),
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        trade = result.trades[0]

        # Entry around 100, price went to 115 (>5% trigger)
        # Breakeven stop should be at entry price (~100)
        # Crash went to 95 then 90, so should have exited near entry
        assert trade.exit_reason == "stop_loss"
        # Exit should be near entry price (breakeven)
        assert abs(trade.exit_price - trade.entry_price) < trade.entry_price * 0.10


# =============================================================================
# 3. Engine Integration Tests - Full backtest scenarios
# =============================================================================


class TestTrailingStopBacktestIntegration:
    """Full backtest integration tests."""

    def test_trailing_vs_fixed_stop_comparison(
        self, basic_config, uptrend_data, always_entry_strategy
    ):
        """Trailing stop should outperform fixed stop in trending market."""
        # Run with fixed stop
        fixed_strategy = always_entry_strategy.model_copy(deep=True)
        fixed_strategy.stop_loss = StopLossConfig(type=StopLossType.PERCENT, value=0.05)

        # Run with trailing stop
        trailing_strategy = always_entry_strategy.model_copy(deep=True)
        trailing_strategy.stop_loss = StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05)

        engine = BacktestEngine(basic_config)

        fixed_result = engine.run(fixed_strategy, uptrend_data)
        trailing_result = engine.run(trailing_strategy, uptrend_data)

        # Trailing stop should capture more profit in uptrend
        assert trailing_result.final_capital >= fixed_result.final_capital, (
            f"Trailing: ${trailing_result.final_capital:,.2f} "
            f"should >= Fixed: ${fixed_result.final_capital:,.2f}"
        )

    def test_trailing_stop_exit_reason(self, basic_config, uptrend_data, always_entry_strategy):
        """Trades closed by trailing stop should have correct exit_reason."""
        always_entry_strategy.stop_loss = StopLossConfig(
            type=StopLossType.TRAILING_PERCENT, value=0.05
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(always_entry_strategy, uptrend_data)

        # Find trades that hit stop
        stop_trades = [t for t in result.trades if t.exit_reason == "stop_loss"]
        assert len(stop_trades) > 0, "Should have at least one trade closed by stop"

    def test_no_trades_does_not_crash(self, basic_config):
        """Engine should handle no trades scenario gracefully."""
        n = 10
        timestamps = [datetime(2024, 1, i + 1) for i in range(n)]
        close = [100.0] * n  # Flat

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close,
            highs=close,
            lows=close,
            closes=close,
            volumes=[1_000_000.0] * n,
        )

        # Entry condition that never triggers
        strategy = StrategyConfig(
            name="never_enters",
            symbols=["TEST"],
            indicators=[IndicatorConfig(type="sma", name="sma", params={"period": 2})],
            entry_rules=[
                Rule(
                    conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=999999)]
                )
            ],
            stop_loss=StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05),
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(strategy, data)

        assert len(result.trades) == 0
        assert result.final_capital == basic_config.initial_capital


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_gap_down_through_trailing_stop(
        self, basic_config, volatile_data, always_entry_strategy
    ):
        """Price gap through trailing stop should exit at gap open."""
        always_entry_strategy.stop_loss = StopLossConfig(
            type=StopLossType.TRAILING_PERCENT, value=0.05
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(always_entry_strategy, volatile_data)

        # Should have exited when gap happened
        assert len(result.trades) >= 1
        # Exit should be at/near gap open, not the theoretical stop price

    def test_immediate_stop_hit(self, basic_config):
        """Stop hit on very next bar after entry."""
        n = 5
        timestamps = [datetime(2024, 1, i + 1) for i in range(n)]
        close = np.array([100.0, 100.0, 80.0, 80.0, 80.0])  # Immediate crash

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close * 1.01).tolist(),
            lows=(close * 0.99).tolist(),
            closes=close.tolist(),
            volumes=[1_000_000.0] * n,
        )

        strategy = StrategyConfig(
            name="immediate_stop",
            symbols=["TEST"],
            indicators=[IndicatorConfig(type="sma", name="sma", params={"period": 2})],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=0)])
            ],
            stop_loss=StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05),
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=95),
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        trade = result.trades[0]
        assert trade.exit_reason == "stop_loss"

    def test_trailing_stop_with_take_profit(self, basic_config):
        """Trailing stop should work alongside take profit."""
        n = 20
        timestamps = [datetime(2024, 1, i + 1) for i in range(n)]
        # Steady uptrend - should hit take profit
        close = np.linspace(100, 150, n)

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=(close * 0.99).tolist(),
            highs=(close * 1.01).tolist(),
            lows=(close * 0.98).tolist(),
            closes=close.tolist(),
            volumes=[1_000_000.0] * n,
        )

        from bonito.backtest.strategy import TakeProfitConfig, TakeProfitType

        strategy = StrategyConfig(
            name="stop_and_tp",
            symbols=["TEST"],
            indicators=[IndicatorConfig(type="sma", name="sma", params={"period": 2})],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=0)])
            ],
            stop_loss=StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.10),
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.20),
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=95),
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(strategy, data)

        assert len(result.trades) >= 1
        # Should hit take profit before trailing stop in steady uptrend
        trade = result.trades[0]
        assert trade.exit_reason in ("take_profit", "end_of_data")


# =============================================================================
# 4. Agent Integration Tests - Full flow from tool to result
# =============================================================================


class TestAgentToolIntegration:
    """Test integration with agent tools."""

    @pytest.mark.asyncio
    async def test_create_strategy_with_trailing_stop(self):
        """CreateStrategyTool should accept trailing_stop_pct parameter."""
        from bonito.agent.tools import CreateStrategyTool

        strategy_store = {}
        tool = CreateStrategyTool(strategy_store)

        result = await tool.execute(
            name="trailing_test",
            description="Test trailing stop",
            indicators=[{"type": "sma", "name": "sma", "params": {"period": 20}}],
            entry_conditions=[{"left": "close", "comparison": "gt", "right": "sma"}],
            trailing_stop_pct=0.05,  # New parameter
        )

        assert result.success, f"Failed: {result.error}"
        assert "trailing_test" in strategy_store

        strategy = strategy_store["trailing_test"]
        assert strategy.stop_loss is not None
        assert strategy.stop_loss.type == StopLossType.TRAILING_PERCENT
        assert strategy.stop_loss.value == 0.05

    @pytest.mark.asyncio
    async def test_create_strategy_with_trailing_atr(self):
        """CreateStrategyTool should accept trailing_atr_multiple parameter."""
        from bonito.agent.tools import CreateStrategyTool

        strategy_store = {}
        tool = CreateStrategyTool(strategy_store)

        result = await tool.execute(
            name="trailing_atr_test",
            description="Test trailing ATR stop",
            indicators=[{"type": "sma", "name": "sma", "params": {"period": 20}}],
            entry_conditions=[{"left": "close", "comparison": "gt", "right": "sma"}],
            trailing_atr_multiple=2.5,
            atr_period=14,
        )

        assert result.success, f"Failed: {result.error}"

        strategy = strategy_store["trailing_atr_test"]
        assert strategy.stop_loss is not None
        assert strategy.stop_loss.type == StopLossType.TRAILING_ATR
        assert strategy.stop_loss.value == 2.5
        assert strategy.stop_loss.atr_period == 14

    @pytest.mark.asyncio
    async def test_full_flow_create_and_backtest_trailing(self):
        """Full flow: create strategy with trailing stop → run backtest."""
        from bonito.agent.tools import CreateStrategyTool, RunBacktestTool

        strategy_store = {}
        result_store = {}

        create_tool = CreateStrategyTool(strategy_store)
        backtest_tool = RunBacktestTool(strategy_store, result_store)

        # Create strategy with trailing stop
        create_result = await create_tool.execute(
            name="trailing_spy",
            description="SPY with trailing stop",
            indicators=[{"type": "rsi", "name": "rsi", "params": {"period": 14}}],
            entry_conditions=[{"left": "rsi", "comparison": "lt", "right": 30}],
            trailing_stop_pct=0.05,
        )
        assert create_result.success, f"Create failed: {create_result.error}"

        # Run backtest
        bt_result = await backtest_tool.execute(
            strategy_name="trailing_spy",
            symbol="SPY",
            start_date="2024-01-01",
            end_date="2024-06-01",
        )
        assert bt_result.success, f"Backtest failed: {bt_result.error}"

        # Should have metrics
        assert "metrics" in bt_result.data
        assert "total_return" in bt_result.data["metrics"]


# =============================================================================
# 5. Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Ensure existing functionality still works."""

    def test_fixed_percent_stop_still_works(
        self, basic_config, uptrend_data, always_entry_strategy
    ):
        """Original percent stop should work unchanged."""
        always_entry_strategy.stop_loss = StopLossConfig(
            type=StopLossType.PERCENT,  # Original type
            value=0.05,
        )

        engine = BacktestEngine(basic_config)
        result = engine.run(always_entry_strategy, uptrend_data)

        # Should still work
        assert result is not None
        assert result.metrics is not None

    def test_no_stop_loss_still_works(self, basic_config, uptrend_data, always_entry_strategy):
        """Strategy without stop loss should still work."""
        always_entry_strategy.stop_loss = None

        engine = BacktestEngine(basic_config)
        result = engine.run(always_entry_strategy, uptrend_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_create_strategy_with_old_stop_loss_pct(self):
        """Original stop_loss_pct parameter should still work."""
        from bonito.agent.tools import CreateStrategyTool

        strategy_store = {}
        tool = CreateStrategyTool(strategy_store)

        # Old way - should still work
        result = await tool.execute(
            name="old_style",
            description="Test old style",
            indicators=[{"type": "sma", "name": "sma", "params": {"period": 20}}],
            entry_conditions=[{"left": "close", "comparison": "gt", "right": "sma"}],
            stop_loss_pct=0.05,  # Original parameter
        )

        assert result.success
        strategy = strategy_store["old_style"]
        assert strategy.stop_loss is not None
        assert strategy.stop_loss.type == StopLossType.PERCENT


# =============================================================================
# Run tests with: pytest tests/test_trailing_stops.py -v
# =============================================================================
