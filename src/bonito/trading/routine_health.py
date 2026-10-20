"""Did the live Routines actually run? A dead-man's switch for the live account.

2026-10-20: Robinhood renamed the Agentic account's nickname to "MCP"; both Routines
asserted the old nickname in step 1 and stopped BEFORE taking the cycle lock — so
they left no commit, no alert, and their run status still read SUCCEEDED. Four
trading days passed with no daily cycle and almost no stop checks before anyone
noticed. `bonito live health` couldn't see it: it only runs in the paper workflow,
and the live ledger's `updated_at` can stay fresh from a single intraday run.

This module checks the evidence each Routine leaves behind on `main`:

- daily cycle: a commit "chore(livetrade): live cycle <day>"
- intraday stop checks: completed runs ("intraday live stop-check <day>T..." or
  "intraday lock release (<day>T..."), at least ``min_intraday`` of them
- pending orders: no queued-order sentinel older than ``stale_pending_sessions``
  sessions (the daily cycle's resolve-pending step should have healed it)

Alarm-only by construction: never imported by the trading path.
"""

import subprocess
from datetime import date, datetime, timedelta
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from bonito.trading.paper import PaperLedger

MIN_INTRADAY_RUNS = 4  # of ~7 scheduled per session; tolerates a couple of lock contentions
STALE_PENDING_SESSIONS = 2


class RoutineHealthReport(BaseModel):
    day: date
    status: Literal["OK", "ALARM", "SKIPPED"]
    trading_day: bool
    daily_cycle_ran: bool = False
    intraday_runs: int = 0
    min_intraday: int = MIN_INTRADAY_RUNS
    stale_pending: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    def status_line(self) -> str:
        return (
            f"ROUTINE_HEALTH status={self.status} day={self.day} "
            f"daily_cycle={str(self.daily_cycle_ran).lower()} "
            f"intraday_runs={self.intraday_runs}/{self.min_intraday} "
            f"stale_pending={len(self.stale_pending)}"
        )


def _is_pending_sentinel(fill) -> bool:
    return (
        fill.quantity == 0 and bool(fill.broker_order_id) and "resolved=" not in (fill.reason or "")
    )


def check_routine_activity(
    subjects: list[str],
    day: date,
    *,
    trading_day: bool,
    ledger: PaperLedger | None = None,
    min_intraday: int = MIN_INTRADAY_RUNS,
    stale_pending_sessions: int = STALE_PENDING_SESSIONS,
) -> RoutineHealthReport:
    """Judge one session's Routine activity from commit subjects on main."""
    if not trading_day:
        return RoutineHealthReport(day=day, status="SKIPPED", trading_day=False,
                                   min_intraday=min_intraday,
                                   reasons=["not a trading day"])  # fmt: skip
    iso = day.isoformat()
    daily = any(f"live cycle {iso}" in s for s in subjects)
    intraday = sum(
        1
        for s in subjects
        if f"intraday live stop-check {iso}T" in s or f"intraday lock release ({iso}T" in s
    )
    stale: list[str] = []
    if ledger is not None:
        for f in ledger.fills:
            if not _is_pending_sentinel(f):
                continue
            queued = f.filled_at.date()
            if int(np.busday_count(queued, day)) > stale_pending_sessions:
                stale.append(f"{f.side} {f.symbol} queued {queued} (order {f.broker_order_id})")

    reasons = []
    if not daily:
        reasons.append(f"no daily live cycle commit for {iso}")
    if intraday < min_intraday:
        reasons.append(f"only {intraday} intraday stop-check run(s) on {iso} (< {min_intraday})")
    if stale:
        reasons.append(
            f"{len(stale)} queued order(s) unresolved for > {stale_pending_sessions} sessions"
        )
    return RoutineHealthReport(
        day=day,
        status="ALARM" if reasons else "OK",
        trading_day=True,
        daily_cycle_ran=daily,
        intraday_runs=intraday,
        min_intraday=min_intraday,
        stale_pending=stale,
        reasons=reasons,
    )


def commit_subjects_for_day(day: date, ref: str = "HEAD") -> list[str]:
    """Commit subjects on ``ref`` from ``day`` 00:00 UTC to next day 12:00 UTC.

    The window runs past midnight because the daily cycle commits around 20:50 UTC
    and its subject carries the session date regardless of when it lands.
    """
    since = datetime.combine(day, datetime.min.time())
    until = since + timedelta(days=1, hours=12)
    _require_history_reaches(since, ref)
    out = subprocess.run(
        ["git", "log", ref, f"--since={since.isoformat()}Z", f"--until={until.isoformat()}Z",
         "--format=%s"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return [line for line in out.stdout.splitlines() if line.strip()]


def _require_history_reaches(since: datetime, ref: str) -> None:
    """Refuse to judge a day a SHALLOW clone doesn't cover.

    A truncated history makes runs look missing (a false ALARM); the CI workflow
    checks out full history, and this guard makes any other caller fail loudly.
    """
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if shallow != "true":
        return
    oldest = subprocess.run(
        ["git", "log", ref, "--reverse", "--format=%cI"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    if not oldest or datetime.fromisoformat(oldest[0]).replace(tzinfo=None) > since:
        raise RuntimeError(
            f"shallow clone history starts {oldest[0] if oldest else '?'} — after {since:%F}; "
            "run `git fetch --unshallow` (or fetch-depth: 0 in CI)"
        )
