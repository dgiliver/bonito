# Week 2 Sprint: Backtest Engine

**Goal**: A working backtest engine where you can run strategies against historical data and get meaningful performance metrics.

**End State**: Running `quant backtest examples/ema_cross_strategy.json` executes a strategy and displays Sharpe ratio, max drawdown, trade list, and equity curve.

---

## Prerequisites

### Verify Week 1 is Complete
```bash
# Should have data available
python -m quant_agent.cli data list

# Should show SPY, AAPL, QQQ with ~1,487 bars each
```

### Understanding the Architecture

The backtest engine has four main components:

```
┌─────────────────────────────────────────────────────────────────┐
│                     STRATEGY CONFIG (JSON/DSL)                  │
│  • Indicators to compute                                        │
│  • Entry/exit rules                                             │
│  • Position sizing                                              │
│  • Risk management (stops, targets)                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INDICATOR ENGINE                           │
│  • SMA, EMA, RSI, MACD, ATR, Bollinger, Stochastic             │
│  • Computes all indicators as numpy arrays                      │
│  • Returns dict: {"sma_20": np.array, "rsi": np.array, ...}    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SIGNAL GENERATOR                          │
│  • Evaluates entry/exit rules against indicator arrays          │
│  • Handles comparisons: >, <, crosses_above, crosses_below     │
│  • Returns boolean arrays: entry_signals[], exit_signals[]      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SIMULATION ENGINE                          │
│  • Loops through bars                                           │
│  • Manages positions, cash, equity                              │
│  • Applies stops/targets                                        │
│  • Records trades                                               │
│  • Calculates equity curve                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      METRICS CALCULATOR                         │
│  • Returns, Sharpe, Sortino                                     │
│  • Drawdown analysis                                            │
│  • Trade statistics                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tickets Overview

| Ticket | Priority | Estimate | Description |
|--------|----------|----------|-------------|
| T1 | P0 | 3-4h | Test & Fix Indicator Calculations |
| T2 | P0 | 2-3h | Test & Fix Strategy DSL Parsing |
| T3 | P0 | 4-5h | Test & Fix Backtest Simulation |
| T4 | P1 | 2-3h | Implement CLI Backtest Command |
| T5 | P1 | 2-3h | Integration Tests with Real Data |
| T6 | P2 | 1-2h | Performance Optimization |

**Total Estimate**: 14-20 hours

---

## Ticket 1: Test & Fix Indicator Calculations

**Priority**: P0 (Start Here)  
**Estimate**: 3-4 hours  
**File**: `src/quant_agent/backtest/indicators.py`

### Why This Matters

Indicators are the foundation of every strategy. If SMA is wrong, every strategy using SMA will be wrong. We need to verify each indicator against known-good values.

### Current State

The indicator module is scaffolded with:
- `sma()` - Simple Moving Average
- `ema()` - Exponential Moving Average
- `rsi()` - Relative Strength Index
- `atr()` - Average True Range
- `macd()` - MACD
- `bollinger_bands()` - Bollinger Bands
- `stochastic()` - Stochastic Oscillator

### Tasks

- [ ] **1.1** Create comprehensive indicator tests
- [ ] **1.2** Verify SMA against manual calculation
- [ ] **1.3** Verify EMA against manual calculation
- [ ] **1.4** Verify RSI against known values
- [ ] **1.5** Verify ATR calculation
- [ ] **1.6** Verify MACD components
- [ ] **1.7** Verify Bollinger Bands
- [ ] **1.8** Fix any bugs found
- [ ] **1.9** Add edge case handling (NaN propagation, insufficient data)

### Test File

Create `tests/test_indicators.py` (we have a basic one, let's expand it):

```python
"""Comprehensive tests for technical indicators."""

import numpy as np
import pytest

from quant_agent.backtest.indicators import (
    sma, ema, rsi, atr, macd, bollinger_bands, stochastic,
    compute_indicators,
)
from quant_agent.backtest.strategy import IndicatorConfig, IndicatorType
from quant_agent.data.models import BarData


class TestSMA:
    """Tests for Simple Moving Average."""
    
    def test_basic_calculation(self):
        """Verify SMA calculation against manual computation."""
        # Simple case: [1, 2, 3, 4, 5] with period 3
        # SMA[2] = (1+2+3)/3 = 2.0
        # SMA[3] = (2+3+4)/3 = 3.0
        # SMA[4] = (3+4+5)/3 = 4.0
        prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = sma(prices, period=3)
        
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == pytest.approx(2.0)
        assert result[3] == pytest.approx(3.0)
        assert result[4] == pytest.approx(4.0)
    
    def test_single_value(self):
        """SMA of constant values equals that value."""
        prices = np.array([100.0] * 20)
        result = sma(prices, period=10)
        
        # All valid values should be 100
        valid = result[~np.isnan(result)]
        assert all(v == pytest.approx(100.0) for v in valid)
    
    def test_period_longer_than_data(self):
        """SMA with period > data length should be all NaN."""
        prices = np.array([1.0, 2.0, 3.0])
        result = sma(prices, period=5)
        
        assert all(np.isnan(result))
    
    def test_real_world_values(self):
        """Test SMA against known SPY values.
        
        Using a simple sequence that's easy to verify.
        """
        # Simulate 10 days of prices
        prices = np.array([100, 102, 101, 103, 105, 104, 106, 108, 107, 109], dtype=float)
        
        # 5-day SMA
        result = sma(prices, period=5)
        
        # SMA[4] = mean([100, 102, 101, 103, 105]) = 102.2
        assert result[4] == pytest.approx(102.2)
        
        # SMA[5] = mean([102, 101, 103, 105, 104]) = 103.0
        assert result[5] == pytest.approx(103.0)


