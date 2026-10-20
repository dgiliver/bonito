"""Tests for the live-Routine dead-man's switch (bonito.trading.routine_health)."""

import os
import subprocess
from datetime import date, datetime

import pytest

from bonito.trading.paper import PaperFill, PaperLedger
from bonito.trading.routine_health import (
    _require_history_reaches,
    check_routine_activity,
    commit_subjects_for_day,
)

DAY = date(2026, 10, 16)  # a Friday
GOOD = [
    "chore(livetrade): live cycle 2026-10-16",
    "chore(livetrade): cycle lock acquire (daily)",
    *[f"chore(livetrade): intraday live stop-check 2026-10-16T{h}:42Z" for h in range(13, 20)],
    *["chore(livetrade): cycle lock acquire (intraday)"] * 7,
]


def sentinel(on: datetime, symbol="QQQ", order_id="o-1", reason="no_fill: queued"):
    return PaperFill(
        symbol=symbol,
        side="buy",
        quantity=0.0,
        price=100.0,
        notional=0.0,
        reason=reason,
        filled_at=on,
        broker_order_id=order_id,
    )


class TestCheckRoutineActivity:
    def test_healthy_day_is_ok(self):
        r = check_routine_activity(
            GOOD, DAY, trading_day=True, ledger=PaperLedger(cash=1, starting_cash=1)
        )
        assert r.status == "OK" and r.daily_cycle_ran and r.intraday_runs == 7

    def test_missing_daily_cycle_alarms(self):
        """The 2026-10-16 outage: no daily commit at all."""
        subjects = [s for s in GOOD if "live cycle" not in s]
        r = check_routine_activity(subjects, DAY, trading_day=True)
        assert r.status == "ALARM" and not r.daily_cycle_ran
        assert any("no daily live cycle" in x for x in r.reasons)

    def test_too_few_intraday_runs_alarms(self):
        subjects = GOOD[:2] + GOOD[2:4]  # daily + 2 intraday runs
        r = check_routine_activity(subjects, DAY, trading_day=True, min_intraday=4)
        assert r.status == "ALARM" and r.intraday_runs == 2

    def test_lock_acquires_alone_do_not_count_as_runs(self):
        """A run that took the lock but never finished isn't coverage."""
        subjects = GOOD[:2] + ["chore(livetrade): cycle lock acquire (intraday)"] * 7
        assert check_routine_activity(subjects, DAY, trading_day=True).intraday_runs == 0

    def test_lock_release_commits_count_as_completed_runs(self):
        subjects = GOOD[:2] + [
            f"chore(livetrade): intraday lock release ({DAY}T1{h}:41Z)" for h in range(4)
        ]
        assert check_routine_activity(subjects, DAY, trading_day=True).intraday_runs == 4

    def test_other_days_commits_do_not_count(self):
        subjects = ["chore(livetrade): live cycle 2026-10-15"] + [
            f"chore(livetrade): intraday live stop-check 2026-10-15T{h}:42Z" for h in range(13, 20)
        ]
        r = check_routine_activity(subjects, DAY, trading_day=True)
        assert r.status == "ALARM" and not r.daily_cycle_ran and r.intraday_runs == 0

    def test_non_trading_day_is_skipped(self):
        r = check_routine_activity([], date(2026, 10, 17), trading_day=False)
        assert r.status == "SKIPPED"

    def test_stale_pending_order_alarms_but_fresh_one_does_not(self):
        ledger = PaperLedger(cash=1, starting_cash=1)
        ledger.fills.append(sentinel(datetime(2026, 10, 15, 20, 50)))  # 1 session old
        assert check_routine_activity(GOOD, DAY, trading_day=True, ledger=ledger).status == "OK"
        old = PaperLedger(cash=1, starting_cash=1)
        old.fills.append(sentinel(datetime(2026, 10, 12, 20, 50)))  # 4 sessions old
        r = check_routine_activity(GOOD, DAY, trading_day=True, ledger=old)
        assert r.status == "ALARM" and len(r.stale_pending) == 1

    def test_resolved_sentinel_is_not_pending(self):
        ledger = PaperLedger(cash=1, starting_cash=1)
        ledger.fills.append(sentinel(datetime(2026, 10, 1), reason="no_fill: x resolved=filled"))
        assert check_routine_activity(GOOD, DAY, trading_day=True, ledger=ledger).status == "OK"


class TestGitHistory:
    def repo(self, tmp_path, dates: list[str]):
        def git(*a, env=None):
            subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, env=env)

        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        for i, d in enumerate(dates):
            (tmp_path / "f").write_text(str(i))
            git("add", "f")
            env = {**os.environ, "GIT_COMMITTER_DATE": d, "GIT_AUTHOR_DATE": d}
            git("commit", "-q", "-m", f"chore(livetrade): live cycle {d[:10]}", env=env)
        return tmp_path

    def test_subjects_window_covers_the_day(self, tmp_path, monkeypatch):
        repo = self.repo(
            tmp_path, ["2026-10-15T20:50:00Z", "2026-10-16T20:50:00Z", "2026-10-17T15:00:00Z"]
        )
        monkeypatch.chdir(repo)
        subjects = commit_subjects_for_day(DAY)
        assert subjects == ["chore(livetrade): live cycle 2026-10-16"]

    def test_shallow_clone_that_misses_the_day_refuses(self, tmp_path, monkeypatch):
        (tmp_path / "src").mkdir()
        src = self.repo(
            tmp_path / "src",
            ["2026-10-10T20:50:00Z", "2026-10-15T20:50:00Z", "2026-10-16T20:50:00Z"],
        )
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", f"file://{src}", str(clone)],
            check=True,
            capture_output=True,
        )
        monkeypatch.chdir(clone)
        with pytest.raises(RuntimeError, match="shallow clone"):
            _require_history_reaches(datetime(2026, 10, 15), "HEAD")
