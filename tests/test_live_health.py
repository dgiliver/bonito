"""Tests for bonito.trading.health (D2) and the resume/health CLI (D1+D2).

Section C: unit tests directly against `check_ledger_health()` / `sessions_between()`.
Always pass an explicit `as_of` — never rely on wall-clock `datetime.now()`.

Section D: CLI tests for `bonito live health` and `bonito live resume`, run
against a hermetic tmp_path universe/ledger (`monkeypatch.chdir`), never
touching the repo's real `config/` or `livetrade/`.

Section E: the `--json` contract test doubles as the CI-readable interface
`paper-trading.yml` depends on to decide whether to open an issue.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from bonito.cli import app
from bonito.trading.health import check_ledger_health, sessions_between
from bonito.trading.paper import PaperFill, PaperLedger, PaperPosition

runner = CliRunner()


def _fill(quantity: float, filled_at: datetime, symbol: str = "AAA") -> PaperFill:
    return PaperFill(
        symbol=symbol,
        side="buy",
        quantity=quantity,
        price=100.0,
        notional=quantity * 100.0,
        reason="test",
        filled_at=filled_at,
        strategy_name="test",
    )


class TestSessionsBetween:
    """Verified vectors from the D2 spec — pins the exact business-day arithmetic."""

    def test_vectors(self):
        assert sessions_between(datetime(2026, 8, 18).date(), datetime(2026, 9, 20).date()) == 23
        assert sessions_between(datetime(2026, 9, 18).date(), datetime(2026, 9, 21).date()) == 1
        assert sessions_between(datetime(2026, 9, 18).date(), datetime(2026, 9, 19).date()) == 0
        assert sessions_between(datetime(2026, 8, 18).date(), datetime(2026, 9, 1).date()) == 10
        assert sessions_between(datetime(2026, 7, 2).date(), datetime(2026, 7, 6).date()) == 2


class TestCheckLedgerHealth:
    def test_halted_ledger_alarms(self):
        ledger = PaperLedger(
            cash=100.0,
            starting_cash=150.0,
            halted=True,
            halt_reason="drawdown 30.0% >= 25% cap",
        )
        ledger.fills.append(_fill(1.0, datetime(2026, 9, 19, 15, 0, tzinfo=UTC)))

        report = check_ledger_health(ledger, as_of=datetime(2026, 9, 20, 15, 0, tzinfo=UTC))

        assert report.status == "ALARM"
        assert report.halted is True
        assert report.fills_stale is False
        assert any("kill switch" in r for r in report.reasons)

    def test_no_fills_for_more_than_n_sessions_alarms(self):
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        ledger.fills.append(_fill(1.0, datetime(2026, 8, 18, 15, 0, tzinfo=UTC)))

        report = check_ledger_health(
            ledger,
            as_of=datetime(2026, 9, 20, 15, 0, tzinfo=UTC),
            stale_after_sessions=10,
        )

        assert report.sessions_since_fill == 23
        assert report.fills_stale is True
        assert report.status == "ALARM"

    def test_recently_trading_ledger_is_ok(self):
        """False-positive guard: a strategy that traded yesterday must not alarm."""
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        ledger.fills.append(_fill(1.0, datetime(2026, 9, 17, 15, 0, tzinfo=UTC)))

        report = check_ledger_health(ledger, as_of=datetime(2026, 9, 18, 15, 0, tzinfo=UTC))

        assert report.sessions_since_fill == 1
        assert report.status == "OK"
        assert report.reasons == []

    def test_weekend_gap_is_not_stale(self):
        """Fri fill -> Mon as_of is one trading session, not three calendar days.

        A calendar-day implementation ((end - start).days) would report 3 and
        false-alarm against stale_after_sessions=2.
        """
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        ledger.fills.append(_fill(1.0, datetime(2026, 9, 18, 15, 0, tzinfo=UTC)))  # Friday

        report = check_ledger_health(
            ledger,
            as_of=datetime(2026, 9, 21, 15, 0, tzinfo=UTC),  # Monday
            stale_after_sessions=2,
        )

        assert report.sessions_since_fill == 1
        assert report.status == "OK"
        assert report.fills_stale is False

    def test_fill_timestamp_uses_et_session_date(self):
        """01:37 UTC on 8/7 is 21:37 ET on 8/6 — must land in the prior ET
        session, not the raw UTC calendar date (which would make it 0)."""
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        ledger.fills.append(_fill(1.0, datetime(2026, 8, 7, 1, 37, 33, tzinfo=UTC)))

        report = check_ledger_health(ledger, as_of=datetime(2026, 8, 7, 20, 0, tzinfo=UTC))

        assert report.sessions_since_fill == 1

    def test_ledger_with_no_fills_does_not_false_alarm(self):
        """A brand-new ledger has no fills to be stale about — that's a
        distinct, named blind spot, not a false ALARM."""
        as_of = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0, updated_at=as_of - timedelta(hours=1))

        report = check_ledger_health(ledger, as_of=as_of)

        assert report.sessions_since_fill is None
        assert report.fills_stale is False
        assert any("no fills" in r for r in report.reasons)

    def test_zero_quantity_sentinels_do_not_count_as_fills(self):
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        ledger.fills.append(_fill(1.0, datetime(2026, 8, 18, 15, 0, tzinfo=UTC)))
        sentinel = _fill(0.0, datetime(2026, 9, 18, 15, 0, tzinfo=UTC))
        ledger.fills.append(sentinel)

        report = check_ledger_health(ledger, as_of=datetime(2026, 9, 20, 15, 0, tzinfo=UTC))

        assert report.fills_stale is True
        assert report.last_activity_at == sentinel.filled_at

    def test_idle_cycle_alarms_independently(self):
        ledger = PaperLedger(
            cash=100.0,
            starting_cash=150.0,
            updated_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
        )
        ledger.fills.append(_fill(1.0, datetime(2026, 9, 17, 15, 0, tzinfo=UTC)))

        report = check_ledger_health(
            ledger,
            as_of=datetime(2026, 9, 21, 15, 0, tzinfo=UTC),
            idle_after_sessions=3,
        )

        assert report.cycle_idle is True
        assert report.fills_stale is False
        assert report.status == "ALARM"


# ---------------------------------------------------------------------------
# CLI tests — `bonito live health` / `bonito live resume`
# ---------------------------------------------------------------------------


def _write_universe(tmp_path, mode: str = "paper", filename: str = "config/universe.json"):
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "name": "cli_test",
                "symbols": ["AAA"],
                "strategy_path": "unused_strategy.json",
                "mode": mode,
                "live_enabled": True,
            }
        )
    )
    return path


def _write_ledger(tmp_path, mode: str = "paper", **kwargs) -> tuple[object, object]:
    ledger_dir = tmp_path / "livetrade"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"{mode}_ledger.json"
    ledger = PaperLedger(**kwargs)
    ledger.save(path)
    return ledger, path


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestHealthCLI:
    def test_health_exits_3_on_halted_ledger(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _write_ledger(
            tmp_path,
            cash=100.0,
            starting_cash=150.0,
            halted=True,
            halt_reason="drawdown 30% >= 25% cap",
        )

        result = runner.invoke(app, ["live", "health", "-u", "config/universe.json"])

        assert result.exit_code == 3

    def test_health_exits_0_on_healthy_ledger(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        ledger, path = _write_ledger(tmp_path, cash=150.0, starting_cash=150.0)
        ledger.fills.append(_fill(1.0, datetime.now(UTC)))
        ledger.save(path)

        result = runner.invoke(app, ["live", "health", "-u", "config/universe.json"])

        assert result.exit_code == 0

    def test_health_json_is_parseable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _write_ledger(
            tmp_path,
            cash=100.0,
            starting_cash=150.0,
            halted=True,
            halt_reason="drawdown 30% >= 25% cap",
        )

        result = runner.invoke(app, ["live", "health", "-u", "config/universe.json", "--json"])

        assert result.exit_code == 3
        payload = json.loads(result.stdout)
        assert payload["status"] == "ALARM"
        for key in ("halted", "fills_stale", "cycle_idle", "sessions_since_fill"):
            assert key in payload

    def test_health_selects_ledger_by_universe_mode(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path, mode="live", filename="config/universe.live.json")
        # Paper ledger is halted — must NOT be the one consulted.
        _write_ledger(
            tmp_path,
            mode="paper",
            cash=100.0,
            starting_cash=150.0,
            halted=True,
            halt_reason="drawdown 30% >= 25% cap",
        )
        live_ledger, live_path = _write_ledger(
            tmp_path, mode="live", cash=150.0, starting_cash=150.0
        )
        live_ledger.fills.append(_fill(1.0, datetime.now(UTC)))
        live_ledger.save(live_path)

        result = runner.invoke(app, ["live", "health", "-u", "config/universe.live.json"])

        assert result.exit_code == 0

    def test_health_exits_1_when_ledger_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        # No livetrade/ directory at all.

        result = runner.invoke(app, ["live", "health", "-u", "config/universe.json"])

        assert result.exit_code == 1

    def test_health_leaves_the_ledger_file_untouched(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _, path = _write_ledger(
            tmp_path,
            cash=100.0,
            starting_cash=150.0,
            halted=True,
            halt_reason="drawdown 30% >= 25% cap",
        )
        before = _sha256(path)

        runner.invoke(app, ["live", "health", "-u", "config/universe.json"])

        assert _sha256(path) == before


class TestResumeCLI:
    def test_resume_preview_without_yes_changes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _, path = _write_ledger(
            tmp_path,
            cash=100.0,
            starting_cash=150.0,
            peak_equity=200.0,
            halted=True,
            halt_reason="drawdown 50% >= 25% cap",
        )
        before = _sha256(path)

        result = runner.invoke(app, ["live", "resume", "-u", "config/universe.json"])

        assert result.exit_code == 1
        assert _sha256(path) == before
        assert "--yes" in result.output

    def test_resume_yes_rebaselines_peak_in_saved_ledger(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _, path = _write_ledger(
            tmp_path,
            cash=4468.86,
            starting_cash=5000.0,
            peak_equity=6004.60,
            halted=True,
            halt_reason="drawdown 25.6% >= 25% cap",
        )

        result = runner.invoke(app, ["live", "resume", "-u", "config/universe.json", "--yes"])

        assert result.exit_code == 0
        reloaded = PaperLedger.load(path)
        assert reloaded.halted is False
        assert reloaded.peak_equity == pytest.approx(4468.86)

    def test_resume_keep_peak_preserves_old_behaviour(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _, path = _write_ledger(
            tmp_path,
            cash=100.0,
            starting_cash=150.0,
            peak_equity=200.0,  # 50% drawdown at cash=100 — will re-halt next cycle
            halted=True,
            halt_reason="drawdown 50% >= 25% cap",
        )

        result = runner.invoke(
            app, ["live", "resume", "-u", "config/universe.json", "--yes", "--keep-peak"]
        )

        assert result.exit_code == 0
        reloaded = PaperLedger.load(path)
        assert reloaded.halted is False
        assert reloaded.peak_equity == 200.0
        assert "re-halt" in result.output.lower()

    def test_resume_on_healthy_ledger_does_not_rebaseline(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        _, path = _write_ledger(tmp_path, cash=150.0, starting_cash=150.0)
        before = _sha256(path)

        result = runner.invoke(app, ["live", "resume", "-u", "config/universe.json", "--yes"])

        assert result.exit_code == 0
        assert _sha256(path) == before

    def test_resume_aborts_when_a_position_cannot_be_priced(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_universe(tmp_path)
        ledger, path = _write_ledger(
            tmp_path,
            cash=0.0,
            starting_cash=150.0,
            peak_equity=200.0,
            halted=True,
            halt_reason="drawdown 50% >= 25% cap",
        )
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA",
            quantity=1.0,
            entry_price=100.0,
            entry_date=datetime.now(UTC),
            high_water_mark=100.0,
        )
        ledger.save(path)
        before = _sha256(path)

        monkeypatch.setattr("bonito.data.quotes.fetch_latest_quotes", lambda symbols: {})

        result = runner.invoke(app, ["live", "resume", "-u", "config/universe.json", "--yes"])

        assert result.exit_code == 1
        assert _sha256(path) == before