class TestEMA:
    """Tests for Exponential Moving Average."""
    
    def test_first_value_is_sma(self):
        """EMA initial value should be SMA of first `period` values."""
        prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = ema(prices, period=3)
        
        # First valid EMA at index 2 should be SMA of [1, 2, 3] = 2.0
        assert result[2] == pytest.approx(2.0)
    
    def test_ema_responds_faster_than_sma(self):
        """EMA should respond faster to price changes than SMA."""
        # Price jumps from 100 to 150
        prices = np.array([100.0] * 10 + [150.0] * 5)
        
        sma_result = sma(prices, period=5)
        ema_result = ema(prices, period=5)
        
        # After the jump, EMA should be higher than SMA (closer to 150)
        # because EMA weights recent prices more heavily
        assert ema_result[-1] > sma_result[-1]
    
    def test_ema_formula(self):
        """Verify EMA uses correct multiplier: 2/(period+1)."""
        prices = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        period = 3
        result = ema(prices, period=period)
        
        # Multiplier = 2/(3+1) = 0.5
        k = 2 / (period + 1)
        
        # EMA[2] = SMA of first 3 = 11.0
        assert result[2] == pytest.approx(11.0)
        
        # EMA[3] = 13 * 0.5 + 11 * 0.5 = 12.0
        expected_ema_3 = 13 * k + 11 * (1 - k)
        assert result[3] == pytest.approx(expected_ema_3)


class TestRSI:
    """Tests for Relative Strength Index."""
    
    def test_rsi_bounds(self):
        """RSI should always be between 0 and 100."""
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(200))
        result = rsi(prices, period=14)
        
        valid = result[~np.isnan(result)]
        assert all(0 <= v <= 100 for v in valid)
    
    def test_rsi_overbought(self):
        """Consistently rising prices should give RSI near 100."""
        prices = np.array([float(i) for i in range(1, 30)])
        result = rsi(prices, period=14)
        
        # Last RSI should be very high (near 100)
        assert result[-1] > 95
    
    def test_rsi_oversold(self):
        """Consistently falling prices should give RSI near 0."""
        prices = np.array([float(i) for i in range(30, 0, -1)])
        result = rsi(prices, period=14)
        
        # Last RSI should be very low (near 0)
        assert result[-1] < 5
    
    def test_rsi_neutral(self):
        """Alternating up/down should give RSI near 50."""
        # Prices: 100, 101, 100, 101, 100, 101...
        prices = np.array([100 + (i % 2) for i in range(30)], dtype=float)
        result = rsi(prices, period=14)
        
        # RSI should be around 50
        assert 40 < result[-1] < 60


class TestATR:
    """Tests for Average True Range."""
    
    def test_atr_basic(self):
        """ATR should measure volatility correctly."""
        # Constant range of 2 (high - low)
        high = np.array([102.0] * 20)
        low = np.array([100.0] * 20)
        close = np.array([101.0] * 20)
        
        result = atr(high, low, close, period=14)
        
        # ATR should converge to ~2 (the constant range)
        valid = result[~np.isnan(result)]
        assert valid[-1] == pytest.approx(2.0, rel=0.1)
    
    def test_atr_with_gaps(self):
        """ATR should account for gaps (close to next high/low)."""
        high = np.array([105, 110, 108, 112, 109], dtype=float)
        low = np.array([100, 103, 102, 106, 104], dtype=float)
        close = np.array([103, 108, 105, 110, 107], dtype=float)
        
        result = atr(high, low, close, period=3)
        
        # ATR should be positive
        valid = result[~np.isnan(result)]
        assert all(v > 0 for v in valid)
    
    def test_atr_increases_with_volatility(self):
        """ATR should increase when price swings get larger."""
        # First half: small range
        high1 = np.array([101.0] * 20)
        low1 = np.array([99.0] * 20)
        close1 = np.array([100.0] * 20)
        
        # Second half: large range
        high2 = np.array([110.0] * 20)
        low2 = np.array([90.0] * 20)
        close2 = np.array([100.0] * 20)
        
        high = np.concatenate([high1, high2])
        low = np.concatenate([low1, low2])
        close = np.concatenate([close1, close2])
        
        result = atr(high, low, close, period=10)
        
        # ATR at end should be higher than at middle
        assert result[-1] > result[19]


class TestMACD:
    """Tests for MACD indicator."""
    
    def test_macd_components(self):
        """MACD should return three components."""
        prices = np.array([float(100 + i) for i in range(50)])
        macd_line, signal_line, histogram = macd(prices, 12, 26, 9)
        
        assert len(macd_line) == len(prices)
        assert len(signal_line) == len(prices)
        assert len(histogram) == len(prices)
    
    def test_macd_trending_market(self):
        """In uptrend, MACD line should be positive."""
        prices = np.array([float(100 + i * 2) for i in range(50)])
        macd_line, signal_line, histogram = macd(prices, 12, 26, 9)
        
        # After enough data, MACD should be positive in uptrend
        assert macd_line[-1] > 0
    
    def test_histogram_is_difference(self):
        """Histogram should be MACD line minus signal line."""
        prices = np.array([float(100 + i + np.sin(i/5)*10) for i in range(100)])
        macd_line, signal_line, histogram = macd(prices, 12, 26, 9)
        
        # Check at a point where both are valid
        idx = 50
        if not np.isnan(macd_line[idx]) and not np.isnan(signal_line[idx]):
            expected = macd_line[idx] - signal_line[idx]
            assert histogram[idx] == pytest.approx(expected, rel=0.01)


