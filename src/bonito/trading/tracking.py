"""Paper-vs-replay tracking: continuously verify the simulation against reality.

Everything in the autonomous loop trusts the account replay — the weekly
gate, the adopted optimizations, the headline backtest numbers. This module
closes the last unverified link by comparing what the PAPER LEDGER actually
did (real fill prices from the daily cycle and intraday sweeps, real
timing, real data quirks) against what the replay says the same pipeline
should have done over the same window.

Two layers of comparison:

- **Fill-level fidelity** (primary, robust to config changes): every paper
  fill is matched to the replay's fill on the same (symbol, side, ~date);
  the price deltas in basis points measure execution fidelity. Paper fills
  with no replay counterpart are DECISION divergences (the live pipeline
  traded when the replay wouldn't, or vice versa) — those are worse than
  price noise and are counted separately.
- **Equity-level gap** (headline, noisier): the paper ledger's daily
  equity curve, reconstructed from its fills marked at stored closes, vs
  the replay's curve over the same window. Early on this includes
  config-change artifacts (the paper history spans config versions; the
  replay runs the CURRENT config) — fill fidelity is the signal to trust
  until the post-change history dominates.

The weekly workflow runs this after research and opens an issue only when
status is WARN — silence means the simulation is tracking reality.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from bonito.trading.live_runner import UniverseConfig
from bonito.trading.paper import PaperFill, PaperLedger
from bonito.trading.portfolio_backtest import (
    AccountBacktestResult,
    ReplayStore,
    backtest_account,
)

logger = logging.getLogger(__name__)

# A paper fill and a replay fill refer to the same decision when they share
# symbol/side and land within this many calendar days (the daily cycle can
# fill a signal the replay dates one bar earlier/later around weekends).
MATCH_TOLERANCE_DAYS = 1

# WARN thresholds — breaching any flips the weekly status.
MAX_MEAN_FILL_BPS = 50.0  # mean |paper - replay| fill price gap (paper mode)
MAX_MEAN_FILL_BPS_LIVE = 50.0  # mean fill gap for live mode (equal for now — RFC D2;
#   recalibrate from rehearsal data before scaling size)
MAX_DECISION_DIVERGENCE = 0.20  # share of paper fills with no replay match
MAX_EQUITY_GAP_PCT = 3.0  # |paper - replay| final equity, % of replay
# Below this many matched fills the comparison is statistically meaningless —
# a single intraday-vs-close outlier dominates the mean (observed 2026-06-12:
# 5 fills, worst 944bps, all explained by config churn + fill timing).
MIN_MATCHED_FILLS = 10


class FillComparison(BaseModel):
    """One paper fill matched (or not) against the replay."""

    symbol: str
    side: str
    paper_date: datetime
    paper_price: float
    replay_price: float | None = None
    delta_bps: float | None = None
    matched: bool


class TrackingReport(BaseModel):
    """One paper-vs-replay verification — the weekly fidelity record."""

    generated_at: datetime
    window_start: datetime
    window_end: datetime
    status: Literal["OK", "WARN", "INSUFFICIENT"]
    reasons: list[str] = Field(default_factory=list)

    paper_fills: int
    matched_fills: int
    no_fill_count: int = Field(
        default=0, description="Number of zero-qty (no_fill) events in the ledger"
    )
    decision_divergence: float = Field(
        ..., description="Share of paper fills with no replay counterpart"
    )
    mean_abs_fill_bps: float | None = None
    median_abs_fill_bps: float | None = None
    worst_fill_bps: float | None = None

    paper_final_equity: float
    replay_final_equity: float
    equity_gap_pct: float
    mean_daily_tracking_error_bps: float | None = None

    fills: list[FillComparison] = Field(default_factory=list)


def replay_fill_events(result: AccountBacktestResult) -> list[tuple[str, str, datetime, float]]:
    """Flatten the replay into (symbol, side, date, price) fill events."""
    events: list[tuple[str, str, datetime, float]] = []
    for t in result.trades:
        events.append((t.symbol.upper(), "buy", t.entry_date, t.entry_price))
        events.append((t.symbol.upper(), "sell", t.exit_date, t.exit_price))
    for symbol, pos in result.open_position_entries.items():
        events.append((symbol.upper(), "buy", pos.entry_date, pos.entry_price))
    return events


def match_fills(
    paper_fills: list[PaperFill],
    replay_events: list[tuple[str, str, datetime, float]],
) -> list[FillComparison]:
    """Greedily pair each paper fill with the nearest unconsumed replay event.

    Pairing key is (symbol, side) within MATCH_TOLERANCE_DAYS; each replay
    event is consumed at most once so repeated round trips in the same
    symbol pair off one-to-one in date order.
    """
    pool: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for symbol, side, date, price in replay_events:
        pool.setdefault((symbol, side), []).append((date, price))
    for events in pool.values():
        events.sort()

    comparisons: list[FillComparison] = []
    tolerance = timedelta(days=MATCH_TOLERANCE_DAYS)
    for fill in sorted(paper_fills, key=lambda f: f.filled_at):
        key = (fill.symbol.upper(), fill.side)
        candidates = pool.get(key, [])
        paper_day = fill.filled_at.replace(tzinfo=None)
        best_i: int | None = None
        best_gap: timedelta | None = None
        for i, (date, _) in enumerate(candidates):
            gap = abs(date - paper_day)
            if gap <= tolerance and (best_gap is None or gap < best_gap):
                best_i, best_gap = i, gap
        if best_i is None:
            comparisons.append(
                FillComparison(
                    symbol=fill.symbol,
                    side=fill.side,
                    paper_date=paper_day,
                    paper_price=fill.price,
                    matched=False,
                )
            )
            continue
        _, replay_price = candidates.pop(best_i)
        delta_bps = (fill.price - replay_price) / replay_price * 10_000
        comparisons.append(
            FillComparison(
                symbol=fill.symbol,
                side=fill.side,
                paper_date=paper_day,
                paper_price=fill.price,
                replay_price=replay_price,
                delta_bps=round(delta_bps, 2),
                matched=True,
            )
        )
    return comparisons


def paper_equity_curve(
    ledger: PaperLedger,
    store,
    universe: UniverseConfig,
    end: datetime,
) -> tuple[list[datetime], list[float]]:
    """Reconstruct the ledger's daily equity from its fills and stored closes.

    Walks each trading day from the first fill: applies that day's fills to
    cash/positions, then marks open positions at the day's stored close
    (carrying the last known close across gaps).
    """
    if not ledger.fills:
        return [], []
    fills = sorted(ledger.fills, key=lambda f: f.filled_at)
    first_day = fills[0].filled_at.replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")

    symbols = sorted({f.symbol.upper() for f in fills})
    bars = {s: store.get_bars(s, start, end, universe.data.timeframe) for s in symbols}
    closes: dict[str, dict[datetime, float]] = {
        s: dict(zip(b.timestamps, b.closes, strict=True)) for s, b in bars.items() if b is not None
    }
    trading_days = sorted(
        {d for c in closes.values() for d in c if first_day <= d <= end} | {first_day}
    )

    cash = ledger.starting_cash
    positions: dict[str, float] = {}
    last_close: dict[str, float] = {}
    fill_i = 0
    dates: list[datetime] = []
    equity: list[float] = []
    for day in trading_days:
        day_cutoff = day + timedelta(days=1)
        while fill_i < len(fills) and fills[fill_i].filled_at.replace(tzinfo=None) < day_cutoff:
            f = fills[fill_i]
            fill_i += 1
            # D3: zero-qty no_fill sentinels carry no cash/position change.
            if f.quantity == 0:
                continue
            sym = f.symbol.upper()
            if f.side == "buy":
                cash -= f.notional
                positions[sym] = positions.get(sym, 0.0) + f.quantity
            else:
                cash += f.notional
                positions[sym] = positions.get(sym, 0.0) - f.quantity
                if abs(positions[sym]) < 1e-9:
                    del positions[sym]
            last_close.setdefault(sym, f.price)
        for sym in positions:
            price = closes.get(sym, {}).get(day)
            if price is not None:
                last_close[sym] = price
        dates.append(day)
        equity.append(cash + sum(q * last_close.get(s, 0.0) for s, q in positions.items()))
    return dates, equity


def run_tracking(
    universe: UniverseConfig,
    ledger: PaperLedger,
    store,
    end: datetime | None = None,
) -> TrackingReport:
    """Compare the paper ledger against a replay of the same window."""
    end = end or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # D3: separate zero-qty no_fill sentinel events before any comparison.
    # They are NOT passed to match_fills (keeps match_fills pure) and are
    # NOT applied to the equity reconstruction in paper_equity_curve.
    no_fill_events = [f for f in ledger.fills if f.quantity == 0]
    real_fills = [f for f in ledger.fills if f.quantity != 0]
    no_fill_count = len(no_fill_events)

    if not real_fills:
        # backtest_account() raises on an empty/zero-width window, so a
        # ledger with only no_fill sentinels (no real fills yet) must be
        # caught here rather than falling through — same as the
        # genuinely-empty-ledger case, just with the no_fill count reported.
        insufficient_reasons = ["paper ledger has no fills yet"]
        if no_fill_count:
            insufficient_reasons = [
                f"paper ledger has no real fills yet ({no_fill_count} no_fill event(s) recorded)"
            ]
        return TrackingReport(
            generated_at=datetime.now(),
            window_start=end,
            window_end=end,
            status="INSUFFICIENT",
            reasons=insufficient_reasons,
            paper_fills=0,
            matched_fills=0,
            no_fill_count=no_fill_count,
            decision_divergence=0.0,
            paper_final_equity=ledger.starting_cash,
            replay_final_equity=ledger.starting_cash,
            equity_gap_pct=0.0,
        )

    # D2: use the live band when the universe is in live mode.
    mean_band = MAX_MEAN_FILL_BPS_LIVE if universe.mode == "live" else MAX_MEAN_FILL_BPS

    # Rebuild a ledger-like object with only real fills for the equity curve.
    # We pass a filtered ledger view rather than mutating the real ledger.
    class _FilteredLedger:
        def __init__(self, src: PaperLedger, fills: list) -> None:
            self.fills = fills
            self.starting_cash = src.starting_cash

    filtered_ledger = _FilteredLedger(ledger, real_fills)

    window_start = (
        min(f.filled_at for f in real_fills).replace(
            tzinfo=None, hour=0, minute=0, second=0, microsecond=0
        )
        if real_fills
        else end
    )

    replay = ReplayStore.from_store(store, universe, end)
    result = backtest_account(universe, replay, window_start, end)

    comparisons = match_fills(real_fills, replay_fill_events(result))
    matched = [c for c in comparisons if c.matched]
    deltas = np.array([abs(c.delta_bps) for c in matched]) if matched else np.array([])
    divergence = 1 - len(matched) / len(comparisons) if comparisons else 0.0

    paper_dates, paper_equity = paper_equity_curve(
        filtered_ledger,  # type: ignore[arg-type]
        store,
        universe,
        end,
    )
    paper_final = paper_equity[-1] if paper_equity else ledger.starting_cash
    replay_final = result.final_equity
    equity_gap_pct = (paper_final - replay_final) / replay_final * 100 if replay_final else 0.0

    te_bps: float | None = None
    replay_by_date = dict(zip(result.equity_dates, result.equity_curve, strict=True))
    common = [
        (p, replay_by_date[d])
        for d, p in zip(paper_dates, paper_equity, strict=True)
        if d in replay_by_date
    ]
    if len(common) > 1:
        diffs = [abs(p - r) / r * 10_000 for p, r in common if r]
        te_bps = round(float(np.mean(diffs)), 1)

    reasons: list[str] = []
    if no_fill_count:
        reasons.append(f"{no_fill_count} no_fill event(s) recorded in the ledger")

    if len(matched) < MIN_MATCHED_FILLS:
        status: Literal["OK", "WARN", "INSUFFICIENT"] = "INSUFFICIENT"
        reasons.append(f"only {len(matched)} matched fills (<{MIN_MATCHED_FILLS})")
    else:
        status = "OK"
        if float(np.mean(deltas)) > mean_band:
            status = "WARN"
            # D2: name the band in the reason so live vs paper is clear.
            band_label = "live band" if universe.mode == "live" else "paper band"
            reasons.append(
                f"mean fill gap {np.mean(deltas):.0f}bps > {mean_band:.0f}bps ({band_label})"
            )
        if divergence > MAX_DECISION_DIVERGENCE:
            status = "WARN"
            reasons.append(f"decision divergence {divergence:.0%} > {MAX_DECISION_DIVERGENCE:.0%}")
        if abs(equity_gap_pct) > MAX_EQUITY_GAP_PCT:
            status = "WARN"
            reasons.append(
                f"equity gap {equity_gap_pct:+.1f}% > ±{MAX_EQUITY_GAP_PCT:.0f}% "
                "(config changes during the paper window inflate this early on)"
            )

    return TrackingReport(
        generated_at=datetime.now(),
        window_start=window_start,
        window_end=end,
        status=status,
        reasons=reasons,
        paper_fills=len(comparisons),
        matched_fills=len(matched),
        no_fill_count=no_fill_count,
        decision_divergence=round(divergence, 4),
        mean_abs_fill_bps=round(float(np.mean(deltas)), 1) if len(deltas) else None,
        median_abs_fill_bps=round(float(np.median(deltas)), 1) if len(deltas) else None,
        worst_fill_bps=round(float(np.max(deltas)), 1) if len(deltas) else None,
        paper_final_equity=round(paper_final, 2),
        replay_final_equity=round(replay_final, 2),
        equity_gap_pct=round(equity_gap_pct, 2),
        mean_daily_tracking_error_bps=te_bps,
        fills=comparisons,
    )


def save_tracking_report(
    report: TrackingReport, directory: Path = Path("livetrade/research")
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"tracking_{report.generated_at.strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(report.model_dump_json(indent=2))
    return path
