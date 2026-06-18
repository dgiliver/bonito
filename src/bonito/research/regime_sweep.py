"""Cross-regime robustness reporting for a single already-run backtest.

A train/holdout gate (cluster_research.research_cluster) answers "does this
generalize past the data it was picked on." It does not answer "does this
survive a crash," because a single holdout window usually sits inside one
regime. This module answers that second question: slice one full-history
backtest result into several fixed historical windows (GFC, COVID, the 2022
bear, etc.) and compare each to a buy-and-hold benchmark over the same
window — the question a professional allocator asks before sizing a
strategy, not just before approving it.

Short windows are noisy: a 3-month regime with 2 trades can swing Sharpe to
a value that looks great or terrible by chance alone. `RegimeRow.low_sample`
flags this explicitly rather than letting a thin sample masquerade as a
verdict — see kill_verdict's MAX_SHARPE comment for why an extreme Sharpe
on its own is not trustworthy.
"""

from datetime import datetime

from pydantic import BaseModel

from bonito.backtest.models import BacktestResult
from bonito.data.models import BarData
from bonito.trading.validation import WindowMetrics, kill_verdict, window_metrics

# Trades below this count make a window's Sharpe a near-meaningless point
# estimate — a couple of lucky or unlucky trades dominate the ratio. Flag,
# don't hide: the regime's return/drawdown can still be informative even
# when its Sharpe isn't.
LOW_SAMPLE_TRADES = 10


class Regime(BaseModel):
    """A named historical (or current) window to evaluate a strategy over."""

    name: str
    start: datetime
    end: datetime


# Fixed, well-known historical stress windows. These are real calendar
# history and don't go stale. "Full history" isn't included here since its
# end keeps moving with new data — build it from the data itself via
# full_history_regime() instead.
STANDARD_REGIMES: list[Regime] = [
    Regime(name="GFC crash+grind", start=datetime(2007, 7, 1), end=datetime(2009, 12, 31)),
    Regime(name="COVID crash", start=datetime(2020, 2, 1), end=datetime(2020, 4, 30)),
    Regime(name="COVID V-recovery", start=datetime(2020, 4, 1), end=datetime(2020, 12, 31)),
    Regime(name="2022 bear/chop", start=datetime(2022, 1, 1), end=datetime(2022, 12, 31)),
    Regime(name="2023-25 AI bull", start=datetime(2023, 1, 1), end=datetime(2025, 12, 31)),
]


def full_history_regime(data: BarData) -> Regime:
    """The complete span of `data` as a Regime, for an aggregate row."""
    return Regime(name="Full history", start=data.timestamps[0], end=data.timestamps[-1])


def cagr(total_return: float, years: float) -> float:
    """Compound annual growth rate from a cumulative return over `years`.

    Multi-decade cumulative returns (e.g. "9823%") are technically correct
    but read as alarming or overfit-flavored; CAGR is the number that's
    actually comparable across strategies, windows, and a benchmark.
    """
    base = 1 + total_return
    if base <= 0:
        return -1.0  # total wipeout
    if years <= 0:
        return 0.0
    return base ** (1 / years) - 1


class RegimeRow(BaseModel):
    """One regime's verdict for one strategy, with a benchmark alongside."""

    regime: str
    start: datetime
    end: datetime
    metrics: WindowMetrics
    cagr: float
    reasons: list[str]
    low_sample: bool
    benchmark_total_return: float | None = None
    benchmark_cagr: float | None = None

    @property
    def passed(self) -> bool:
        return not self.reasons


def _buy_hold_return(data: BarData, start: datetime, end: datetime) -> float | None:
    """Buy-and-hold return of `data` over [start, end], or None if the
    window falls outside the data's range."""
    start_idx = next((i for i, t in enumerate(data.timestamps) if t >= start), None)
    end_candidates = [i for i, t in enumerate(data.timestamps) if t <= end]
    if start_idx is None or not end_candidates:
        return None
    end_idx = end_candidates[-1]
    if end_idx <= start_idx or data.closes[start_idx] <= 0:
        return None
    return data.closes[end_idx] / data.closes[start_idx] - 1


def regime_report(
    result: BacktestResult,
    regimes: list[Regime],
    benchmark_data: BarData | None = None,
    low_sample_trades: int = LOW_SAMPLE_TRADES,
) -> list[RegimeRow]:
    """Slice one full-range backtest result into each regime window.

    `result` must come from a backtest run over a span covering every
    regime in `regimes` plus its own warm-up — this only slices an
    already-computed equity curve and trade list, it never re-runs the
    engine. Pass the benchmark's BarData (typically the traded symbol
    itself, or the broad market) to get a buy-and-hold comparison alongside
    each regime.
    """
    rows = []
    for regime in regimes:
        m = window_metrics(result, regime.start, regime.end)
        reasons = kill_verdict(m)
        benchmark_return = None
        benchmark_cagr = None
        if benchmark_data is not None:
            benchmark_return = _buy_hold_return(benchmark_data, regime.start, regime.end)
            if benchmark_return is not None:
                benchmark_cagr = cagr(benchmark_return, m.years)
        rows.append(
            RegimeRow(
                regime=regime.name,
                start=regime.start,
                end=regime.end,
                metrics=m,
                cagr=cagr(m.total_return, m.years),
                reasons=reasons,
                low_sample=m.trades < low_sample_trades,
                benchmark_total_return=benchmark_return,
                benchmark_cagr=benchmark_cagr,
            )
        )
    return rows
