"""Technical indicator calculations.

Supports both built-in indicators and pandas-ta indicators.
"""

import numpy as np
import pandas as pd

from bonito.backtest.strategy import IndicatorConfig, IndicatorType
from bonito.data.models import BarData

# Lazy import for pandas_ta to avoid startup overhead
_pandas_ta = None


def _get_pandas_ta():
    """Lazy load pandas_ta module."""
    global _pandas_ta
    if _pandas_ta is None:
        import pandas_ta as ta

        _pandas_ta = ta
    return _pandas_ta


def _bardata_to_dataframe(data: BarData) -> pd.DataFrame:
    """Convert BarData to pandas DataFrame for pandas-ta.

    Uses timestamps as DatetimeIndex which is required for VWAP and other
    time-aware indicators.
    """
    df = pd.DataFrame(
        {
            "open": data.open,
            "high": data.high,
            "low": data.low,
            "close": data.close,
            "volume": data.volume,
        }
    )
    # Set DatetimeIndex for indicators like VWAP that require it
    if data.timestamps:
        df.index = pd.DatetimeIndex(data.timestamps)
    return df


def _compute_pandas_ta_indicator(
    df: pd.DataFrame,
    indicator_type: str,
    name: str,
    params: dict,
) -> dict[str, np.ndarray]:
    """Compute a pandas-ta indicator and extract results.

    Args:
        df: DataFrame with OHLCV data
        indicator_type: Name of the pandas-ta indicator (e.g., "vwap", "adx")
        name: User-specified name prefix for the indicator
        params: Parameters to pass to the indicator

    Returns:
        Dictionary of indicator name -> numpy array
    """
    ta = _get_pandas_ta()
    results = {}

    # Get the indicator function from pandas_ta
    indicator_func = getattr(ta, indicator_type, None)
    if indicator_func is None:
        raise ValueError(f"Unknown pandas-ta indicator: {indicator_type}")

    # Map common parameter names to pandas-ta conventions
    mapped_params = _map_params(indicator_type, params)

    try:
        # Call the indicator function
        result = indicator_func(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            volume=df["volume"],
            open_=df["open"],
            **mapped_params,
        )
    except TypeError:
        # Some indicators don't need all OHLCV - try with just what's needed
        try:
            result = indicator_func(close=df["close"], **mapped_params)
        except TypeError:
            try:
                result = indicator_func(
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    **mapped_params,
                )
            except TypeError:
                # Last resort - let pandas-ta figure it out
                result = indicator_func(df, **mapped_params)

    # Handle different result types
    if result is None:
        # Indicator returned nothing - likely insufficient data
        results[name] = np.full(len(df), np.nan)
    elif isinstance(result, pd.Series):
        results[name] = result.values
    elif isinstance(result, pd.DataFrame):
        # Multi-column indicator - extract each column
        for col in result.columns:
            # Create meaningful suffix from column name
            suffix = _clean_column_suffix(col, indicator_type)
            results[f"{name}_{suffix}"] = result[col].values
    else:
        # Unexpected type
        results[name] = np.array(result)

    return results


def _map_params(indicator_type: str, params: dict) -> dict:
    """Map common parameter names to pandas-ta conventions.

    Our DSL uses "period" but pandas-ta often uses "length".
    """
    mapped = params.copy()

    # Common mappings
    if "period" in mapped and "length" not in mapped:
        mapped["length"] = mapped.pop("period")

    # Indicator-specific mappings
    if indicator_type == "donchian" and "length" in mapped:
        # Donchian uses lower_length and upper_length
        length = mapped.pop("length")
        mapped.setdefault("lower_length", length)
        mapped.setdefault("upper_length", length)

    return mapped


