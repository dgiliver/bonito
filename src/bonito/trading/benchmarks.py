"""Market-relative benchmarks: how did the account do against the market it trades in?

The fidelity check (`tracking`) grades the ledger only against its own replay, so a
strategy that tracks its replay perfectly while losing to the index reads "OK" —
exactly how the 2026-10 profitability review found live -12.4% vs SPY +3.2% with
tracking green. These are the scoreboards that question needs:

- SPY / QQQ: the cheap default you could hold instead.
- hold-universe: an equal-weight, daily-rebalanced hold of the universe's own
  symbols — what the stock list earns with no timing at all. A timing layer that
  trails it is subtracting value.

Report-only by construction: nothing here is imported by the trading path
(`generate_intents`, `preflight`, `reconcile`), and every failure degrades to
"n/a" rather than raising.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field

from bonito.trading.live_runner import UniverseConfig

logger = logging.getLogger(__name__)

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ")
HOLD_UNIVERSE = "hold-universe"
# hold-universe is only meaningful when most of the list has data — a container
# that refreshed just the open positions (the intraday sweep) must read "n/a",
# not a hold of 3 cherry-picked symbols.
MIN_UNIVERSE_COVERAGE = 0.5
# Benchmarks older than this (calendar days) read n/a — covers weekends + a holiday.
MAX_STALE_DAYS = 5


def _daily(bars) -> dict[date, float]:
    if bars is None:
        return {}
    return {ts.date(): float(c) for ts, c in zip(bars.timestamps, bars.closes, strict=True)}


def hold_universe_curve(
    closes: dict[str, dict[date, float]], days: list[date]
) -> dict[date, float]:
    """Equal-weight, daily-rebalanced hold of the symbols.

    Starts at 1.0 on ``days[0]``. Each day, every symbol with a close that day
    contributes its return from its LAST known close (so a missing bar doesn't drop
    the move across the gap); a symbol that lists mid-window joins from its first
    close. A day with no contributing symbol carries the previous value.
    """
    if not days:
        return {}
    last = {s: c[days[0]] for s, c in closes.items() if days[0] in c and c[days[0]] > 0}
    curve = {days[0]: 1.0}
    value = 1.0
    for cur in days[1:]:
        rets = []
        for s, c in closes.items():
            if cur not in c or c[cur] <= 0:
                continue
            if s in last:
                rets.append(c[cur] / last[s] - 1)
            last[s] = c[cur]
        if rets:
            value *= 1 + sum(rets) / len(rets)
        curve[cur] = value
    return curve


def window_return(series: dict[date, float], start: date, end: date) -> float | None:
    """Return from the first value on/after ``start`` to the last on/before ``end``."""
    inside = sorted(d for d in series if start <= d <= end)
    if len(inside) < 2 or series[inside[0]] <= 0:
        return None
    return series[inside[-1]] / series[inside[0]] - 1


def benchmark_series(
    store, universe: UniverseConfig, start: datetime, end: datetime
) -> dict[str, dict[date, float]]:
    """SPY, QQQ and hold-universe series over [start, end], keyed by calendar date.

    A benchmark with no stored data is simply absent from the result.
    """
    out: dict[str, dict[date, float]] = {}
    for symbol in BENCHMARK_SYMBOLS:
        try:
            series = _daily(store.get_bars(symbol, start, end, universe.data.timeframe))
        except Exception:
            logger.warning("benchmark %s unavailable", symbol, exc_info=True)
            series = {}
        if series:
            out[symbol] = series

    closes: dict[str, dict[date, float]] = {}
    for symbol in universe.symbols:
        try:
            series = _daily(store.get_bars(symbol, start, end, universe.data.timeframe))
        except Exception:
            series = {}
        if series:
            closes[symbol] = series
    if closes and len(closes) >= MIN_UNIVERSE_COVERAGE * len(universe.symbols):
        calendar = out.get("SPY") or {d: 0.0 for c in closes.values() for d in c}
        days = sorted(d for d in calendar if start.date() <= d <= end.date())
        if days:
            out[HOLD_UNIVERSE] = hold_universe_curve(closes, days)
    return out


class MarketComparison(BaseModel):
    """Account return vs each benchmark over the same window (percent / points)."""

    since: date
    until: date
    account_return_pct: float
    benchmark_return_pct: dict[str, float | None] = Field(default_factory=dict)
    excess_pts: dict[str, float | None] = Field(
        default_factory=dict, description="account minus benchmark, percentage points"
    )

    def line(self) -> str:
        """One-line summary, e.g. for `live status` and Routine reports."""
        bits = [f"account {self.account_return_pct:+.2f}%"]
        for label, ret in self.benchmark_return_pct.items():
            if ret is None:
                bits.append(f"{label} n/a")
            else:
                bits.append(f"{label} {ret:+.2f}% ({self.excess_pts[label]:+.2f}pts)")
        return f"vs market since {self.since:%Y-%m-%d} (positions at last close): " + " | ".join(
            bits
        )


def compare_to_market(
    account_return_pct: float,
    since: date,
    until: date,
    series: dict[str, dict[date, float]],
    labels: tuple[str, ...] = (*BENCHMARK_SYMBOLS, HOLD_UNIVERSE),
    max_stale_days: int = MAX_STALE_DAYS,
) -> MarketComparison:
    """Line the account's return up against every benchmark over [since, until].

    A benchmark whose data ends more than ``max_stale_days`` before ``until`` reads
    n/a: a frozen series (benchmark refresh failing) would otherwise silently show a
    shorter window as if it were current.
    """
    bench: dict[str, float | None] = {}
    excess: dict[str, float | None] = {}
    for label in labels:
        s = series.get(label, {})
        fresh = bool(s) and (until - max(s)).days <= max_stale_days
        ret = window_return(s, since, until) if fresh else None
        bench[label] = None if ret is None else round(ret * 100, 2)
        excess[label] = None if ret is None else round(account_return_pct - ret * 100, 2)
    return MarketComparison(
        since=since,
        until=until,
        account_return_pct=round(account_return_pct, 2),
        benchmark_return_pct=bench,
        excess_pts=excess,
    )


def ledger_market_comparison(
    ledger, store, universe: UniverseConfig, current_prices: dict[str, float], end: datetime
) -> MarketComparison | None:
    """Since-inception account return (equity vs starting cash) against the market.

    Benchmarks run from the close of the first fill's session — the same anchor as
    `live performance` (`paper_equity_curve` starts there). Fills land around the
    close, so the account never earned that session; crediting the benchmark with it
    would overstate the gap. None when the ledger has no fills yet.
    """
    if not ledger.fills:
        return None
    first = min(f.filled_at for f in ledger.fills).replace(tzinfo=None)
    since = first.date()
    # Mark positions without a live quote at their last stored close, not at entry
    # price (PaperLedger.equity's fallback), so an unpriced status still compares
    # like-for-like with the benchmarks' closes.
    prices = dict(current_prices)
    for symbol in ledger.positions:
        if symbol not in prices:
            try:
                closes = _daily(store.get_bars(symbol, first, end, universe.data.timeframe))
            except Exception:
                closes = {}
            if closes:
                prices[symbol] = closes[max(closes)]
    equity = ledger.equity(prices)
    account = (equity / ledger.starting_cash - 1) * 100 if ledger.starting_cash else 0.0
    # Query from before the first fill's DATE: bars are stamped 04:00/05:00, so asking
    # from the fill's own timestamp (e.g. 21:32) would drop that session's bar and
    # silently start the benchmarks a day late. window_return anchors on `since`.
    series = benchmark_series(
        store, universe, datetime.combine(since, datetime.min.time()) - timedelta(days=7), end
    )
    return compare_to_market(account, since, end.date(), series)


def refresh_benchmarks(
    universe: UniverseConfig, store, end: datetime | None = None
) -> dict[str, int]:
    """Ingest benchmark bars. NON-FATAL by contract: failures log and return -1.

    Deliberately separate from `refresh_data`, whose failures fail `live refresh`
    (and with it the paper workflow's whole cycle): a missing benchmark must never
    stop trading.
    """
    end = end or datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    results: dict[str, int] = {}
    for symbol in BENCHMARK_SYMBOLS:
        try:
            results[symbol] = store.ingest_from_yahoo(
                symbol,
                start=universe.data.start_date,
                end=end,
                timeframe=universe.data.timeframe,  # type: ignore[arg-type]
            )
        except Exception:
            logger.warning("benchmark refresh failed for %s", symbol, exc_info=True)
            results[symbol] = -1
    return results
