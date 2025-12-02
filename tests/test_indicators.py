"""Comprehensive tests for technical indicators."""

import numpy as np
import pytest

from quant_agent.backtest.indicators import (
    atr,
    bollinger_bands,
    compute_indicators,
    ema,
    macd,
    rsi,
    sma,
    stochastic,
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
        """Test SMA against known values."""
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
        # Price jumps from 100 to 150 - check DURING the transition
        prices = np.array([100.0] * 10 + [150.0] * 3)

        sma_result = sma(prices, period=5)
        ema_result = ema(prices, period=5)

        # At the first bar after the jump (index 10), EMA should be higher than SMA
        # because EMA weights recent prices more heavily
        # SMA at index 10 = avg(100,100,100,100,150) = 110
        # EMA at index 10 should be > 110 due to weighting
        idx = 11  # Second bar after jump
        assert (
            ema_result[idx] > sma_result[idx]
        ), f"EMA ({ema_result[idx]:.2f}) should respond faster than SMA ({sma_result[idx]:.2f})"

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
        prices = np.array([float(100 + i + np.sin(i / 5) * 10) for i in range(100)])
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
        prices = np.array([100 + np.sin(i / 3) * 5 for i in range(30)], dtype=float)
        upper, middle, lower = bollinger_bands(prices, period=10, std_dev=2)

        for i in range(len(prices)):
            if not np.isnan(middle[i]):
                upper_dist = upper[i] - middle[i]
                lower_dist = middle[i] - lower[i]
                assert upper_dist == pytest.approx(lower_dist, rel=0.01)

    def test_wider_bands_with_higher_std(self):
        """Higher std_dev should give wider bands."""
        prices = np.array([100 + np.sin(i / 3) * 10 for i in range(30)], dtype=float)

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
        np.random.seed(42)
        high = np.array([100 + np.random.rand() * 10 for _ in range(50)])
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
        """When close equals the lowest low over lookback, %K should be 0."""
        # Create flat data where close is always at the lowest point
        # All highs are 110, all lows are 100, all closes are 100
        high = np.array([110.0] * 20)
        low = np.array([100.0] * 20)
        close = np.array([100.0] * 20)  # Close at the lowest low

        k, d = stochastic(high, low, close, k_period=5, d_period=3)

        # %K should be 0 when close equals lowest low over the period
        valid_k = k[~np.isnan(k)]
        assert all(v == pytest.approx(0, abs=1) for v in valid_k), f"Expected ~0, got {valid_k}"


class TestComputeIndicators:
    """Tests for the compute_indicators orchestration function."""

    @pytest.fixture
    def sample_bar_data(self):
        """Create sample bar data for testing."""
        from datetime import datetime, timedelta

        n = 50
        base_date = datetime(2024, 1, 1)
        timestamps = [base_date + timedelta(days=i) for i in range(n)]
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
        indicators = [IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})]
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
                params={"fast_period": 12, "slow_period": 26, "signal_period": 9},
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
                type=IndicatorType.BBANDS, name="bb", params={"period": 20, "std_dev": 2}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)

        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result
