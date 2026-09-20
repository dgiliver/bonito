"""Read-only ledger liveness checks — alarm only, never gates trading.

This module is purely diagnostic. It is NEVER imported by
``bonito.trading.live_runner``, and is NEVER called from ``preflight``,
``generate_intents``, or ``execute_paper`` — a ledger health alarm must
never block, delay, or alter a trading decision. ``check_ledger_health``
only reads the ``PaperLedger`` object it is handed: it never touches the
``MarketDataStore``, never calls ``ledger.save()``, and never writes
anything under ``livetrade/``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
from pydantic import BaseModel

# Trading sessions with zero real (quantity > 0) fills before the ledger is flagged stale.
STALE_FILL_SESSIONS = 10
# Trading sessions with no cycle writing the ledger (`updated_at` unchanged) before it's flagged idle.
IDLE_UPDATE_SESSIONS = 3

_ET = ZoneInfo("America/New_York")


def _et_date(ts: datetime) -> date:
    """Trading-session date for a timestamp, in US/Eastern.

    Naive timestamps are assumed UTC — every timestamp written by
    ``PaperLedger`` comes from ``datetime.now(UTC)``.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_ET).date()


def sessions_between(start: date, end: date) -> int:
    """Approximate count of trading sessions in the interval ``(start, end]``.

    Uses ``numpy.busday_count`` (Mon-Fri, no holiday calendar) — good enough
    for an alarm threshold, not intended as an exact session count.
    """
    return int(np.busday_count(start + timedelta(days=1), end + timedelta(days=1)))


class LedgerHealthReport(BaseModel):
    """Read-only snapshot of ledger liveness. Advisory only — never gates trading."""

    status: Literal["OK", "ALARM"]
    mode: str
    ledger_path: str
    as_of: datetime
    halted: bool
    halt_reason: str = ""
    peak_equity: float | None
    cash: float
    open_positions: int
    total_fills: int
    last_fill_at: datetime | None
    last_activity_at: datetime | None
    sessions_since_fill: int | None
    fills_stale: bool = False
    stale_after_sessions: int
    updated_at: datetime | None
    sessions_since_update: int | None
    cycle_idle: bool = False
    idle_after_sessions: int
    reasons: list[str]

    def describe(self) -> str:
        """Human-readable, multi-line summary (for `Panel` display)."""
        lines = [
            f"[bold]{self.status}[/bold] — {self.mode} ledger ({self.ledger_path})",
            f"Halted: {self.halted}" + (f" — {self.halt_reason}" if self.halted else ""),
            f"Cash: ${self.cash:.2f} | Open positions: {self.open_positions} | "
            f"Total fills: {self.total_fills}",
        ]
        if self.last_fill_at is not None:
            lines.append(
                f"Last real fill: {self.last_fill_at.isoformat()} "
                f"({self.sessions_since_fill} session(s) ago, cap {self.stale_after_sessions})"
            )
        if self.updated_at is not None:
            lines.append(
                f"Last ledger update: {self.updated_at.isoformat()} "
                f"({self.sessions_since_update} session(s) ago, cap {self.idle_after_sessions})"
            )
        if self.reasons:
            lines.append("Reasons:\n" + "\n".join(f"  - {r}" for r in self.reasons))
        return "\n".join(lines)

    def status_line(self) -> str:
        """One-line, CI-readable summary."""
        last_fill = self.last_fill_at.date().isoformat() if self.last_fill_at else "never"
        return (
            f"HEALTH status={self.status} mode={self.mode} "
            f"halted={str(self.halted).lower()} "
            f"fills_stale={str(self.fills_stale).lower()} "
            f"cycle_idle={str(self.cycle_idle).lower()} "
            f"sessions_since_fill={self.sessions_since_fill} "
            f"last_fill={last_fill}"
        )


def check_ledger_health(
    ledger,
    *,
    mode: str = "paper",
    ledger_path: str = "",
    as_of: datetime | None = None,
    stale_after_sessions: int = STALE_FILL_SESSIONS,
    idle_after_sessions: int = IDLE_UPDATE_SESSIONS,
) -> LedgerHealthReport:
    """Read-only liveness check for a `PaperLedger`. Never mutates or saves it.

    Flags two independent conditions, on top of the kill switch, as ALARM:
      - `fills_stale`: no real (quantity > 0) fill for `stale_after_sessions`
        trading sessions — the strategy may have stopped signaling.
      - `cycle_idle`: no cycle has written the ledger for `idle_after_sessions`
        trading sessions — the scheduled job itself may have stopped running.
    """
    now = as_of or datetime.now(UTC)

    real_fills = [f for f in ledger.fills if f.quantity > 0]
    last_fill_at = max((f.filled_at for f in real_fills), default=None)
    last_activity_at = max((f.filled_at for f in ledger.fills), default=None)

    sessions_since_fill = (
        sessions_between(_et_date(last_fill_at), _et_date(now))
        if last_fill_at is not None
        else None
    )
    fills_stale = sessions_since_fill is not None and sessions_since_fill >= stale_after_sessions

    sessions_since_update = (
        sessions_between(_et_date(ledger.updated_at), _et_date(now))
        if ledger.updated_at is not None
        else None
    )
    cycle_idle = sessions_since_update is not None and sessions_since_update >= idle_after_sessions

    reasons: list[str] = []
    if ledger.halted:
        reasons.append(f"kill switch latched: {ledger.halt_reason}")
    if last_fill_at is None:
        reasons.append("no fills recorded yet — fill staleness not measurable")
    elif fills_stale:
        reasons.append(
            f"no fills for {sessions_since_fill} trading sessions (cap {stale_after_sessions})"
        )
    if cycle_idle:
        reasons.append(
            f"no cycle has written the ledger for {sessions_since_update} sessions "
            f"(cap {idle_after_sessions})"
        )

    status: Literal["OK", "ALARM"] = (
        "ALARM" if (ledger.halted or fills_stale or cycle_idle) else "OK"
    )

    return LedgerHealthReport(
        status=status,
        mode=mode,
        ledger_path=ledger_path,
        as_of=now,
        halted=ledger.halted,
        halt_reason=ledger.halt_reason,
        peak_equity=ledger.peak_equity,
        cash=ledger.cash,
        open_positions=len(ledger.positions),
        total_fills=len(ledger.fills),
        last_fill_at=last_fill_at,
        last_activity_at=last_activity_at,
        sessions_since_fill=sessions_since_fill,
        fills_stale=fills_stale,
        stale_after_sessions=stale_after_sessions,
        updated_at=ledger.updated_at,
        sessions_since_update=sessions_since_update,
        cycle_idle=cycle_idle,
        idle_after_sessions=idle_after_sessions,
        reasons=reasons,
    )
