"""Tests for rolling lookback conditions (F022)."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.indicators import (
    crossed_above_within,
    crossed_below_within,
    percentile_rank,
    rolling_max,
    rolling_mean,
    rolling_min,
    rolling_std,
    was_above,
    was_below,
    zscore,
)
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    PositionSizeConfig,
    PositionSizeType,
    Rule,
    RuleCondition,
    StrategyConfig,
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


class TestRollingMax:
    """Test rolling_max indicator."""

    def test_rolling_max_basic(self):
        """Rolling max should return highest value in window."""
        values = np.array([10.0, 12.0, 8.0, 15.0, 11.0, 9.0, 14.0])
        result = rolling_max(values, period=3)

        # First 2 values should be NaN (not enough data)
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        # From index 2 onwards
        assert result[2] == 12.0  # max(10, 12, 8)
        assert result[3] == 15.0  # max(12, 8, 15)
        assert result[4] == 15.0  # max(8, 15, 11)
        assert result[5] == 15.0  # max(15, 11, 9)
        assert result[6] == 14.0  # max(11, 9, 14)

    def test_rolling_max_all_same(self):
        """Rolling max with constant values."""
        values = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        result = rolling_max(values, period=3)
        assert result[2] == 5.0
        assert result[4] == 5.0


class TestRollingMin:
    """Test rolling_min indicator."""

    def test_rolling_min_basic(self):
        """Rolling min should return lowest value in window."""
        values = np.array([10.0, 12.0, 8.0, 15.0, 11.0, 9.0, 14.0])
        result = rolling_min(values, period=3)

        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == 8.0  # min(10, 12, 8)
        assert result[3] == 8.0  # min(12, 8, 15)
        assert result[4] == 8.0  # min(8, 15, 11)
        assert result[5] == 9.0  # min(15, 11, 9)
        assert result[6] == 9.0  # min(11, 9, 14)


class TestRollingMean:
    """Test rolling_mean indicator."""

    def test_rolling_mean_basic(self):
        """Rolling mean should return average of window."""
        values = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        result = rolling_mean(values, period=3)

        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == pytest.approx(20.0)  # (10+20+30)/3
        assert result[3] == pytest.approx(30.0)  # (20+30+40)/3
        assert result[4] == pytest.approx(40.0)  # (30+40+50)/3


class TestRollingStd:
    """Test rolling_std indicator."""

    def test_rolling_std_basic(self):
        """Rolling std should return standard deviation of window."""
        values = np.array([10.0, 10.0, 10.0, 20.0, 20.0])
        result = rolling_std(values, period=3)

        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == 0.0  # All same values
        assert result[3] > 0.0  # Has variance


class TestZScore:
    """Test zscore indicator."""

    def test_zscore_basic(self):
        """Z-score should be (value - mean) / std."""
        values = np.array([10.0, 10.0, 10.0, 10.0, 20.0])
        result = zscore(values, period=4)

        # First 3 values are NaN
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert np.isnan(result[2])
        # Index 3: all 10s, z-score is 0
        assert result[3] == pytest.approx(0.0)
        # Index 4: 20 is above mean of (10,10,10,20)=12.5
        assert result[4] > 0  # Above mean

    def test_zscore_constant_returns_zero(self):
        """Z-score of constant values should be 0 (not NaN)."""
        values = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        result = zscore(values, period=3)
        # All same values - z-score should be 0, not NaN
        assert result[4] == 0.0


class TestPercentileRank:
    """Test percentile_rank indicator."""

    def test_percentile_rank_basic(self):
        """Percentile rank should be 0-100."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = percentile_rank(values, period=5)

        # Index 4 has the highest value in the window
        assert result[4] > 80  # Should be near 100 (highest)

    def test_percentile_rank_at_minimum(self):
        """Value at period low should have low percentile."""
        values = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        result = percentile_rank(values, period=5)

        # Index 4 has the lowest value
        assert result[4] < 20  # Should be near 0 (lowest)


class TestWasAbove:
    """Test was_above comparison function."""

    def test_was_above_finds_condition(self):
        """was_above should find if condition was ever true in window."""
        left = np.array([5.0, 15.0, 5.0, 5.0, 5.0])
        right = 10.0  # Threshold
        result = was_above(left, right, lookback=3)

        # Index 0,1: not enough lookback
        assert result[0] is False or result[0] == False  # noqa: E712
        # Index 2: window is [5, 15, 5] - 15 > 10, so True
        assert result[2] is True or result[2] == True  # noqa: E712
        # Index 3: window is [15, 5, 5] - 15 > 10, so True
        assert result[3] is True or result[3] == True  # noqa: E712
        # Index 4: window is [5, 5, 5] - none > 10, so False
        assert result[4] is False or result[4] == False  # noqa: E712

    def test_was_above_with_array_right(self):
        """was_above should work with array right operand."""
        left = np.array([5.0, 15.0, 5.0, 5.0, 5.0])
        right = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
        result = was_above(left, right, lookback=3)

        assert result[2] is True or result[2] == True  # noqa: E712


class TestWasBelow:
    """Test was_below comparison function."""

    def test_was_below_finds_condition(self):
        """was_below should find if condition was ever true in window."""
        left = np.array([50.0, 25.0, 50.0, 50.0, 50.0])
        right = 30.0  # Threshold
        result = was_below(left, right, lookback=3)

        # Index 2: window is [50, 25, 50] - 25 < 30, so True
        assert result[2] is True or result[2] == True  # noqa: E712
        # Index 4: window is [50, 50, 50] - none < 30, so False
        assert result[4] is False or result[4] == False  # noqa: E712