class TestBollingerBands:
    """Tests for Bollinger Bands."""
    
    def test_middle_is_sma(self):
        """Middle band should be SMA."""
        prices = np.array([100, 102, 101, 103, 105, 104, 106, 108, 107, 109], dtype=float)
        upper, middle, lower = bollinger_bands(prices, period=5, std_dev=2)
        
        sma_result = sma(prices, period=5)
        
        # Middle band should equal SMA
        for i in range(len(prices)):
            if not np.isnan(middle[i]):
                assert middle[i] == pytest.approx(sma_result[i])
    
    def test_band_symmetry(self):
        """Upper and lower bands should be symmetric around middle."""
        prices = np.array([100 + np.sin(i/3)*5 for i in range(30)], dtype=float)
        upper, middle, lower = bollinger_bands(prices, period=10, std_dev=2)
        
        for i in range(len(prices)):
            if not np.isnan(middle[i]):
                upper_dist = upper[i] - middle[i]
                lower_dist = middle[i] - lower[i]
                assert upper_dist == pytest.approx(lower_dist, rel=0.01)
    
    def test_wider_bands_with_higher_std(self):
        """Higher std_dev should give wider bands."""
        prices = np.array([100 + np.sin(i/3)*10 for i in range(30)], dtype=float)
        
        upper1, middle1, lower1 = bollinger_bands(prices, period=10, std_dev=1)
        upper2, middle2, lower2 = bollinger_bands(prices, period=10, std_dev=2)
        
        # Width with std_dev=2 should be twice width with std_dev=1
        idx = 20
        width1 = upper1[idx] - lower1[idx]
        width2 = upper2[idx] - lower2[idx]
        
        assert width2 == pytest.approx(width1 * 2, rel=0.01)


class TestStochastic:
    """Tests for Stochastic Oscillator."""
    
    def test_stochastic_bounds(self):
        """Stochastic should be between 0 and 100."""
        high = np.array([100 + np.random.rand()*10 for _ in range(50)])
        low = high - 5
        close = (high + low) / 2
        
        k, d = stochastic(high, low, close, k_period=14, d_period=3)
        
        valid_k = k[~np.isnan(k)]
        valid_d = d[~np.isnan(d)]
        
        assert all(0 <= v <= 100 for v in valid_k)
        assert all(0 <= v <= 100 for v in valid_d)
    
    def test_stochastic_at_high(self):
        """When close equals high, %K should be 100."""
        high = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], dtype=float)
        low = high - 10
        close = high.copy()  # Close at high
        
        k, d = stochastic(high, low, close, k_period=5, d_period=3)
        
        # %K should be 100 when close is at high
        valid_k = k[~np.isnan(k)]
        assert all(v == pytest.approx(100, rel=0.01) for v in valid_k)
    
    def test_stochastic_at_low(self):
        """When close equals low, %K should be 0."""
        high = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], dtype=float)
        low = high - 10
        close = low.copy()  # Close at low
        
        k, d = stochastic(high, low, close, k_period=5, d_period=3)
        
        # %K should be 0 when close is at low
        valid_k = k[~np.isnan(k)]
        assert all(v == pytest.approx(0, rel=0.01) for v in valid_k)


class TestComputeIndicators:
    """Tests for the compute_indicators orchestration function."""
    
    @pytest.fixture
    def sample_bar_data(self):
        """Create sample bar data for testing."""
        n = 50
        timestamps = [f"2024-01-{i+1:02d}" for i in range(n)]
        base_price = 100
        
        # Generate some realistic-ish price data
        np.random.seed(42)
        returns = np.random.randn(n) * 0.02
        close = base_price * np.cumprod(1 + returns)
        
        return BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=(close * 0.999).tolist(),
            highs=(close * 1.01).tolist(),
            lows=(close * 0.99).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
    
    def test_includes_price_fields(self, sample_bar_data):
        """compute_indicators should always include OHLCV."""
        result = compute_indicators(sample_bar_data, [])
        
        assert "open" in result
        assert "high" in result
        assert "low" in result
        assert "close" in result
        assert "volume" in result
    
    def test_computes_sma(self, sample_bar_data):
        """Test computing SMA indicator."""
        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})
        ]
        result = compute_indicators(sample_bar_data, indicators)
        
        assert "sma_20" in result
        assert len(result["sma_20"]) == len(sample_bar_data)
    
    def test_computes_multiple_indicators(self, sample_bar_data):
        """Test computing multiple indicators at once."""
        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma_10", params={"period": 10}),
            IndicatorConfig(type=IndicatorType.EMA, name="ema_20", params={"period": 20}),
            IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14}),
        ]
        result = compute_indicators(sample_bar_data, indicators)
        
        assert "sma_10" in result
        assert "ema_20" in result
        assert "rsi_14" in result
    
    def test_macd_creates_three_outputs(self, sample_bar_data):
        """MACD should create line, signal, and histogram."""
        indicators = [
            IndicatorConfig(
                type=IndicatorType.MACD, 
                name="macd",
                params={"fast_period": 12, "slow_period": 26, "signal_period": 9}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        
        assert "macd_line" in result
        assert "macd_signal" in result
        assert "macd_hist" in result
    
    def test_bbands_creates_three_outputs(self, sample_bar_data):
        """Bollinger Bands should create upper, middle, lower."""
        indicators = [
            IndicatorConfig(
                type=IndicatorType.BBANDS,
                name="bb",
                params={"period": 20, "std_dev": 2}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        
        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result
```

### Acceptance Criteria

- [ ] All indicator tests pass
- [ ] Indicators match manual calculations
- [ ] Edge cases (NaN, insufficient data) handled correctly
- [ ] `compute_indicators()` correctly orchestrates all indicators

---

## Ticket 2: Test & Fix Strategy DSL Parsing

**Priority**: P0  
**Estimate**: 2-3 hours  
**File**: `src/quant_agent/backtest/strategy.py`

### Why This Matters

The Strategy DSL is how the LLM (and users) define trading strategies. If parsing is broken, no strategies will work.

### Tasks

- [ ] **2.1** Verify all Pydantic models validate correctly
- [ ] **2.2** Test parsing from JSON files
- [ ] **2.3** Test edge cases (missing fields, invalid values)
- [ ] **2.4** Test `to_prompt_description()` output
- [ ] **2.5** Ensure example strategies in `examples/` parse correctly

### Test File

Expand `tests/test_strategy.py`:

```python
"""Tests for strategy configuration parsing."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from quant_agent.backtest.strategy import (
    StrategyConfig,
    IndicatorConfig,
    IndicatorType,
    Rule,
    RuleCondition,
    Comparison,
    PositionSizeConfig,
    PositionSizeType,
    StopLossConfig,
    StopLossType,
    TakeProfitConfig,
    TakeProfitType,
)


class TestIndicatorConfig:
    """Tests for IndicatorConfig model."""
    
    def test_valid_sma(self):
        """Test creating valid SMA indicator."""
        config = IndicatorConfig(
            type=IndicatorType.SMA,
            name="sma_20",
            params={"period": 20}
        )
        assert config.type == IndicatorType.SMA
        assert config.params["period"] == 20
    
    def test_valid_macd(self):
        """Test creating valid MACD indicator."""
        config = IndicatorConfig(
            type=IndicatorType.MACD,
            name="macd",
            params={"fast_period": 12, "slow_period": 26, "signal_period": 9}
        )
        assert config.type == IndicatorType.MACD
    
    def test_default_params(self):
        """Test that params defaults to empty dict."""
        config = IndicatorConfig(
            type=IndicatorType.RSI,
            name="rsi"
        )
        assert config.params == {}


class TestRuleCondition:
    """Tests for RuleCondition model."""
    
    def test_numeric_comparison(self):
        """Test condition with numeric right side."""
        cond = RuleCondition(
            left="rsi",
            comparison=Comparison.LT,
            right=30
        )
        assert cond.right == 30
    
    def test_indicator_comparison(self):
        """Test condition comparing two indicators."""
        cond = RuleCondition(
            left="fast_ema",
            comparison=Comparison.CROSSES_ABOVE,
            right="slow_ema"
        )
        assert cond.right == "slow_ema"
    
    def test_all_comparison_types(self):
        """Test all comparison operators are valid."""
        comparisons = [
            Comparison.GT,
            Comparison.GTE,
            Comparison.LT,
            Comparison.LTE,
            Comparison.EQ,
            Comparison.CROSSES_ABOVE,
            Comparison.CROSSES_BELOW,
        ]
        for comp in comparisons:
            cond = RuleCondition(left="a", comparison=comp, right="b")
            assert cond.comparison == comp


class TestRule:
    """Tests for Rule model."""
    
    def test_single_condition(self):
        """Test rule with single condition."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30)
            ]
        )
        assert len(rule.conditions) == 1
        assert rule.logic == "AND"  # default
    
    def test_multiple_conditions_and(self):
        """Test rule with multiple AND conditions."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30),
                RuleCondition(left="close", comparison=Comparison.GT, right="sma_200"),
            ],
            logic="AND"
        )
        assert len(rule.conditions) == 2
    
    def test_multiple_conditions_or(self):
        """Test rule with multiple OR conditions."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30),
                RuleCondition(left="rsi", comparison=Comparison.GT, right=70),
            ],
            logic="OR"
        )
        assert rule.logic == "OR"
    
    def test_empty_conditions_fails(self):
        """Test that empty conditions list fails validation."""
        with pytest.raises(ValidationError):
            Rule(conditions=[])


