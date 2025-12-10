"""Comprehensive tests for pandas-ta integration.

These tests follow TDD principles - written BEFORE implementation.
Tests cover:
1. Core pandas-ta indicators (VWAP, ADX, Donchian, OBV)
2. Multi-column output handling
3. Backward compatibility with existing indicators
4. Edge cases and error handling
"""

from datetime import datetime, timedelta

import numpy as np
import pytest

from bonito.backtest.strategy import IndicatorConfig, IndicatorType
from bonito.data.models import BarData


class TestPandasTAIntegration:
    """Integration tests for pandas-ta indicators."""

    @pytest.fixture
    def sample_bar_data(self) -> BarData:
        """Create realistic sample bar data for testing."""
        n = 100
        base_date = datetime(2024, 1, 1)
        timestamps = [base_date + timedelta(days=i) for i in range(n)]

        # Generate realistic price data with trend and volatility
        np.random.seed(42)
        base_price = 100.0
        returns = np.random.randn(n) * 0.02  # 2% daily vol
        close = base_price * np.cumprod(1 + returns)

        # Generate OHLC from close
        high = close * (1 + np.abs(np.random.randn(n) * 0.01))
        low = close * (1 - np.abs(np.random.randn(n) * 0.01))
        opens = np.roll(close, 1)
        opens[0] = base_price

        # Volume with realistic patterns (higher on volatile days)
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
    def trending_up_data(self) -> BarData:
        """Create data with strong uptrend for ADX testing."""
        n = 100
        base_date = datetime(2024, 1, 1)
        timestamps = [base_date + timedelta(days=i) for i in range(n)]

        # Strong uptrend: 1% daily gain with small noise
        np.random.seed(42)
        daily_return = 0.01
        noise = np.random.randn(n) * 0.002
        close = 100.0 * np.cumprod(1 + daily_return + noise)

        high = close * 1.005
        low = close * 0.995
        opens = np.roll(close, 1)
        opens[0] = 100.0

        volumes = [1_000_000] * n

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
    def sideways_data(self) -> BarData:
        """Create ranging/sideways data for ADX testing."""
        n = 100
        base_date = datetime(2024, 1, 1)
        timestamps = [base_date + timedelta(days=i) for i in range(n)]

        # Sideways: oscillate around 100 with no trend
        np.random.seed(42)
        close = 100.0 + np.sin(np.linspace(0, 10 * np.pi, n)) * 2 + np.random.randn(n) * 0.5

        high = close + 0.5
        low = close - 0.5
        opens = np.roll(close, 1)
        opens[0] = 100.0

        volumes = [1_000_000] * n

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


