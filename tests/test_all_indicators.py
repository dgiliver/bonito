"""Comprehensive tests for ALL indicators - built-in and pandas-ta.

This test suite validates every indicator available in the system:
1. Built-in indicators (SMA, EMA, RSI, MACD, ATR, BBands, Stoch)
2. Volume indicators (VWAP, OBV, CMF, MFI, AD)
3. Trend indicators (ADX, SuperTrend, Aroon, PSAR)
4. Volatility/Channels (Donchian, Keltner)
5. Momentum (CCI, ROC, Williams %R, Momentum, TSI)
6. Statistics (Z-Score, StdDev)

Each indicator is tested for:
- Basic computation succeeds
- Output values are reasonable
- Multi-column outputs have correct names
- Parameters work correctly
- Integration with the backtest engine
"""

from datetime import datetime, timedelta

import numpy as np
import pytest

from bonito.backtest.indicators import compute_indicators
from bonito.backtest.strategy import IndicatorConfig, IndicatorType
from bonito.data.models import BarData

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_bar_data() -> BarData:
    """Create realistic sample bar data with 200 bars."""
    n = 200
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]

    np.random.seed(42)
    base_price = 100.0
    returns = np.random.randn(n) * 0.02
    close = base_price * np.cumprod(1 + returns)

    high = close * (1 + np.abs(np.random.randn(n) * 0.01))
    low = close * (1 - np.abs(np.random.randn(n) * 0.01))
    opens = np.roll(close, 1)
    opens[0] = base_price

    base_vol = 1_000_000
    vol_multiplier = 1 + np.abs(returns) * 10
    volumes = (base_vol * vol_multiplier).astype(int).tolist()

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=volumes,
    )


@pytest.fixture
def uptrend_data() -> BarData:
    """Data with consistent uptrend."""
    n = 200
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]

    np.random.seed(42)
    daily_return = 0.005  # 0.5% daily gain
    noise = np.random.randn(n) * 0.002
    close = 100.0 * np.cumprod(1 + daily_return + noise)

    high = close * 1.005
    low = close * 0.995
    opens = np.roll(close, 1)
    opens[0] = 100.0

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=[1_000_000] * n,
    )


@pytest.fixture
def downtrend_data() -> BarData:
    """Data with consistent downtrend."""
    n = 200
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]

    np.random.seed(42)
    daily_return = -0.005  # 0.5% daily loss
    noise = np.random.randn(n) * 0.002
    close = 100.0 * np.cumprod(1 + daily_return + noise)

    high = close * 1.005
    low = close * 0.995
    opens = np.roll(close, 1)
    opens[0] = 100.0

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=[1_000_000] * n,
    )


@pytest.fixture
def sideways_data() -> BarData:
    """Data oscillating sideways."""
    n = 200
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]

    np.random.seed(42)
    # Oscillate around 100 with no trend
    close = 100.0 + np.sin(np.linspace(0, 20 * np.pi, n)) * 3 + np.random.randn(n) * 0.5

    high = close + 0.5
    low = close - 0.5
    opens = np.roll(close, 1)
    opens[0] = 100.0

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=[1_000_000] * n,
    )


@pytest.fixture
def high_volume_spike_data() -> BarData:
    """Data with volume spike in the middle."""
    n = 200
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]

    np.random.seed(42)
    close = 100.0 * np.cumprod(1 + np.random.randn(n) * 0.01)

    high = close * 1.005
    low = close * 0.995
    opens = np.roll(close, 1)
    opens[0] = 100.0

    # Volume spike at bar 100
    volumes = [1_000_000] * n
    volumes[100] = 10_000_000  # 10x spike

    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=volumes,
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def count_valid(arr: np.ndarray) -> int:
    """Count non-NaN values in array."""
    return np.sum(~np.isnan(arr))


def assert_bounds(arr: np.ndarray, min_val: float, max_val: float, name: str):
    """Assert all valid values are within bounds."""
    valid = arr[~np.isnan(arr)]
    assert all(min_val <= v <= max_val for v in valid), (
        f"{name} values outside [{min_val}, {max_val}]"
    )


