"""Technical indicator calculations."""

import numpy as np

from bonito.backtest.strategy import IndicatorConfig, IndicatorType
from bonito.data.models import BarData


def compute_indicators(
    data: BarData,
    indicators: list[IndicatorConfig],
) -> dict[str, np.ndarray]:
    """Compute all configured indicators.

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

    for config in indicators:
        if config.type == IndicatorType.SMA:
            period = config.params.get("period", 20)
            results[config.name] = sma(data.close, period)

        elif config.type == IndicatorType.EMA:
            period = config.params.get("period", 20)
            results[config.name] = ema(data.close, period)

        elif config.type == IndicatorType.RSI:
            period = config.params.get("period", 14)
            results[config.name] = rsi(data.close, period)

        elif config.type == IndicatorType.ATR:
            period = config.params.get("period", 14)
            results[config.name] = atr(data.high, data.low, data.close, period)

        elif config.type == IndicatorType.MACD:
            fast = config.params.get("fast_period", 12)
            slow = config.params.get("slow_period", 26)
            signal = config.params.get("signal_period", 9)
            macd_line, signal_line, histogram = macd(data.close, fast, slow, signal)
            results[f"{config.name}_line"] = macd_line
            results[f"{config.name}_signal"] = signal_line
            results[f"{config.name}_hist"] = histogram

        elif config.type == IndicatorType.BBANDS:
            period = config.params.get("period", 20)
            std_dev = config.params.get("std_dev", 2.0)
            upper, middle, lower = bollinger_bands(data.close, period, std_dev)
            results[f"{config.name}_upper"] = upper
            results[f"{config.name}_middle"] = middle
            results[f"{config.name}_lower"] = lower

        elif config.type == IndicatorType.STOCH:
            k_period = config.params.get("k_period", 14)
            d_period = config.params.get("d_period", 3)
            k, d = stochastic(data.high, data.low, data.close, k_period, d_period)
            results[f"{config.name}_k"] = k
            results[f"{config.name}_d"] = d

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