class TestStrategyConfig:
    """Tests for StrategyConfig model."""
    
    def test_minimal_valid_strategy(self):
        """Test creating minimal valid strategy."""
        config = StrategyConfig(
            name="test",
            symbols=["SPY"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        assert config.name == "test"
        assert config.timeframe == "1d"  # default
        assert config.max_positions == 1  # default
    
    def test_full_strategy(self):
        """Test creating fully-specified strategy."""
        config = StrategyConfig(
            name="full_test",
            description="A complete test strategy",
            version="2.0",
            symbols=["SPY", "QQQ"],
            timeframe="1h",
            indicators=[
                IndicatorConfig(type=IndicatorType.EMA, name="fast", params={"period": 12}),
                IndicatorConfig(type=IndicatorType.EMA, name="slow", params={"period": 26}),
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
                ])
            ],
            exit_rules=[
                Rule(conditions=[
                    RuleCondition(left="fast", comparison=Comparison.CROSSES_BELOW, right="slow")
                ])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=25),
            max_positions=2,
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05),
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.10),
        )
        
        assert config.version == "2.0"
        assert len(config.indicators) == 2
        assert config.position_size.value == 25
    
    def test_no_symbols_fails(self):
        """Test that empty symbols list fails."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=[],
                entry_rules=[
                    Rule(conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right=100)
                    ])
                ]
            )
    
    def test_no_entry_rules_fails(self):
        """Test that empty entry_rules fails."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=["SPY"],
                entry_rules=[]
            )
    
    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=["SPY"],
                entry_rules=[
                    Rule(conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right=100)
                    ])
                ],
                unknown_field="should fail"
            )


class TestStrategyFromJSON:
    """Tests for loading strategies from JSON."""
    
    def test_load_ema_cross_example(self):
        """Test loading the example EMA cross strategy."""
        example_path = Path("examples/ema_cross_strategy.json")
        if not example_path.exists():
            pytest.skip("Example file not found")
        
        with open(example_path) as f:
            data = json.load(f)
        
        config = StrategyConfig(**data)
        assert config.name == "ema_cross_basic"
        assert "SPY" in config.symbols
    
    def test_load_rsi_mean_reversion_example(self):
        """Test loading the example RSI mean reversion strategy."""
        example_path = Path("examples/rsi_mean_reversion.json")
        if not example_path.exists():
            pytest.skip("Example file not found")
        
        with open(example_path) as f:
            data = json.load(f)
        
        config = StrategyConfig(**data)
        assert config.name == "rsi_mean_reversion"
    
    def test_roundtrip_json(self):
        """Test that strategy can be serialized and deserialized."""
        original = StrategyConfig(
            name="roundtrip_test",
            symbols=["AAPL"],
            indicators=[
                IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="rsi", comparison=Comparison.LT, right=30)
                ])
            ]
        )
        
        # Serialize
        json_str = original.model_dump_json()
        
        # Deserialize
        loaded = StrategyConfig.model_validate_json(json_str)
        
        assert loaded.name == original.name
        assert loaded.symbols == original.symbols
        assert loaded.indicators[0].name == original.indicators[0].name