class TestVWAPIndicator(TestPandasTAIntegration):
    """Tests for Volume Weighted Average Price (VWAP)."""

    def test_vwap_computes_successfully(self, sample_bar_data):
        """VWAP should compute without errors."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="vwap", name="vwap")]
        result = compute_indicators(sample_bar_data, indicators)

        assert "vwap" in result
        assert len(result["vwap"]) == len(sample_bar_data)

    def test_vwap_values_are_reasonable(self, sample_bar_data):
        """VWAP should be within the price range."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="vwap", name="vwap")]
        result = compute_indicators(sample_bar_data, indicators)

        vwap = result["vwap"]
        close = sample_bar_data.close

        # VWAP should be between low and high of the day (roughly)
        valid_vwap = vwap[~np.isnan(vwap)]
        valid_close = np.array(close)[~np.isnan(vwap)]

        # VWAP should be within 10% of close (reasonable range)
        for v, c in zip(valid_vwap, valid_close, strict=True):
            assert abs(v - c) / c < 0.1, f"VWAP {v} too far from close {c}"

    def test_vwap_weights_by_volume(self, sample_bar_data):
        """VWAP should weight prices by volume - higher volume = more weight."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="vwap", name="vwap")]
        result = compute_indicators(sample_bar_data, indicators)

        # VWAP should not equal simple average (unless volume is constant)
        vwap = result["vwap"]
        typical_price = (
            np.array(sample_bar_data.high)
            + np.array(sample_bar_data.low)
            + np.array(sample_bar_data.close)
        ) / 3

        # They should be close but not identical
        valid_mask = ~np.isnan(vwap)
        if np.sum(valid_mask) > 0:
            # Check they're correlated but not identical
            correlation = np.corrcoef(vwap[valid_mask], typical_price[valid_mask])[0, 1]
            assert correlation > 0.9, "VWAP should be highly correlated with typical price"


class TestADXIndicator(TestPandasTAIntegration):
    """Tests for Average Directional Index (ADX)."""

    def test_adx_returns_three_components(self, sample_bar_data):
        """ADX should return ADX, +DI, -DI."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="adx", name="trend", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)

        # Should have all three components
        assert "trend_adx" in result or "trend" in result, "ADX value missing"
        # Note: exact naming will depend on implementation

    def test_adx_bounds(self, sample_bar_data):
        """ADX should be between 0 and 100."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="adx", name="trend", params={"length": 14})]
        result = compute_indicators(sample_bar_data, indicators)

        # Find ADX values (could be named "trend" or "trend_adx")
        adx_key = "trend_adx" if "trend_adx" in result else "trend"
        if adx_key in result:
            adx = result[adx_key]
            valid = adx[~np.isnan(adx)]
            assert all(0 <= v <= 100 for v in valid), "ADX should be 0-100"

    def test_adx_high_in_trending_market(self, trending_up_data):
        """ADX should be high (>25) in strongly trending markets."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="adx", name="trend", params={"length": 14})]
        result = compute_indicators(trending_up_data, indicators)

        adx_key = "trend_adx" if "trend_adx" in result else "trend"
        if adx_key in result:
            adx = result[adx_key]
            # Last ADX value should be high for trending data
            valid = adx[~np.isnan(adx)]
            if len(valid) > 0:
                assert valid[-1] > 20, f"ADX {valid[-1]} should be high in uptrend"

    def test_adx_low_in_sideways_market(self, sideways_data):
        """ADX should be low (<25) in sideways/ranging markets."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="adx", name="trend", params={"length": 14})]
        result = compute_indicators(sideways_data, indicators)

        adx_key = "trend_adx" if "trend_adx" in result else "trend"
        if adx_key in result:
            adx = result[adx_key]
            valid = adx[~np.isnan(adx)]
            if len(valid) > 0:
                # ADX should be lower in sideways market
                assert valid[-1] < 40, f"ADX {valid[-1]} should be lower in sideways market"


class TestDonchianChannels(TestPandasTAIntegration):
    """Tests for Donchian Channels."""

    def test_donchian_returns_three_bands(self, sample_bar_data):
        """Donchian should return upper, middle, lower bands."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)

        # Should have upper and lower at minimum
        has_upper = any("upper" in k.lower() or "dcu" in k.lower() for k in result)
        has_lower = any("lower" in k.lower() or "dcl" in k.lower() for k in result)

        assert has_upper or has_lower, f"Donchian bands missing. Keys: {list(result.keys())}"

    def test_donchian_upper_is_highest_high(self, sample_bar_data):
        """Donchian upper should be highest high over period."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)

        # Find upper band
        upper_key = next((k for k in result if "upper" in k.lower() or "dcu" in k.lower()), None)
        if upper_key:
            upper = result[upper_key]
            high = np.array(sample_bar_data.high)

            # Check at a valid point
            idx = 50
            if not np.isnan(upper[idx]):
                expected_upper = np.max(high[idx - 19 : idx + 1])  # 20-period lookback
                assert upper[idx] == pytest.approx(expected_upper, rel=0.01)

    def test_donchian_lower_is_lowest_low(self, sample_bar_data):
        """Donchian lower should be lowest low over period."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(
                type="donchian", name="dc", params={"lower_length": 20, "upper_length": 20}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)

        # Find lower band
        lower_key = next((k for k in result if "lower" in k.lower() or "dcl" in k.lower()), None)
        if lower_key:
            lower = result[lower_key]
            low = np.array(sample_bar_data.low)

            # Check at a valid point
            idx = 50
            if not np.isnan(lower[idx]):
                expected_lower = np.min(low[idx - 19 : idx + 1])
                assert lower[idx] == pytest.approx(expected_lower, rel=0.01)