class TestCrossedAboveWithin:
    """Test crossed_above_within comparison function."""

    def test_crossed_above_detects_crossover(self):
        """crossed_above_within should detect crossover in lookback."""
        # Left crosses above 10 between index 1 and 2
        left = np.array([5.0, 8.0, 12.0, 12.0, 12.0, 12.0])
        right = 10.0
        result = crossed_above_within(left, right, lookback=3)

        # Index 2: crossover just happened (8->12 crosses 10)
        assert result[2] is True or result[2] == True  # noqa: E712
        # Index 3: crossover was 1 bar ago, still in window
        assert result[3] is True or result[3] == True  # noqa: E712
        # Index 4: crossover was 2 bars ago, still in 3-bar window
        assert result[4] is True or result[4] == True  # noqa: E712
        # Index 5: crossover was 3 bars ago, outside 3-bar window
        assert result[5] is False or result[5] == False  # noqa: E712


class TestCrossedBelowWithin:
    """Test crossed_below_within comparison function."""

    def test_crossed_below_detects_crossunder(self):
        """crossed_below_within should detect crossunder in lookback."""
        # Left crosses below 10 between index 1 and 2
        left = np.array([15.0, 12.0, 8.0, 8.0, 8.0, 8.0])
        right = 10.0
        result = crossed_below_within(left, right, lookback=3)

        # Index 2: crossunder just happened (12->8 crosses 10)
        assert result[2] is True or result[2] == True  # noqa: E712
        # Index 5: crossunder was 3 bars ago, outside 3-bar window
        assert result[5] is False or result[5] == False  # noqa: E712


class TestRollingIndicatorsInStrategy:
    """Test rolling indicators used in strategy conditions."""

    def test_breakout_strategy_with_rolling_max(self):
        """Strategy should trigger when close >= rolling_max (breakout)."""
        # Price rises, hits new highs at end
        prices = [100, 102, 101, 103, 99, 98, 105, 107, 106]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Breakout",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(
                    type="rolling_max",
                    name="high_5",
                    params={"series": "close", "period": 5},
                )
            ],
            entry_rules=[
                Rule(
                    conditions=[
                        RuleCondition(left="close", comparison=Comparison.GTE, right="high_5")
                    ]
                )
            ],
            exit_rules=[
                Rule(
                    conditions=[
                        RuleCondition(left="close", comparison=Comparison.LT, right="high_5")
                    ]
                )
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

        # Should have at least one trade on breakout
        assert len(result.trades) >= 1

    def test_mean_reversion_with_zscore(self):
        """Strategy should trigger when z-score is extreme."""
        # Price with big spike at end
        prices = [100, 100, 100, 100, 100, 100, 100, 100, 120, 100]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Mean Reversion",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(
                    type="zscore",
                    name="price_zscore",
                    params={"series": "close", "period": 5},
                )
            ],
            entry_rules=[
                Rule(
                    conditions=[
                        RuleCondition(left="price_zscore", comparison=Comparison.GT, right=1.5)
                    ],
                    side="short",
                )
            ],
            exit_rules=[
                Rule(
                    conditions=[
                        RuleCondition(left="price_zscore", comparison=Comparison.LT, right=0.5)
                    ]
                )
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

        # Should have at least one short trade when z-score spikes
        assert len(result.trades) >= 1


class TestLookbackComparisonsInStrategy:
    """Test was_above/was_below comparisons in strategy rules."""

    def test_was_below_triggers_entry(self):
        """Strategy should trigger if condition was met recently."""
        # RSI-like pattern: dips below 30 then recovers
        prices = [100, 95, 90, 85, 90, 95, 100, 105]
        data = create_test_data(prices)

        strategy = StrategyConfig(
            name="Recent Oversold",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(type="rsi", name="rsi_5", params={"period": 5}),
            ],
            entry_rules=[
                Rule(
                    conditions=[
                        # RSI was below 40 in last 3 bars
                        RuleCondition(
                            left="rsi_5",
                            comparison=Comparison.WAS_BELOW,
                            right=40,
                            lookback=3,
                        )
                    ]
                )
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="rsi_5", comparison=Comparison.GT, right=60)])
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

        # Strategy should execute without error
        assert result is not None


class TestRuleConditionLookbackField:
    """Test the lookback field on RuleCondition model."""

    def test_lookback_field_default_is_none(self):
        """RuleCondition should have lookback=None by default."""
        condition = RuleCondition(left="rsi", comparison=Comparison.LT, right=30)
        assert condition.lookback is None

    def test_lookback_field_can_be_set(self):
        """RuleCondition should accept lookback parameter."""
        condition = RuleCondition(
            left="rsi",
            comparison=Comparison.WAS_BELOW,
            right=30,
            lookback=5,
        )
        assert condition.lookback == 5

    def test_lookback_must_be_positive(self):
        """Lookback must be >= 1 if specified."""
        with pytest.raises(ValueError):
            RuleCondition(
                left="rsi",
                comparison=Comparison.WAS_BELOW,
                right=30,
                lookback=0,
            )


class TestNewComparisonEnums:
    """Test the new comparison operators are in the enum."""

    def test_was_above_in_enum(self):
        """Comparison enum should have WAS_ABOVE."""
        assert Comparison.WAS_ABOVE.value == "was_above"

    def test_was_below_in_enum(self):
        """Comparison enum should have WAS_BELOW."""
        assert Comparison.WAS_BELOW.value == "was_below"

    def test_crossed_above_within_in_enum(self):
        """Comparison enum should have CROSSED_ABOVE_WITHIN."""
        assert Comparison.CROSSED_ABOVE_WITHIN.value == "crossed_above_within"

    def test_crossed_below_within_in_enum(self):
        """Comparison enum should have CROSSED_BELOW_WITHIN."""
        assert Comparison.CROSSED_BELOW_WITHIN.value == "crossed_below_within"