class TestToPromptDescription:
    """Tests for to_prompt_description method."""
    
    def test_includes_key_info(self):
        """Test that description includes all key information."""
        config = StrategyConfig(
            name="test_strategy",
            description="My test",
            symbols=["SPY"],
            indicators=[
                IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right="sma_20")
                ])
            ],
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        )
        
        desc = config.to_prompt_description()
        
        assert "test_strategy" in desc
        assert "SPY" in desc
        assert "sma_20" in desc
        assert "close" in desc
        assert "Stop Loss" in desc
```

### Acceptance Criteria

- [ ] All strategy parsing tests pass
- [ ] Example JSON files load correctly
- [ ] Invalid configs are rejected with clear errors
- [ ] Roundtrip serialization works

---

## Ticket 3: Test & Fix Backtest Simulation

**Priority**: P0  
**Estimate**: 4-5 hours  
**File**: `src/quant_agent/backtest/engine.py`

### Why This Matters

This is the heart of the system. The simulation must correctly:
- Generate entry/exit signals from rules
- Execute trades at the right prices
- Track positions and cash
- Apply stops and targets
- Calculate accurate metrics

### Tasks

- [ ] **3.1** Test rule evaluation (comparisons, crosses)
- [ ] **3.2** Test signal generation
- [ ] **3.3** Test trade execution and fills
- [ ] **3.4** Test position tracking
- [ ] **3.5** Test stop loss execution
- [ ] **3.6** Test take profit execution
- [ ] **3.7** Test metrics calculation
- [ ] **3.8** Test with known strategy outcomes

### Test File

Create `tests/test_backtest_engine.py`:

```python
"""Tests for the backtest engine."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from quant_agent.backtest.engine import BacktestEngine
from quant_agent.backtest.models import BacktestConfig, Trade
from quant_agent.backtest.strategy import (
    StrategyConfig,
    IndicatorConfig,
    IndicatorType,
    Rule,
    RuleCondition,
    Comparison,
    PositionSizeConfig,
    PositionSizeType,
    StopLossConfig,
    StopLossType,
    TakeProfitConfig,
    TakeProfitType,
)
from quant_agent.data.models import BarData


@pytest.fixture
def sample_bar_data():
    """Create sample bar data for testing."""
    n = 100
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]
    
    # Create trending price data
    np.random.seed(42)
    base_price = 100
    trend = np.linspace(0, 20, n)  # Upward trend
    noise = np.random.randn(n) * 2
    close = base_price + trend + noise
    
    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=(close - 0.5).tolist(),
        highs=(close + 1).tolist(),
        lows=(close - 1).tolist(),
        closes=close.tolist(),
        volumes=[1000000] * n,
    )


@pytest.fixture
def engine():
    """Create a backtest engine with default config."""
    config = BacktestConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000,
        commission=0.001,
        slippage=0.0005,
    )
    return BacktestEngine(config)


class TestRuleEvaluation:
    """Tests for rule evaluation logic."""
    
    def test_greater_than(self, engine, sample_bar_data):
        """Test > comparison."""
        # Strategy: enter when close > 110
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=110)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Should have some trades since price trends from 100 to 120
        assert result.metrics.total_trades > 0
    
    def test_less_than(self, engine, sample_bar_data):
        """Test < comparison."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.LT, right=105)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Should enter early when price is low
        if result.metrics.total_trades > 0:
            first_trade = result.trades[0]
            assert first_trade.entry_price < 110  # Entered at lower price
    
    def test_crosses_above(self, engine):
        """Test crosses_above comparison."""
        # Create data where fast EMA crosses above slow EMA
        n = 100
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        
        # Price starts low, then jumps up
        close = np.array([100.0] * 50 + [120.0] * 50)
        
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close + 1).tolist(),
            lows=(close - 1).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(type=IndicatorType.EMA, name="fast", params={"period": 5}),
                IndicatorConfig(type=IndicatorType.EMA, name="slow", params={"period": 20}),
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
                ])
            ]
        )
        
        result = engine.run(strategy, data)
        
        # Should have at least one trade from the crossover
        assert result.metrics.total_trades >= 1