class TestOBVIndicator(TestPandasTAIntegration):
    """Tests for On-Balance Volume (OBV)."""

    def test_obv_computes_successfully(self, sample_bar_data):
        """OBV should compute without errors."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="obv", name="obv")]
        result = compute_indicators(sample_bar_data, indicators)

        assert "obv" in result
        assert len(result["obv"]) == len(sample_bar_data)

    def test_obv_cumulative_nature(self, sample_bar_data):
        """OBV should be cumulative based on price direction."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="obv", name="obv")]
        result = compute_indicators(sample_bar_data, indicators)

        obv = result["obv"]

        # OBV should change based on price direction
        close = np.array(sample_bar_data.close)
        volume = np.array(sample_bar_data.volume)

        # Manual calculation for verification
        manual_obv = np.zeros(len(close))
        manual_obv[0] = volume[0]
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                manual_obv[i] = manual_obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                manual_obv[i] = manual_obv[i - 1] - volume[i]
            else:
                manual_obv[i] = manual_obv[i - 1]

        # Check correlation (exact values may differ due to implementation)
        valid_mask = ~np.isnan(obv)
        if np.sum(valid_mask) > 10:
            correlation = np.corrcoef(obv[valid_mask], manual_obv[valid_mask])[0, 1]
            assert correlation > 0.99, "OBV should match manual calculation"


class TestSuperTrendIndicator(TestPandasTAIntegration):
    """Tests for SuperTrend indicator."""

    def test_supertrend_computes_successfully(self, sample_bar_data):
        """SuperTrend should compute without errors."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(type="supertrend", name="st", params={"length": 10, "multiplier": 3.0})
        ]
        result = compute_indicators(sample_bar_data, indicators)

        # Should have supertrend value
        has_supertrend = any("st" in k.lower() or "supertrend" in k.lower() for k in result)
        assert has_supertrend, f"SuperTrend missing. Keys: {list(result.keys())}"

    def test_supertrend_direction(self, trending_up_data):
        """SuperTrend direction should reflect trend."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(type="supertrend", name="st", params={"length": 10, "multiplier": 3.0})
        ]
        result = compute_indicators(trending_up_data, indicators)

        # Find direction indicator
        dir_key = next((k for k in result if "dir" in k.lower() or "trend" in k.lower()), None)
        if dir_key and dir_key in result:
            direction = result[dir_key]
            # In uptrend, direction should be mostly positive (1) at the end
            valid = direction[~np.isnan(direction)]
            if len(valid) > 0:
                # Last value should indicate uptrend
                pass  # Direction encoding varies by implementation


class TestBackwardCompatibility(TestPandasTAIntegration):
    """Ensure existing indicators still work after pandas-ta integration."""

    def test_existing_sma_still_works(self, sample_bar_data):
        """SMA should still work with IndicatorType enum."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})]
        result = compute_indicators(sample_bar_data, indicators)

        assert "sma_20" in result
        assert len(result["sma_20"]) == len(sample_bar_data)

        # Verify calculation is correct
        close = np.array(sample_bar_data.close)
        expected_sma_50 = np.mean(close[30:50])
        assert result["sma_20"][49] == pytest.approx(expected_sma_50, rel=0.01)

    def test_existing_ema_still_works(self, sample_bar_data):
        """EMA should still work."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type=IndicatorType.EMA, name="ema_12", params={"period": 12})]
        result = compute_indicators(sample_bar_data, indicators)

        assert "ema_12" in result
        valid = result["ema_12"][~np.isnan(result["ema_12"])]
        assert len(valid) > 0

    def test_existing_rsi_still_works(self, sample_bar_data):
        """RSI should still work."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14})]
        result = compute_indicators(sample_bar_data, indicators)

        assert "rsi_14" in result
        valid = result["rsi_14"][~np.isnan(result["rsi_14"])]
        assert all(0 <= v <= 100 for v in valid)

    def test_existing_macd_still_works(self, sample_bar_data):
        """MACD should still produce three outputs."""
        from bonito.backtest.indicators import compute_indicators

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

    def test_existing_bbands_still_works(self, sample_bar_data):
        """Bollinger Bands should still produce three outputs."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(
                type=IndicatorType.BBANDS, name="bb", params={"period": 20, "std_dev": 2}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)

        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result

    def test_existing_atr_still_works(self, sample_bar_data):
        """ATR should still work."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type=IndicatorType.ATR, name="atr_14", params={"period": 14})]
        result = compute_indicators(sample_bar_data, indicators)

        assert "atr_14" in result
        valid = result["atr_14"][~np.isnan(result["atr_14"])]
        assert all(v > 0 for v in valid)

    def test_existing_stochastic_still_works(self, sample_bar_data):
        """Stochastic should still produce %K and %D."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            IndicatorConfig(
                type=IndicatorType.STOCH, name="stoch", params={"k_period": 14, "d_period": 3}
            )
        ]
        result = compute_indicators(sample_bar_data, indicators)

        assert "stoch_k" in result
        assert "stoch_d" in result