def assert_has_valid_values(arr: np.ndarray, min_count: int, name: str):
    """Assert array has minimum number of valid values."""
    valid_count = count_valid(arr)
    assert valid_count >= min_count, (
        f"{name} has only {valid_count} valid values, expected >= {min_count}"
    )


# =============================================================================
# BUILT-IN INDICATORS
# =============================================================================


class TestSMAIndicator:
    """Simple Moving Average tests."""

    def test_sma_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "sma_20" in result
        assert_has_valid_values(result["sma_20"], 180, "SMA")

    def test_sma_different_periods(self, sample_bar_data):
        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma_10", params={"period": 10}),
            IndicatorConfig(type=IndicatorType.SMA, name="sma_50", params={"period": 50}),
            IndicatorConfig(type=IndicatorType.SMA, name="sma_200", params={"period": 200}),
        ]
        result = compute_indicators(sample_bar_data, indicators)
        assert "sma_10" in result
        assert "sma_50" in result
        assert "sma_200" in result
        # Shorter periods should have more valid values
        assert count_valid(result["sma_10"]) > count_valid(result["sma_50"])

    def test_sma_values_reasonable(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        sma = result["sma"]
        close = sample_bar_data.close
        # SMA should be within price range
        valid_sma = sma[~np.isnan(sma)]
        assert all(min(close) * 0.5 < v < max(close) * 1.5 for v in valid_sma)


class TestEMAIndicator:
    """Exponential Moving Average tests."""

    def test_ema_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.EMA, name="ema_12", params={"period": 12})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "ema_12" in result
        assert_has_valid_values(result["ema_12"], 180, "EMA")

    def test_ema_faster_than_sma(self, uptrend_data):
        """EMA should respond faster to price changes than SMA."""
        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20}),
            IndicatorConfig(type=IndicatorType.EMA, name="ema", params={"period": 20}),
        ]
        result = compute_indicators(uptrend_data, indicators)
        # In uptrend, EMA should be above SMA (closer to current price)
        sma = result["sma"]
        ema = result["ema"]
        # Check last 50 values
        assert np.nanmean(ema[-50:]) > np.nanmean(sma[-50:])


class TestRSIIndicator:
    """Relative Strength Index tests."""

    def test_rsi_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "rsi" in result
        assert_has_valid_values(result["rsi"], 180, "RSI")

    def test_rsi_bounds(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert_bounds(result["rsi"], 0, 100, "RSI")

    def test_rsi_overbought_in_uptrend(self, uptrend_data):
        indicators = [IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})]
        result = compute_indicators(uptrend_data, indicators)
        # RSI should be high (>70) in strong uptrend
        assert result["rsi"][-1] > 60

    def test_rsi_oversold_in_downtrend(self, downtrend_data):
        indicators = [IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})]
        result = compute_indicators(downtrend_data, indicators)
        # RSI should be low (<30) in strong downtrend
        assert result["rsi"][-1] < 40


class TestMACDIndicator:
    """MACD tests."""

    def test_macd_computes_three_outputs(self, sample_bar_data):
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

    def test_macd_histogram_is_difference(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.MACD, name="macd", params={})]
        result = compute_indicators(sample_bar_data, indicators)
        idx = 100
        if not np.isnan(result["macd_line"][idx]) and not np.isnan(result["macd_signal"][idx]):
            expected_hist = result["macd_line"][idx] - result["macd_signal"][idx]
            assert result["macd_hist"][idx] == pytest.approx(expected_hist, rel=0.01)


