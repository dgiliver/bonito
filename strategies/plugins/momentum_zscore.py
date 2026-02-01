"""Momentum Z-Score Strategy Plugin.

A momentum strategy that generates signals based on the z-score of price returns.
Enters long when the z-score exceeds a threshold (indicating strong momentum),
and exits when the z-score falls below an exit threshold.

This serves as an example plugin demonstrating:
- Parameter definition with ParameterSpec
- Signal generation with SignalOutput
- Custom indicator computation for charting
"""

import numpy as np

from bonito.backtest.plugins import ParameterSpec, SignalOutput, StrategyPlugin
from bonito.data.models import BarData


class MomentumZscoreStrategy(StrategyPlugin):
    """Z-score momentum strategy with dynamic thresholds.

    This strategy computes the z-score of daily returns over a lookback period.
    When the z-score exceeds the entry threshold, it generates a long signal.
    The position is exited when z-score falls below the exit threshold.

    Good for trending markets but may underperform in choppy conditions.
    """

    name = "momentum_zscore"
    description = "Long when z-score of returns exceeds threshold (momentum breakout)"

    parameters = {
        "lookback": ParameterSpec(
            type="int",
            default=20,
            min=5,
            max=100,
            description="Lookback period for z-score calculation",
        ),
        "entry_threshold": ParameterSpec(
            type="float",
            default=2.0,
            min=0.5,
            max=4.0,
            description="Z-score threshold for long entry (higher = more selective)",
        ),
        "exit_threshold": ParameterSpec(
            type="float",
            default=0.0,
            min=-2.0,
            max=2.0,
            description="Z-score threshold for exit (lower = hold longer)",
        ),
    }

    def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
        """Compute entry/exit signals based on return z-score.

        Args:
            data: Historical bar data (OHLCV)
            params: Validated parameters

        Returns:
            SignalOutput with entry/exit boolean arrays and z-score indicator
        """
        closes = data.close
        lookback = params["lookback"]
        entry_thresh = params["entry_threshold"]
        exit_thresh = params["exit_threshold"]

        n = len(closes)

        # Compute daily returns
        returns = np.zeros(n)
        returns[1:] = (closes[1:] - closes[:-1]) / closes[:-1]

        # Compute rolling z-score of returns
        zscore = np.zeros(n)
        for i in range(lookback, n):
            window = returns[i - lookback + 1 : i + 1]
            mean = np.mean(window)
            std = np.std(window)
            if std > 0:
                zscore[i] = (returns[i] - mean) / std

        # Generate signals
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)

        # Entry: z-score crosses above entry threshold
        entries[lookback:] = (zscore[lookback - 1 : -1] <= entry_thresh) & (
            zscore[lookback:] > entry_thresh
        )

        # Exit: z-score falls below exit threshold
        exits[lookback:] = zscore[lookback:] < exit_thresh

        return SignalOutput(
            entries=entries,
            exits=exits,
            entry_side="long",
            indicators={
                "zscore": zscore,
                "returns": returns,
            },
            metadata={
                "lookback": lookback,
                "entry_threshold": entry_thresh,
                "exit_threshold": exit_thresh,
            },
        )