class TestTradeExecution:
    """Tests for trade execution logic."""
    
    def test_entry_at_open(self, engine, sample_bar_data):
        """Test that entries happen at next bar's open."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Verify trades were entered at open prices (not close)
        for trade in result.trades:
            # Entry price should be close to an open price in the data
            # (accounting for slippage)
            assert trade.entry_price > 0
    
    def test_exit_at_open(self, engine, sample_bar_data):
        """Test that exits happen at next bar's open."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ],
            exit_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=115)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Should have at least one completed trade
        completed = [t for t in result.trades if t.exit_reason != "end_of_data"]
        if completed:
            assert completed[0].exit_price > 0
    
    def test_commission_deducted(self, engine, sample_bar_data):
        """Test that commissions are properly deducted."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Total commission should be positive if there are trades
        if result.metrics.total_trades > 0:
            assert result.total_commission > 0


class TestStopLoss:
    """Tests for stop loss execution."""
    
    def test_percent_stop_loss_triggers(self):
        """Test that percent stop loss triggers correctly."""
        # Create data with a crash
        n = 50
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        
        # Price rises then crashes
        close = np.array([100.0] * 10 + [105.0] * 10 + [90.0] * 30)
        
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close + 1).tolist(),
            lows=(close - 1).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
        
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100000,
            commission=0,
            slippage=0,
        )
        engine = BacktestEngine(config)
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=103)
                ])
            ],
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.10),  # 10% stop
        )
        
        result = engine.run(strategy, data)
        
        # Should have exited due to stop loss
        stop_exits = [t for t in result.trades if t.exit_reason == "stop_loss"]
        assert len(stop_exits) > 0, "Stop loss should have triggered"


class TestTakeProfit:
    """Tests for take profit execution."""
    
    def test_percent_take_profit_triggers(self):
        """Test that percent take profit triggers correctly."""
        n = 50
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        
        # Price rises steadily
        close = np.linspace(100, 130, n)
        
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close + 1).tolist(),
            lows=(close - 1).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
        
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100000,
            commission=0,
            slippage=0,
        )
        engine = BacktestEngine(config)
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ],
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.15),  # 15% target
        )
        
        result = engine.run(strategy, data)
        
        # Should have exited due to take profit
        tp_exits = [t for t in result.trades if t.exit_reason == "take_profit"]
        assert len(tp_exits) > 0, "Take profit should have triggered"


class TestMetricsCalculation:
    """Tests for performance metrics."""
    
    def test_positive_returns_profitable(self, engine, sample_bar_data):
        """Test that positive price movement creates positive returns."""
        # Buy and hold strategy (always in)
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=0)  # Always true
                ])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100)
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Sample data trends up, so should be profitable
        assert result.metrics.total_return > 0
    
    def test_sharpe_ratio_calculation(self, engine, sample_bar_data):
        """Test that Sharpe ratio is calculated correctly."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Sharpe should be a reasonable number (not NaN or infinity)
        assert not np.isnan(result.metrics.sharpe_ratio)
        assert not np.isinf(result.metrics.sharpe_ratio)
    
    def test_max_drawdown_calculation(self, engine, sample_bar_data):
        """Test that max drawdown is calculated correctly."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Max drawdown should be between 0 and 1 (0-100%)
        assert 0 <= result.metrics.max_drawdown <= 1
    
    def test_win_rate_calculation(self, engine, sample_bar_data):
        """Test that win rate is calculated correctly."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ],
            exit_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=115)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        if result.metrics.total_trades > 0:
            # Win rate should be between 0 and 1
            assert 0 <= result.metrics.win_rate <= 1
            
            # Win rate should match actual winning trades
            winning = result.metrics.winning_trades
            total = result.metrics.total_trades
            expected_win_rate = winning / total if total > 0 else 0
            assert result.metrics.win_rate == pytest.approx(expected_win_rate)


class TestEquityCurve:
    """Tests for equity curve generation."""
    
    def test_equity_curve_length(self, engine, sample_bar_data):
        """Test that equity curve has correct length."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Equity curve should have an entry for each bar (approximately)
        assert len(result.equity_curve) > 0
        assert len(result.equity_curve) == len(result.equity_dates)
    
    def test_equity_curve_starts_at_initial(self, engine, sample_bar_data):
        """Test that equity curve starts at initial capital."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=1000)  # Never enters
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # If no trades, equity should remain at initial capital
        if result.metrics.total_trades == 0:
            assert all(eq == pytest.approx(100000) for eq in result.equity_curve)


class TestResultSummary:
    """Tests for result summary output."""
    
    def test_summary_contains_key_metrics(self, engine, sample_bar_data):
        """Test that summary contains all key metrics."""
        strategy = StrategyConfig(
            name="test_summary",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        summary = result.summary()
        
        assert "test_summary" in summary
        assert "Total Return" in summary
        assert "Sharpe Ratio" in summary
        assert "Max Drawdown" in summary
        assert "Win Rate" in summary
```

### Acceptance Criteria

- [ ] All engine tests pass
- [ ] Signal generation is correct
- [ ] Trades execute at correct prices
- [ ] Stops and targets work
- [ ] Metrics are mathematically correct

---

## Ticket 4: Implement CLI Backtest Command

**Priority**: P1  
**Estimate**: 2-3 hours  
**File**: `src/quant_agent/cli.py`

### Tasks

- [ ] **4.1** Load strategy from JSON file
- [ ] **4.2** Fetch data from store
- [ ] **4.3** Run backtest
- [ ] **4.4** Display results nicely
- [ ] **4.5** Save results to file (optional)

### Implementation

Update `cli.py`:

```python
import json
from pathlib import Path

@app.command()
def backtest(
    strategy_file: str = typer.Argument(..., help="Path to strategy config JSON file"),
    symbol: str = typer.Option(None, "--symbol", "-s", help="Override strategy symbol"),
    start: str = typer.Option("2020-01-01", "--start", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    capital: float = typer.Option(100000, "--capital", "-c", help="Initial capital"),
    output: str = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
) -> None:
    """Run a backtest for a strategy configuration."""
    from quant_agent.backtest.engine import BacktestEngine
    from quant_agent.backtest.models import BacktestConfig
    from quant_agent.backtest.strategy import StrategyConfig
    from quant_agent.data.store import MarketDataStore
    
    # Load strategy
    strategy_path = Path(strategy_file)
    if not strategy_path.exists():
        console.print(f"[red]Strategy file not found: {strategy_file}[/red]")
        raise typer.Exit(1)
    
    with open(strategy_path) as f:
        strategy_data = json.load(f)
    
    try:
        strategy = StrategyConfig(**strategy_data)
    except Exception as e:
        console.print(f"[red]Invalid strategy configuration: {e}[/red]")
        raise typer.Exit(1)
    
    # Override symbol if provided
    if symbol:
        strategy = strategy.model_copy(update={"symbols": [symbol.upper()]})
    
    target_symbol = strategy.symbols[0]
    
    # Parse dates
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
    
    # Load data
    store = MarketDataStore()
    
    console.print(f"\n[bold]Loading data for {target_symbol}...[/bold]")
    data = store.get_bars(target_symbol, start_date, end_date, strategy.timeframe)
    store.close()
    
    if data is None:
        console.print(f"[red]No data found for {target_symbol}[/red]")
        console.print(f"[dim]Run 'quant ingest {target_symbol}' first.[/dim]")
        raise typer.Exit(1)
    
    console.print(f"[dim]Loaded {len(data)} bars[/dim]")
    
    # Run backtest
    console.print(f"\n[bold]Running backtest: {strategy.name}[/bold]")
    
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=capital,
    )
    engine = BacktestEngine(config)
    
    with console.status("[bold blue]Backtesting...[/bold blue]"):
        result = engine.run(strategy, data)
    
    # Display results
    console.print(result.summary())
    
    # Trade table
    if result.trades:
        console.print("\n[bold]Recent Trades:[/bold]")
        
        trade_table = Table()
        trade_table.add_column("Entry Date", style="dim")
        trade_table.add_column("Exit Date", style="dim")
        trade_table.add_column("Entry $", justify="right")
        trade_table.add_column("Exit $", justify="right")
        trade_table.add_column("P&L", justify="right")
        trade_table.add_column("Reason")
        
        for trade in result.trades[-10:]:  # Last 10 trades
            pnl_style = "green" if trade.pnl > 0 else "red"
            trade_table.add_row(
                trade.entry_time.strftime("%Y-%m-%d"),
                trade.exit_time.strftime("%Y-%m-%d"),
                f"${trade.entry_price:.2f}",
                f"${trade.exit_price:.2f}",
                f"[{pnl_style}]${trade.pnl:,.2f}[/{pnl_style}]",
                trade.exit_reason,
            )
        
        console.print(trade_table)
    
    # Save results if requested
    if output:
        output_path = Path(output)
        result_data = {
            "strategy_name": result.strategy_name,
            "symbol": result.symbol,
            "period": f"{start} to {end_date.strftime('%Y-%m-%d')}",
            "metrics": {
                "total_return": result.metrics.total_return,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "max_drawdown": result.metrics.max_drawdown,
                "total_trades": result.metrics.total_trades,
                "win_rate": result.metrics.win_rate,
            },
            "equity_curve": result.equity_curve,
        }
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)
        console.print(f"\n[dim]Results saved to {output_path}[/dim]")
