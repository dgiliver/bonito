"""Mean Reversion Strategy Plugin.

A mean reversion strategy that buys when price is oversold (below lower band)
and sells when price reverts to the mean. Uses Bollinger Bands-style bands
around a moving average.

This serves as an example plugin demonstrating:
- Short position support (entry_side="short")
- Multiple indicators for charting
- Range-bound trading logic
"""

import numpy as np

from bonito.backtest.plugins import ParameterSpec, SignalOutput, StrategyPlugin
from bonito.data.models import BarData


class MeanReversionStrategy(StrategyPlugin):
    """Mean reversion strategy using Bollinger-style bands.

    Enters long when price touches the lower band (oversold condition).
    Exits when price reverts back to the moving average.

    Good for range-bound, low-volatility markets.
    May suffer during strong trends.
    """

    name = "mean_reversion"
    description = "Buy oversold (at lower band), sell at mean reversion"

    parameters = {
        "period": ParameterSpec(
            type="int",
            default=20,
            min=5,
            max=100,
            description="Period for moving average and standard deviation",
        ),
        "num_std": ParameterSpec(
            type="float",
            default=2.0,
            min=0.5,
            max=4.0,
            description="Number of standard deviations for bands",
        ),
        "side": ParameterSpec(
            type="str",
            default="long",
            choices=["long", "short"],
            description="Position side: long (buy oversold) or short (sell overbought)",
        ),
    }

    def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
        """Compute entry/exit signals based on band touches.

        Args:
            data: Historical bar data (OHLCV)
            params: Validated parameters

        Returns:
            SignalOutput with entry/exit boolean arrays and band indicators
        """
        closes = data.close
        period = params["period"]
        num_std = params["num_std"]
        side = params["side"]

        n = len(closes)

        # Compute moving average and bands
        sma = np.zeros(n)
        upper_band = np.zeros(n)
        lower_band = np.zeros(n)

        for i in range(period - 1, n):
            window = closes[i - period + 1 : i + 1]
            sma[i] = np.mean(window)
            std = np.std(window)
            upper_band[i] = sma[i] + num_std * std
            lower_band[i] = sma[i] - num_std * std

        # Set NaN for warmup period
        sma[: period - 1] = np.nan
        upper_band[: period - 1] = np.nan
        lower_band[: period - 1] = np.nan

        # Generate signals based on side
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)

        if side == "long":
            # Long: buy when price touches lower band, exit at mean
            entries[period:] = closes[period:] <= lower_band[period:]
            exits[period:] = closes[period:] >= sma[period:]
        else:
            # Short: sell when price touches upper band, exit at mean
            entries[period:] = closes[period:] >= upper_band[period:]
            exits[period:] = closes[period:] <= sma[period:]

        return SignalOutput(
            entries=entries,
            exits=exits,
            entry_side=side,
            indicators={
                "sma": sma,
                "upper_band": upper_band,
                "lower_band": lower_band,
            },
            metadata={
                "period": period,
                "num_std": num_std,
                "side": side,
            },
        )