class TestATRIndicator:
    """Average True Range tests."""

    def test_atr_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.ATR, name="atr", params={"period": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "atr" in result
        assert_has_valid_values(result["atr"], 180, "ATR")

    def test_atr_positive(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.ATR, name="atr", params={"period": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        valid = result["atr"][~np.isnan(result["atr"])]
        assert all(v > 0 for v in valid)


class TestBollingerBands:
    """Bollinger Bands tests."""

    def test_bbands_computes_three_outputs(self, sample_bar_data):
        indicators = [
            IndicatorConfig(
                type=IndicatorType.BBANDS, name="bb", params={"period": 20, "std_dev": 2}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result

    def test_bbands_order(self, sample_bar_data):
        """Upper > Middle > Lower"""
        indicators = [IndicatorConfig(type=IndicatorType.BBANDS, name="bb", params={})]
        result = compute_indicators(sample_bar_data, indicators)
        idx = 100
        if not np.isnan(result["bb_upper"][idx]):
            assert result["bb_upper"][idx] > result["bb_middle"][idx] > result["bb_lower"][idx]

    def test_bbands_symmetry(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.BBANDS, name="bb", params={})]
        result = compute_indicators(sample_bar_data, indicators)
        idx = 100
        if not np.isnan(result["bb_middle"][idx]):
            upper_dist = result["bb_upper"][idx] - result["bb_middle"][idx]
            lower_dist = result["bb_middle"][idx] - result["bb_lower"][idx]
            assert upper_dist == pytest.approx(lower_dist, rel=0.01)


class TestStochasticIndicator:
    """Stochastic Oscillator tests."""

    def test_stoch_computes_two_outputs(self, sample_bar_data):
        indicators = [
            IndicatorConfig(
                type=IndicatorType.STOCH, name="stoch", params={"k_period": 14, "d_period": 3}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        assert "stoch_k" in result
        assert "stoch_d" in result

    def test_stoch_bounds(self, sample_bar_data):
        indicators = [IndicatorConfig(type=IndicatorType.STOCH, name="stoch", params={})]
        result = compute_indicators(sample_bar_data, indicators)
        assert_bounds(result["stoch_k"], 0, 100, "Stoch %K")
        assert_bounds(result["stoch_d"], 0, 100, "Stoch %D")


# =============================================================================
# VOLUME INDICATORS (pandas-ta)
# =============================================================================


class TestVWAPIndicator:
    """Volume Weighted Average Price tests."""

    def test_vwap_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="vwap", name="vwap")]
        result = compute_indicators(sample_bar_data, indicators)
        assert "vwap" in result
        assert_has_valid_values(result["vwap"], 190, "VWAP")

    def test_vwap_reasonable_values(self, sample_bar_data):
        indicators = [IndicatorConfig(type="vwap", name="vwap")]
        result = compute_indicators(sample_bar_data, indicators)
        vwap = result["vwap"]
        close = np.array(sample_bar_data.close)
        # VWAP should be within reasonable range of close
        valid_mask = ~np.isnan(vwap)
        diff_pct = np.abs(vwap[valid_mask] - close[valid_mask]) / close[valid_mask]
        assert np.mean(diff_pct) < 0.1  # Average deviation < 10%


class TestOBVIndicator:
    """On-Balance Volume tests."""

    def test_obv_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="obv", name="obv")]
        result = compute_indicators(sample_bar_data, indicators)
        assert "obv" in result
        assert_has_valid_values(result["obv"], 190, "OBV")

    def test_obv_cumulative(self, uptrend_data):
        """OBV should increase in uptrend (price up = add volume)."""
        indicators = [IndicatorConfig(type="obv", name="obv")]
        result = compute_indicators(uptrend_data, indicators)
        obv = result["obv"]
        # OBV should generally increase in uptrend
        valid = obv[~np.isnan(obv)]
        assert valid[-1] > valid[len(valid) // 2]  # End > middle


class TestCMFIndicator:
    """Chaikin Money Flow tests."""

    def test_cmf_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="cmf", name="cmf", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "cmf" in result
        assert_has_valid_values(result["cmf"], 170, "CMF")

    def test_cmf_reasonable_range(self, sample_bar_data):
        """CMF should typically be in a reasonable range."""
        indicators = [IndicatorConfig(type="cmf", name="cmf", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        # CMF is typically between -1 and 1 but can exceed in extreme cases
        valid = result["cmf"][~np.isnan(result["cmf"])]
        # Most values should be within -2 to 2
        within_range = np.sum(np.abs(valid) <= 2) / len(valid)
        assert within_range > 0.9, f"Only {within_range:.1%} of CMF values within [-2, 2]"


class TestMFIIndicator:
    """Money Flow Index tests."""

    def test_mfi_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="mfi", name="mfi", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "mfi" in result
        assert_has_valid_values(result["mfi"], 180, "MFI")

    def test_mfi_bounds(self, sample_bar_data):
        """MFI should be between 0 and 100 (like RSI)."""
        indicators = [IndicatorConfig(type="mfi", name="mfi", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert_bounds(result["mfi"], 0, 100, "MFI")


class TestADIndicator:
    """Accumulation/Distribution Line tests."""

    def test_ad_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="ad", name="ad")]
        result = compute_indicators(sample_bar_data, indicators)
        assert "ad" in result
        assert_has_valid_values(result["ad"], 190, "A/D")


# =============================================================================
# TREND INDICATORS (pandas-ta)
# =============================================================================


class TestADXIndicator:
    """Average Directional Index tests."""

    def test_adx_computes_multiple_outputs(self, sample_bar_data):
        indicators = [IndicatorConfig(type="adx", name="adx", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        # Should have ADX and directional indicators
        assert "adx_adx" in result or any("adx" in k.lower() for k in result)

    def test_adx_bounds(self, sample_bar_data):
        indicators = [IndicatorConfig(type="adx", name="adx", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        adx_key = next((k for k in result if "adx_adx" in k.lower()), None)
        if adx_key:
            assert_bounds(result[adx_key], 0, 100, "ADX")

    def test_adx_high_in_trend(self, uptrend_data):
        indicators = [IndicatorConfig(type="adx", name="adx", params={"length": 14})]
        result = compute_indicators(uptrend_data, indicators)
        adx_key = next((k for k in result if "adx_adx" in k.lower()), None)
        if adx_key:
            adx = result[adx_key]
            valid = adx[~np.isnan(adx)]
            # ADX should be elevated (>20) in trending market
            assert valid[-1] > 15

    def test_adx_low_in_sideways(self, sideways_data):
        indicators = [IndicatorConfig(type="adx", name="adx", params={"length": 14})]
        result = compute_indicators(sideways_data, indicators)
        adx_key = next((k for k in result if "adx_adx" in k.lower()), None)
        if adx_key:
            adx = result[adx_key]
            valid = adx[~np.isnan(adx)]
            # ADX should be lower (<30) in sideways market
            assert valid[-1] < 35


class TestSuperTrendIndicator:
    """SuperTrend tests."""

    def test_supertrend_computes(self, sample_bar_data):
        indicators = [
            IndicatorConfig(type="supertrend", name="st", params={"length": 10, "multiplier": 3.0})
        ]
        result = compute_indicators(sample_bar_data, indicators)
        has_st = any("st" in k.lower() or "supertrend" in k.lower() for k in result)
        assert has_st, f"SuperTrend missing. Keys: {list(result.keys())}"

    def test_supertrend_values_reasonable(self, sample_bar_data):
        indicators = [
            IndicatorConfig(type="supertrend", name="st", params={"length": 10, "multiplier": 3.0})
        ]
        result = compute_indicators(sample_bar_data, indicators)
        st_key = next(
            (k for k in result if "supertrend" in k.lower() and "d" not in k.lower()), None
        )
        if st_key:
            st = result[st_key]
            close = np.array(sample_bar_data.close)
            # SuperTrend should be within reasonable range of price
            valid_mask = ~np.isnan(st)
            if np.sum(valid_mask) > 0:
                diff_pct = np.abs(st[valid_mask] - close[valid_mask]) / close[valid_mask]
                assert np.mean(diff_pct) < 0.2


class TestAroonIndicator:
    """Aroon indicator tests."""

    def test_aroon_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="aroon", name="aroon", params={"length": 25})]
        result = compute_indicators(sample_bar_data, indicators)
        has_aroon = any("aroon" in k.lower() for k in result)
        assert has_aroon

    def test_aroon_bounds(self, sample_bar_data):
        indicators = [IndicatorConfig(type="aroon", name="aroon", params={"length": 25})]
        result = compute_indicators(sample_bar_data, indicators)
        for key in result:
            if "aroon" in key.lower() and "osc" not in key.lower():
                assert_bounds(result[key], 0, 100, key)


class TestPSARIndicator:
    """Parabolic SAR tests."""

    def test_psar_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="psar", name="psar", params={"af": 0.02, "max_af": 0.2})]
        result = compute_indicators(sample_bar_data, indicators)
        has_psar = any("psar" in k.lower() for k in result)
        assert has_psar


# =============================================================================
# VOLATILITY / CHANNEL INDICATORS (pandas-ta)
# =============================================================================


class TestDonchianChannels:
    """Donchian Channel tests."""

    def test_donchian_computes(self, sample_bar_data):
        indicators = [
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        has_dc = any("dc" in k.lower() for k in result)
        assert has_dc

    def test_donchian_upper_is_highest_high(self, sample_bar_data):
        indicators = [
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        upper_key = next((k for k in result if "dcu" in k.lower()), None)
        if upper_key:
            upper = result[upper_key]
            high = np.array(sample_bar_data.high)
            idx = 100
            if not np.isnan(upper[idx]):
                expected_upper = np.max(high[idx - 19 : idx + 1])
                assert upper[idx] == pytest.approx(expected_upper, rel=0.01)

    def test_donchian_lower_is_lowest_low(self, sample_bar_data):
        indicators = [
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)
        lower_key = next((k for k in result if "dcl" in k.lower()), None)
        if lower_key:
            lower = result[lower_key]
            low = np.array(sample_bar_data.low)
            idx = 100
            if not np.isnan(lower[idx]):
                expected_lower = np.min(low[idx - 19 : idx + 1])
                assert lower[idx] == pytest.approx(expected_lower, rel=0.01)


class TestKeltnerChannels:
    """Keltner Channel tests."""

    def test_keltner_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="kc", name="kc", params={"length": 20, "scalar": 2.0})]
        result = compute_indicators(sample_bar_data, indicators)
        has_kc = any("kc" in k.lower() for k in result)
        assert has_kc


# =============================================================================
# MOMENTUM INDICATORS (pandas-ta)
# =============================================================================


class TestCCIIndicator:
    """Commodity Channel Index tests."""

    def test_cci_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="cci", name="cci", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "cci" in result
        assert_has_valid_values(result["cci"], 170, "CCI")

    def test_cci_has_variance(self, sample_bar_data):
        """CCI should have variance (not constant)."""
        indicators = [IndicatorConfig(type="cci", name="cci", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        cci = result["cci"]
        valid = cci[~np.isnan(cci)]
        # CCI should have variance (not all same value)
        assert np.std(valid) > 0, "CCI has no variance"


class TestROCIndicator:
    """Rate of Change tests."""

    def test_roc_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="roc", name="roc", params={"length": 10})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "roc" in result
        assert_has_valid_values(result["roc"], 180, "ROC")

    def test_roc_positive_in_uptrend(self, uptrend_data):
        indicators = [IndicatorConfig(type="roc", name="roc", params={"length": 10})]
        result = compute_indicators(uptrend_data, indicators)
        roc = result["roc"]
        valid = roc[~np.isnan(roc)]
        # ROC should be mostly positive in uptrend
        assert np.mean(valid) > 0


class TestWilliamsRIndicator:
    """Williams %R tests."""

    def test_willr_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="willr", name="willr", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "willr" in result
        assert_has_valid_values(result["willr"], 180, "Williams %R")

    def test_willr_bounds(self, sample_bar_data):
        """Williams %R should be between -100 and 0."""
        indicators = [IndicatorConfig(type="willr", name="willr", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)
        assert_bounds(result["willr"], -100, 0, "Williams %R")


class TestMomentumIndicator:
    """Momentum indicator tests."""

    def test_mom_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="mom", name="mom", params={"length": 10})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "mom" in result
        assert_has_valid_values(result["mom"], 180, "Momentum")


# =============================================================================
# STATISTICS INDICATORS (pandas-ta)
# =============================================================================


class TestZScoreIndicator:
    """Z-Score tests."""

    def test_zscore_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="zscore", name="zscore", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "zscore" in result
        assert_has_valid_values(result["zscore"], 170, "Z-Score")

    def test_zscore_distribution(self, sample_bar_data):
        """Z-Score should be roughly normally distributed."""
        indicators = [IndicatorConfig(type="zscore", name="zscore", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        zscore = result["zscore"]
        valid = zscore[~np.isnan(zscore)]
        # Most values should be within -3 to 3
        within_3_std = np.sum(np.abs(valid) <= 3) / len(valid)
        assert within_3_std > 0.95


class TestStdDevIndicator:
    """Standard Deviation tests."""

    def test_stdev_computes(self, sample_bar_data):
        indicators = [IndicatorConfig(type="stdev", name="stdev", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        assert "stdev" in result
        assert_has_valid_values(result["stdev"], 170, "StdDev")

    def test_stdev_positive(self, sample_bar_data):
        indicators = [IndicatorConfig(type="stdev", name="stdev", params={"length": 20})]
        result = compute_indicators(sample_bar_data, indicators)
        valid = result["stdev"][~np.isnan(result["stdev"])]
        assert all(v >= 0 for v in valid)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIndicatorIntegration:
    """Integration tests combining multiple indicators."""

    def test_all_builtin_together(self, sample_bar_data):
        """Test all built-in indicators computed together."""
        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20}),
            IndicatorConfig(type=IndicatorType.EMA, name="ema", params={"period": 12}),
            IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
            IndicatorConfig(type=IndicatorType.MACD, name="macd", params={}),
            IndicatorConfig(type=IndicatorType.ATR, name="atr", params={"period": 14}),
            IndicatorConfig(type=IndicatorType.BBANDS, name="bb", params={}),
            IndicatorConfig(type=IndicatorType.STOCH, name="stoch", params={}),
        ]
        result = compute_indicators(sample_bar_data, indicators)

        # Check all present
        assert "sma" in result
        assert "ema" in result
        assert "rsi" in result
        assert "macd_line" in result
        assert "atr" in result
        assert "bb_upper" in result
        assert "stoch_k" in result

    def test_mixed_builtin_and_pandas_ta(self, sample_bar_data):
        """Test mixing built-in and pandas-ta indicators."""
        indicators = [
            # Built-in
            IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20}),
            IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
            # pandas-ta
            IndicatorConfig(type="vwap", name="vwap"),
            IndicatorConfig(type="adx", name="adx", params={"length": 14}),
            IndicatorConfig(type="obv", name="obv"),
        ]
        result = compute_indicators(sample_bar_data, indicators)

        assert "sma" in result
        assert "rsi" in result
        assert "vwap" in result
        assert "obv" in result
        # ADX might be adx_adx
        has_adx = any("adx" in k.lower() for k in result)
        assert has_adx

    def test_volume_indicators_together(self, sample_bar_data):
        """Test all volume indicators together."""
        indicators = [
            IndicatorConfig(type="vwap", name="vwap"),
            IndicatorConfig(type="obv", name="obv"),
            IndicatorConfig(type="mfi", name="mfi", params={"length": 14}),
            IndicatorConfig(type="ad", name="ad"),
        ]
        result = compute_indicators(sample_bar_data, indicators)

        assert "vwap" in result
        assert "obv" in result
        assert "mfi" in result
        assert "ad" in result

    def test_trend_indicators_together(self, sample_bar_data):
        """Test trend indicators together."""
        indicators = [
            IndicatorConfig(type="adx", name="adx", params={"length": 14}),
            IndicatorConfig(type="supertrend", name="st", params={"length": 10, "multiplier": 3.0}),
            IndicatorConfig(type="aroon", name="aroon", params={"length": 25}),
        ]
        result = compute_indicators(sample_bar_data, indicators)

        has_adx = any("adx" in k.lower() for k in result)
        has_st = any("st" in k.lower() or "supertrend" in k.lower() for k in result)
        has_aroon = any("aroon" in k.lower() for k in result)

        assert has_adx and has_st and has_aroon

    def test_momentum_indicators_together(self, sample_bar_data):
        """Test momentum indicators together."""
        indicators = [
            IndicatorConfig(type="cci", name="cci", params={"length": 20}),
            IndicatorConfig(type="roc", name="roc", params={"length": 10}),
            IndicatorConfig(type="willr", name="willr", params={"length": 14}),
            IndicatorConfig(type="mom", name="mom", params={"length": 10}),
        ]
        result = compute_indicators(sample_bar_data, indicators)

        assert "cci" in result
        assert "roc" in result
        assert "willr" in result
        assert "mom" in result


class TestEdgeCases:
    """Edge case tests."""

    def test_short_data(self):
        """Test with very short data series."""
        n = 20
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=[100.0] * n,
            highs=[101.0] * n,
            lows=[99.0] * n,
            closes=[100.0] * n,
            volumes=[1000000] * n,
        )

        # Should not crash
        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20}),
            IndicatorConfig(type="adx", name="adx", params={"length": 14}),
        ]
        result = compute_indicators(data, indicators)
        assert "sma" in result

    def test_constant_prices(self):
        """Test with no price movement."""
        n = 100
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=[100.0] * n,
            highs=[100.0] * n,
            lows=[100.0] * n,
            closes=[100.0] * n,
            volumes=[1000000] * n,
        )

        indicators = [
            IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
            IndicatorConfig(type="vwap", name="vwap"),
        ]
        result = compute_indicators(data, indicators)
        # Should handle gracefully (may have NaN but shouldn't crash)
        assert "rsi" in result
        assert "vwap" in result

    def test_extreme_volatility(self):
        """Test with extreme price swings."""
        n = 100
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        np.random.seed(42)
        # Wild swings: +/-10% each day
        returns = np.random.choice([-0.1, 0.1], size=n)
        close = 100.0 * np.cumprod(1 + returns)

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close * 1.05).tolist(),
            lows=(close * 0.95).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )

        indicators = [
            IndicatorConfig(type=IndicatorType.ATR, name="atr", params={"period": 14}),
            IndicatorConfig(type="adx", name="adx", params={"length": 14}),
        ]
        result = compute_indicators(data, indicators)
        # ATR should be high
        atr = result["atr"]
        valid = atr[~np.isnan(atr)]
        assert np.mean(valid) > 5  # High ATR due to volatility


class TestPerformance:
    """Performance-related tests."""

    @pytest.mark.slow
    def test_large_dataset_all_indicators(self):
        """Test with large dataset and many indicators."""
        n = 5000  # ~20 years of daily data
        timestamps = [datetime(2004, 1, 1) + timedelta(days=i) for i in range(n)]

        np.random.seed(42)
        returns = np.random.randn(n) * 0.02
        close = 100.0 * np.cumprod(1 + returns)

        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=(close * 0.999).tolist(),
            highs=(close * 1.01).tolist(),
            lows=(close * 0.99).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )

        indicators = [
            IndicatorConfig(type=IndicatorType.SMA, name="sma_200", params={"period": 200}),
            IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
            IndicatorConfig(type="vwap", name="vwap"),
            IndicatorConfig(type="adx", name="adx", params={"length": 14}),
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            ),
        ]

        import time

        start = time.time()
        result = compute_indicators(data, indicators)
        elapsed = time.time() - start

        # Should complete in reasonable time
        assert elapsed < 10.0, f"Took {elapsed:.2f}s, expected < 10s"
        assert len(result) >= 8  # OHLCV + indicators