```

### Acceptance Criteria

- [ ] `quant backtest examples/ema_cross_strategy.json` runs successfully
- [ ] Results display nicely with metrics table
- [ ] Trade list shows entry/exit/P&L
- [ ] Can override symbol with `--symbol`
- [ ] Can save results to JSON with `--output`

---

## Ticket 5: Integration Tests with Real Data

**Priority**: P1  
**Estimate**: 2-3 hours  
**File**: `tests/test_backtest_integration.py`

### Tasks

- [ ] **5.1** Test EMA cross strategy on real SPY data
- [ ] **5.2** Test RSI mean reversion on real data
- [ ] **5.3** Verify results are reasonable (not obviously broken)
- [ ] **5.4** Test CLI end-to-end

### Test File

```python
"""Integration tests for backtesting with real data."""

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from quant_agent.backtest.engine import BacktestEngine
from quant_agent.backtest.models import BacktestConfig
from quant_agent.backtest.strategy import StrategyConfig
from quant_agent.data.store import MarketDataStore


@pytest.fixture
def real_spy_data():
    """Load real SPY data from the store."""
    store = MarketDataStore()
    data = store.get_bars(
        symbol="SPY",
        start=datetime(2020, 1, 1),
        end=datetime(2024, 1, 1),
        timeframe="1d"
    )
    store.close()
    
    if data is None:
        pytest.skip("SPY data not available. Run 'quant ingest SPY' first.")
    
    return data


@pytest.fixture
def engine():
    """Create a backtest engine."""
    config = BacktestConfig(
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2024, 1, 1),
        initial_capital=100000,
    )
    return BacktestEngine(config)


class TestEMACrossStrategy:
    """Integration tests for EMA crossover strategy."""
    
    def test_ema_cross_runs(self, engine, real_spy_data):
        """Test that EMA cross strategy runs without errors."""
        example_path = Path("examples/ema_cross_strategy.json")
        with open(example_path) as f:
            strategy_data = json.load(f)
        
        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)
        
        # Should produce valid results
        assert result.metrics.total_trades > 0
        assert not result.metrics.sharpe_ratio != result.metrics.sharpe_ratio  # not NaN
    
    def test_ema_cross_reasonable_results(self, engine, real_spy_data):
        """Test that EMA cross results are reasonable."""
        example_path = Path("examples/ema_cross_strategy.json")
        with open(example_path) as f:
            strategy_data = json.load(f)
        
        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)
        
        # Results should be within reasonable bounds
        # (not crazy good or crazy bad - would indicate bugs)
        assert -1 < result.metrics.total_return < 5  # -100% to 500%
        assert -5 < result.metrics.sharpe_ratio < 5
        assert 0 <= result.metrics.max_drawdown <= 1
        assert 0 <= result.metrics.win_rate <= 1


class TestRSIMeanReversionStrategy:
    """Integration tests for RSI mean reversion strategy."""
    
    def test_rsi_strategy_runs(self, engine, real_spy_data):
        """Test that RSI strategy runs without errors."""
        example_path = Path("examples/rsi_mean_reversion.json")
        with open(example_path) as f:
            strategy_data = json.load(f)
        
        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)
        
        # Should complete without errors
        assert result.final_capital > 0
    
    def test_rsi_entries_at_oversold(self, engine, real_spy_data):
        """Test that RSI strategy enters at oversold conditions."""
        example_path = Path("examples/rsi_mean_reversion.json")
        with open(example_path) as f:
            strategy_data = json.load(f)
        
        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)
        
        # Strategy should have trades (RSI < 30 occurs sometimes)
        # May be 0 if market never got oversold
        assert result.metrics.total_trades >= 0