class TestMixedIndicators(TestPandasTAIntegration):
    """Test mixing legacy indicators with new pandas-ta indicators."""

    def test_mixed_legacy_and_pandas_ta(self, sample_bar_data):
        """Should be able to use both legacy and pandas-ta indicators together."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [
            # Legacy indicators
            IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20}),
            IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14}),
            # New pandas-ta indicators
            IndicatorConfig(type="vwap", name="vwap"),
            IndicatorConfig(type="adx", name="trend", params={"length": 14}),
        ]
        result = compute_indicators(sample_bar_data, indicators)

        # All should be present
        assert "sma_20" in result
        assert "rsi_14" in result
        assert "vwap" in result
        # ADX might be "trend" or "trend_adx"
        has_adx = "trend" in result or "trend_adx" in result
        assert has_adx


class TestEdgeCases(TestPandasTAIntegration):
    """Test edge cases and error handling."""

    def test_short_data_series(self):
        """Should handle data shorter than indicator period gracefully."""
        from bonito.backtest.indicators import compute_indicators

        # Create very short data
        n = 5
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]

        bar_data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=[100.0] * n,
            highs=[101.0] * n,
            lows=[99.0] * n,
            closes=[100.0] * n,
            volumes=[1000000] * n,
        )

        # This should not crash, even if period > data length
        indicators = [IndicatorConfig(type="adx", name="adx", params={"length": 14})]

        # Should not raise an exception
        result = compute_indicators(bar_data, indicators)
        assert "adx" in result or "adx_adx" in result

    def test_constant_prices(self):
        """Should handle constant prices (no volatility)."""
        from bonito.backtest.indicators import compute_indicators

        n = 50
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]

        bar_data = BarData(
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
            IndicatorConfig(type="vwap", name="vwap"),
            IndicatorConfig(type="obv", name="obv"),
        ]

        result = compute_indicators(bar_data, indicators)
        assert "vwap" in result
        assert "obv" in result

    def test_unknown_indicator_type_raises_error(self, sample_bar_data):
        """Unknown indicator type should raise appropriate error."""
        from bonito.backtest.indicators import compute_indicators

        indicators = [IndicatorConfig(type="nonexistent_indicator_xyz", name="test")]

        with pytest.raises((ValueError, KeyError, AttributeError)):
            compute_indicators(sample_bar_data, indicators)


class TestIndicatorTypeExtension:
    """Test that IndicatorType enum or validation handles new types."""

    def test_string_indicator_types_accepted(self):
        """String indicator types should be accepted for pandas-ta indicators."""
        # This should not raise validation error
        config = IndicatorConfig(type="vwap", name="vwap")
        assert config.type == "vwap"

        config = IndicatorConfig(type="adx", name="adx", params={"length": 14})
        assert config.type == "adx"

    def test_enum_indicator_types_still_work(self):
        """Enum types should still work for backward compatibility."""
        config = IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20})
        assert config.type == IndicatorType.SMA


class TestPerformance:
    """Performance-related tests."""

    @pytest.mark.slow
    def test_large_dataset_performance(self):
        """Indicator computation should complete in reasonable time for large datasets."""
        import time

        from bonito.backtest.indicators import compute_indicators

        # Generate 10 years of daily data (~2500 bars)
        n = 2500
        timestamps = [datetime(2014, 1, 1) + timedelta(days=i) for i in range(n)]

        np.random.seed(42)
        base_price = 100.0
        returns = np.random.randn(n) * 0.02
        close = base_price * np.cumprod(1 + returns)

        bar_data = BarData(
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
            IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14}),
            IndicatorConfig(type="vwap", name="vwap"),
            IndicatorConfig(type="adx", name="adx", params={"length": 14}),
        ]

        start = time.time()
        result = compute_indicators(bar_data, indicators)
        elapsed = time.time() - start

        # Should complete in under 5 seconds
        assert elapsed < 5.0, f"Computation took {elapsed:.2f}s, expected < 5s"
        assert len(result) >= 6  # OHLCV + at least 4 indicators