def _clean_column_suffix(col_name: str, indicator_type: str) -> str:
    """Clean up pandas-ta column names for our naming convention.

    pandas-ta returns columns like:
    - "ADX_14", "DMP_14" → we want "adx", "dmp"
    - "SUPERT_10_3.0", "SUPERTd_10_3.0" → we want "value", "direction"
    - "AROOND_25", "AROONU_25" → we want "down", "up"
    - "KCLe_20_2.0", "KCBe_20_2.0" → we want "lower", "basis", "upper"
    """
    col_lower = col_name.lower()
    indicator_lower = indicator_type.lower()

    # Special mappings for known indicators with complex output names
    # Order matters - more specific prefixes should come first!
    special_mappings = {
        # SuperTrend: SUPERTd (direction), SUPERTl (long), SUPERTs (short), SUPERT (value)
        # Must check longer prefixes first!
        "supertrend": [
            ("supertd", "direction"),
            ("supertl", "long"),
            ("superts", "short"),
            ("supert", "value"),
        ],
        # Aroon: AROONOSC (oscillator), AROOND (down), AROONU (up)
        "aroon": [("aroonosc", "osc"), ("aroond", "down"), ("aroonu", "up")],
        # Keltner Channels: KCLe (lower), KCBe (basis/middle), KCUe (upper)
        "kc": [("kcle", "lower"), ("kcbe", "middle"), ("kcue", "upper")],
        # PSAR: PSARaf (acceleration), PSARl (long), PSARs (short), PSARr (reversal)
        "psar": [("psaraf", "af"), ("psarl", "long"), ("psars", "short"), ("psarr", "reversal")],
    }

    # Check if we have special mappings for this indicator
    if indicator_lower in special_mappings:
        mappings = special_mappings[indicator_lower]
        # Look for matching prefix in the column name (order matters!)
        for prefix, suffix in mappings:
            if prefix in col_lower:
                return suffix

    # Generic cleaning
    parts = col_lower.split("_")

    # Filter out numeric parts (integers and floats like "14", "3.0", "0.02")
    def is_numeric(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    non_numeric = [p for p in parts if not is_numeric(p)]

    if not non_numeric:
        return indicator_lower

    # Remove indicator name prefix if present
    if non_numeric[0] == indicator_lower:
        non_numeric = non_numeric[1:]

    if not non_numeric:
        return indicator_lower

    return "_".join(non_numeric) if non_numeric else indicator_lower


def compute_indicators(
    data: BarData,
    indicators: list[IndicatorConfig],
) -> dict[str, np.ndarray]:
    """Compute all configured indicators.

    Supports both built-in indicators (SMA, EMA, RSI, etc.) and pandas-ta
    indicators (VWAP, ADX, Donchian, OBV, etc.).

    Args:
        data: Bar data to compute indicators on
        indicators: List of indicator configurations

    Returns:
        Dictionary mapping indicator names to their values
    """
    results: dict[str, np.ndarray] = {
        # Always include price data
        "open": data.open,
        "high": data.high,
        "low": data.low,
        "close": data.close,
        "volume": data.volume,
    }

    # Prepare DataFrame once for pandas-ta indicators (lazy)
    df: pd.DataFrame | None = None

    for config in indicators:
        indicator_type = config.type

        # Handle built-in indicators (IndicatorType enum)
        if indicator_type == IndicatorType.SMA:
            period = config.params.get("period", 20)
            results[config.name] = sma(data.close, period)

        elif indicator_type == IndicatorType.EMA:
            period = config.params.get("period", 20)
            results[config.name] = ema(data.close, period)

        elif indicator_type == IndicatorType.RSI:
            period = config.params.get("period", 14)
            results[config.name] = rsi(data.close, period)

        elif indicator_type == IndicatorType.ATR:
            period = config.params.get("period", 14)
            results[config.name] = atr(data.high, data.low, data.close, period)

        elif indicator_type == IndicatorType.MACD:
            fast = config.params.get("fast_period", 12)
            slow = config.params.get("slow_period", 26)
            signal = config.params.get("signal_period", 9)
            macd_line, signal_line, histogram = macd(data.close, fast, slow, signal)
            results[f"{config.name}_line"] = macd_line
            results[f"{config.name}_signal"] = signal_line
            results[f"{config.name}_hist"] = histogram

        elif indicator_type == IndicatorType.BBANDS:
            period = config.params.get("period", 20)
            std_dev = config.params.get("std_dev", 2.0)
            upper, middle, lower = bollinger_bands(data.close, period, std_dev)
            results[f"{config.name}_upper"] = upper
            results[f"{config.name}_middle"] = middle
            results[f"{config.name}_lower"] = lower

        elif indicator_type == IndicatorType.STOCH:
            k_period = config.params.get("k_period", 14)
            d_period = config.params.get("d_period", 3)
            k, d = stochastic(data.high, data.low, data.close, k_period, d_period)
            results[f"{config.name}_k"] = k
            results[f"{config.name}_d"] = d

        else:
            # Handle pandas-ta indicators (string type)
            if df is None:
                df = _bardata_to_dataframe(data)

            indicator_name = str(indicator_type).lower()
            pandas_ta_results = _compute_pandas_ta_indicator(
                df, indicator_name, config.name, config.params
            )
            results.update(pandas_ta_results)

    return results


def sma(prices: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    result = np.full_like(prices, np.nan)
    for i in range(period - 1, len(prices)):
        result[i] = np.mean(prices[i - period + 1 : i + 1])
    return result


def ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    result = np.full_like(prices, np.nan)
    multiplier = 2 / (period + 1)

    # Initialize with SMA
    result[period - 1] = np.mean(prices[:period])

    # Calculate EMA
    for i in range(period, len(prices)):
        result[i] = (prices[i] * multiplier) + (result[i - 1] * (1 - multiplier))

    return result


def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index."""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    result = np.full_like(prices, np.nan)

    # Initial averages
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    # Subsequent values using smoothing
    for i in range(period, len(prices) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result[i + 1] = 100
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100 - (100 / (1 + rs))

    return result


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range."""
    tr = np.maximum(
        high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    )

    result = np.full_like(close, np.nan)
    result[period] = np.mean(tr[:period])

    for i in range(period, len(tr)):
        result[i + 1] = (result[i] * (period - 1) + tr[i]) / period

    return result


def macd(
    prices: np.ndarray,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD indicator."""
    fast_ema = ema(prices, fast_period)
    slow_ema = ema(prices, slow_period)
    macd_line = fast_ema - slow_ema

    # Signal line is EMA of MACD line
    signal_line = ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def bollinger_bands(
    prices: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands."""
    middle = sma(prices, period)

    # Calculate rolling standard deviation
    std = np.full_like(prices, np.nan)
    for i in range(period - 1, len(prices)):
        std[i] = np.std(prices[i - period + 1 : i + 1])

    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    return upper, middle, lower


def stochastic(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic oscillator."""
    k = np.full_like(close, np.nan)

    for i in range(k_period - 1, len(close)):
        highest = np.max(high[i - k_period + 1 : i + 1])
        lowest = np.min(low[i - k_period + 1 : i + 1])

        if highest == lowest:
            k[i] = 50  # Neutral when no range
        else:
            k[i] = 100 * (close[i] - lowest) / (highest - lowest)

    # %D is SMA of %K
    d = sma(k, d_period)

    return k, d