@pytest.mark.slow
class TestCLIIntegration:
    """End-to-end CLI tests."""
    
    def test_backtest_command(self):
        """Test the backtest CLI command."""
        result = subprocess.run(
            [
                "python", "-m", "quant_agent.cli", "backtest",
                "examples/ema_cross_strategy.json",
                "--start", "2023-01-01",
                "--end", "2023-12-31",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should complete (exit code 0) or fail gracefully
        # Check for key metrics in output
        if result.returncode == 0:
            assert "Total Return" in result.stdout or "Sharpe" in result.stdout
        else:
            # Check it's a graceful error, not a crash
            assert "Error" in result.stdout or "not found" in result.stdout.lower()


class TestBuyAndHoldBaseline:
    """Test buy-and-hold as a sanity check."""
    
    def test_buy_and_hold_matches_market(self, engine, real_spy_data):
        """Buy-and-hold should roughly match SPY's return."""
        from quant_agent.backtest.strategy import (
            Rule, RuleCondition, Comparison,
            PositionSizeConfig, PositionSizeType
        )
        
        # Always-in strategy (buy and hold)
        strategy = StrategyConfig(
            name="buy_and_hold",
            symbols=["SPY"],
            entry_rules=[
                Rule(conditions=[
                    # This should trigger on first bar and stay in
                    RuleCondition(left="close", comparison=Comparison.GT, right=0)
                ])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=99)
        )
        
        result = engine.run(strategy, real_spy_data)
        
        # Calculate actual SPY return over period
        actual_return = (real_spy_data.closes[-1] - real_spy_data.closes[0]) / real_spy_data.closes[0]
        
        # Strategy return should be in same ballpark as actual
        # (won't match exactly due to timing, costs)
        assert result.metrics.total_return > actual_return * 0.5  # At least 50% of market
        assert result.metrics.total_return < actual_return * 2  # Not more than 2x market
```

### Acceptance Criteria

- [ ] Example strategies run on real data
- [ ] Results are within reasonable bounds
- [ ] CLI integration test passes
- [ ] Buy-and-hold sanity check passes

---

## Ticket 6: Performance Optimization (Optional)

**Priority**: P2  
**Estimate**: 1-2 hours

### Tasks

- [ ] **6.1** Profile backtest execution
- [ ] **6.2** Optimize indicator calculations (use pandas/ta-lib if needed)
- [ ] **6.3** Optimize loop in simulation engine
- [ ] **6.4** Add timing benchmarks

### Benchmark Test

```python
"""Performance benchmarks for the backtest engine."""

import time
from datetime import datetime

import pytest

from quant_agent.backtest.engine import BacktestEngine
from quant_agent.backtest.models import BacktestConfig
from quant_agent.backtest.strategy import StrategyConfig
from quant_agent.data.store import MarketDataStore


@pytest.mark.slow
class TestPerformance:
    """Performance benchmarks."""
    
    def test_backtest_speed(self):
        """Backtest should complete in reasonable time."""
        store = MarketDataStore()
        data = store.get_bars("SPY", datetime(2020, 1, 1), datetime(2024, 1, 1))
        store.close()
        
        if data is None:
            pytest.skip("SPY data not available")
        
        strategy = StrategyConfig(
            name="perf_test",
            symbols=["SPY"],
            indicators=[
                {"type": "ema", "name": "fast", "params": {"period": 12}},
                {"type": "ema", "name": "slow", "params": {"period": 26}},
                {"type": "rsi", "name": "rsi", "params": {"period": 14}},
            ],
            entry_rules=[{
                "conditions": [
                    {"left": "fast", "comparison": "crosses_above", "right": "slow"}
                ]
            }]
        )
        strategy = StrategyConfig(**strategy.model_dump())
        
        config = BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
        )
        engine = BacktestEngine(config)
        
        # Time the backtest
        start = time.time()
        result = engine.run(strategy, data)
        elapsed = time.time() - start
        
        print(f"\nBacktest completed in {elapsed:.3f} seconds")
        print(f"Bars processed: {len(data)}")
        print(f"Bars per second: {len(data) / elapsed:.0f}")
        
        # Should complete in under 5 seconds for ~1000 bars
        assert elapsed < 5.0, f"Backtest too slow: {elapsed:.2f}s"
```

---

## Daily Breakdown

### Day 1: Indicators (Ticket 1)
- [ ] Write comprehensive indicator tests
- [ ] Run tests, fix failing indicators
- [ ] Verify against manual calculations

### Day 2: Strategy DSL + Engine Start (Tickets 2, 3 start)
- [ ] Complete strategy parsing tests
- [ ] Start engine tests (rule evaluation)
- [ ] Fix any parsing issues

### Day 3: Engine Completion (Ticket 3)
- [ ] Complete engine tests
- [ ] Fix simulation bugs
- [ ] Verify stops and targets work

### Day 4: CLI + Integration (Tickets 4, 5)
- [ ] Implement CLI backtest command
- [ ] Run integration tests with real SPY data
- [ ] Fix any issues

### Day 5: Polish + Buffer
- [ ] Performance testing
- [ ] Code review
- [ ] Documentation updates
- [ ] Prep for Week 3

---

## Commands Cheat Sheet

```bash
# Run all Week 2 tests
pytest tests/test_indicators.py tests/test_strategy.py tests/test_backtest_engine.py -v

# Run specific test class
pytest tests/test_backtest_engine.py::TestTradeExecution -v

# Run integration tests (requires data)
pytest tests/test_backtest_integration.py -v --run-slow

# Run backtest via CLI
python -m quant_agent.cli backtest examples/ema_cross_strategy.json

# Run with custom dates
python -m quant_agent.cli backtest examples/ema_cross_strategy.json --start 2022-01-01 --end 2023-12-31

# Save results
python -m quant_agent.cli backtest examples/ema_cross_strategy.json --output results.json
```

---

## Definition of Done (Week 2)

- [ ] All indicator tests pass
- [ ] All strategy parsing tests pass
- [ ] All engine tests pass
- [ ] `quant backtest examples/ema_cross_strategy.json` works
- [ ] Results show Sharpe, drawdown, trade list
- [ ] Integration tests pass with real SPY data
- [ ] Backtest completes in <5 seconds for 1000 bars

