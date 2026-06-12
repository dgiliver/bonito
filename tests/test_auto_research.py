"""Tests for the autonomous research cycle (bonito.research.auto_research)."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bonito.research import auto_research
from bonito.research.auto_research import (
    HOLDOUT_DAYS,
    build_candidate_map,
    decide_adoption,
    rolling_windows,
    run_auto_research,
)
from bonito.research.cluster_research import ClusterResult, ResearchReport
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import AccountBacktestResult

START = datetime(2022, 1, 1)
HOLDOUT = datetime(2024, 12, 10)
END = datetime(2026, 6, 12)

BASE_STRATEGY = {
    "name": "default",
    "symbols": ["SPY"],
    "timeframe": "1d",
    "indicators": [{"type": "sma", "name": "sma_2", "params": {"period": 2}}],
    "entry_rules": [
        {
            "conditions": [{"left": "close", "comparison": "gt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
    "exit_rules": [],
}


def fake_result(
    train_sharpe: float,
    holdout_sharpe: float,
    train_failures: list[str] | None = None,
    holdout_failures: list[str] | None = None,
) -> AccountBacktestResult:
    """An AccountBacktestResult whose window methods return canned values."""
    result = AccountBacktestResult(
        universe_name="t",
        start=START,
        end=END,
        starting_cash=5000.0,
        final_equity=6000.0,
        total_return=0.2,
        realized_pnl=1000.0,
        unrealized_pnl=0.0,
        equity_dates=[START, END],
        equity_curve=[5000.0, 6000.0],
        max_drawdown=0.1,
        sharpe=1.0,
        trades=[],
        win_rate=0.5,
        profit_factor=1.5,
        max_concurrent_positions=1,
        avg_concurrent_positions=1.0,
        pct_days_in_market=0.5,
        halted=False,
        halt_date=None,
        halt_reason="",
        open_positions={},
        per_symbol_pnl={},
        rejected_intents=0,
    )

    sharpes = {"train": train_sharpe, "holdout": holdout_sharpe}
    failures = {"train": train_failures or [], "holdout": holdout_failures or []}

    def window_for(start: datetime) -> str:
        return "train" if start == START else "holdout"

    object.__setattr__(
        result,
        "window_metrics",
        lambda s, e: type("M", (), {"sharpe": sharpes[window_for(s)], "total_return": 0.1})(),
    )
    object.__setattr__(result, "verdict", lambda s, e: failures[window_for(s)])
    return result


class TestRollingWindows:
    def make_universe(self, tmp_path, start_date: str) -> UniverseConfig:
        path = tmp_path / "s.json"
        path.write_text(json.dumps(BASE_STRATEGY))
        return UniverseConfig(
            name="t",
            symbols=["AAA"],
            strategy_path=str(path),
            data={"timeframe": "1d", "start_date": start_date},
        )

    def test_holdout_tracks_end_date(self, tmp_path):
        universe = self.make_universe(tmp_path, "2022-01-01")
        start, holdout, end = rolling_windows(universe, END)
        assert holdout == END - timedelta(days=HOLDOUT_DAYS)
        assert start == datetime(2022, 1, 1)

    def test_short_train_window_raises(self, tmp_path):
        universe = self.make_universe(tmp_path, "2025-06-01")
        with pytest.raises(ValueError, match="train window too short"):
            rolling_windows(universe, datetime(2026, 6, 12))


class TestDecideAdoption:
    def test_adopts_when_both_windows_improve(self):
        baseline = fake_result(1.0, 1.5)
        candidate = fake_result(1.1, 1.6)
        adopted, reasons, comparisons = decide_adoption(baseline, candidate, START, HOLDOUT, END)
        assert adopted and reasons == []
        assert [c.window for c in comparisons] == ["train", "holdout"]

    def test_adopts_on_exact_tie(self):
        baseline = fake_result(1.0, 1.5)
        candidate = fake_result(1.0, 1.5)
        adopted, reasons, _ = decide_adoption(baseline, candidate, START, HOLDOUT, END)
        assert adopted

    def test_rejects_train_degradation(self):
        adopted, reasons, _ = decide_adoption(
            fake_result(1.0, 1.5), fake_result(0.8, 2.0), START, HOLDOUT, END
        )
        assert not adopted
        assert any("train Sharpe degrades" in r for r in reasons)

    def test_rejects_holdout_degradation(self):
        adopted, reasons, _ = decide_adoption(
            fake_result(1.0, 1.5), fake_result(1.2, 1.4), START, HOLDOUT, END
        )
        assert not adopted
        assert any("holdout Sharpe degrades" in r for r in reasons)

    def test_rejects_new_kill_failure(self):
        adopted, reasons, _ = decide_adoption(
            fake_result(1.0, 1.5),
            fake_result(1.1, 1.6, holdout_failures=["DD 30%>25%"]),
            START,
            HOLDOUT,
            END,
        )
        assert not adopted
        assert any("introduces kill failures" in r for r in reasons)

    def test_tolerates_preexisting_failure(self):
        # A failure the baseline already has must not block adoption.
        adopted, _, _ = decide_adoption(
            fake_result(1.0, 1.5, train_failures=["trades 5<21"]),
            fake_result(1.1, 1.6, train_failures=["trades 5<21"]),
            START,
            HOLDOUT,
            END,
        )
        assert adopted


def make_report(assignments: dict[str, dict], researched: list[str]) -> ResearchReport:
    """Report with one singleton cluster per researched symbol."""
    clusters = []
    for symbol in researched:
        cluster = ClusterResult(
            name=symbol,
            members=[symbol],
            volatility={symbol: 0.3},
            candidates_evaluated=1,
            candidates_eligible=1,
        )
        if symbol in assignments:
            cluster.winner_name = f"win_{symbol}"
            cluster.winner_hash = assignments[symbol]["hash"]
            cluster.winner_config = assignments[symbol]["config"]
            from bonito.research.cluster_research import MemberVerdict
            from bonito.trading.validation import WindowMetrics

            metrics = WindowMetrics(
                start=START,
                end=END,
                years=1.0,
                trades=20,
                win_rate=0.5,
                total_return=0.5,
                sharpe=1.5,
                max_drawdown=0.1,
            )
            cluster.verdicts = [
                MemberVerdict(symbol=symbol, train=metrics, holdout=metrics, holdout_reasons=[])
            ]
        clusters.append(cluster)
    return ResearchReport(
        generated_at=datetime.now(),
        start=START,
        holdout=HOLDOUT,
        end=END,
        default_strategy_hash="default00000",
        clusters=clusters,
    )


class TestBuildCandidateMap:
    def universe(self, tmp_path, symbol_strategies: dict[str, str]) -> UniverseConfig:
        path = tmp_path / "s.json"
        path.write_text(json.dumps(BASE_STRATEGY))
        return UniverseConfig(
            name="t",
            symbols=["AAA", "BBB", "CCC"],
            strategy_path=str(path),
            symbol_strategies=symbol_strategies,
            data={"timeframe": "1d", "start_date": "2022-01-01"},
        )

    def test_new_winner_assigned_and_file_written(self, tmp_path):
        universe = self.universe(tmp_path, {})
        report = make_report(
            {"AAA": {"hash": "aaa111", "config": BASE_STRATEGY}}, researched=["AAA", "BBB"]
        )
        candidate, created = build_candidate_map(universe, report, tmp_path / "strategies")
        assert set(candidate) == {"AAA"}
        assert len(created) == 1 and created[0].exists()
        assert json.loads(created[0].read_text())["name"] == "default"

    def test_researched_symbol_without_winner_reverts_to_default(self, tmp_path):
        universe = self.universe(tmp_path, {"BBB": "strategies/old_bbb.json"})
        report = make_report({}, researched=["AAA", "BBB"])
        candidate, created = build_candidate_map(universe, report, tmp_path / "strategies")
        assert candidate == {} and created == []

    def test_unresearched_symbol_keeps_assignment(self, tmp_path):
        universe = self.universe(tmp_path, {"CCC": "strategies/keep_ccc.json"})
        report = make_report({}, researched=["AAA", "BBB"])  # CCC had no data
        candidate, _ = build_candidate_map(universe, report, tmp_path / "strategies")
        assert candidate == {"CCC": "strategies/keep_ccc.json"}


class TestRunAutoResearch:
    """Orchestration with the sweep and replay monkeypatched."""

    def setup_universe(self, tmp_path, symbol_strategies=None) -> Path:
        strategy_path = tmp_path / "default.json"
        strategy_path.write_text(json.dumps(BASE_STRATEGY))
        universe_path = tmp_path / "universe.json"
        universe_path.write_text(
            json.dumps(
                {
                    "name": "auto-test",
                    "symbols": ["AAA", "BBB"],
                    "strategy_path": str(strategy_path),
                    "symbol_strategies": symbol_strategies or {},
                    "data": {"timeframe": "1d", "start_date": "2022-01-01"},
                    "risk": {"starting_cash_usd": 5000.0},
                }
            )
        )
        return universe_path

    def patch_pipeline(self, monkeypatch, report, baseline, candidate):
        monkeypatch.setattr(auto_research, "run_cluster_research", lambda *a, **k: report)
        monkeypatch.setattr(
            auto_research.ReplayStore, "from_store", classmethod(lambda cls, *a, **k: cls({}))
        )
        results = iter([baseline, candidate])
        monkeypatch.setattr(auto_research, "backtest_account", lambda *a, **k: next(results))

    def test_adopt_writes_universe(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        report = make_report(
            {"AAA": {"hash": "aaa111", "config": BASE_STRATEGY}}, researched=["AAA", "BBB"]
        )
        self.patch_pipeline(monkeypatch, report, fake_result(1.0, 1.5), fake_result(1.2, 1.7))

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
        )

        assert result.outcome == "adopted"
        assert result.added == ["AAA"]
        config = json.loads(universe_path.read_text())
        assert "AAA" in config["symbol_strategies"]
        assert Path(config["symbol_strategies"]["AAA"]).exists()

    def test_reject_leaves_universe_untouched_and_cleans_files(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        before = universe_path.read_text()
        report = make_report(
            {"AAA": {"hash": "aaa111", "config": BASE_STRATEGY}}, researched=["AAA", "BBB"]
        )
        self.patch_pipeline(monkeypatch, report, fake_result(1.0, 1.5), fake_result(1.2, 1.0))

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
        )

        assert result.outcome == "rejected"
        assert any("holdout" in r for r in result.reasons)
        assert universe_path.read_text() == before
        assert list((tmp_path / "strategies").glob("auto_*.json")) == []

    def test_unchanged_map_skips_replay(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        report = make_report({}, researched=["AAA", "BBB"])
        monkeypatch.setattr(auto_research, "run_cluster_research", lambda *a, **k: report)

        def boom(*a, **k):
            raise AssertionError("replay must not run when the map is unchanged")

        monkeypatch.setattr(auto_research, "backtest_account", boom)

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
        )
        assert result.outcome == "unchanged"

    def test_stale_assignment_removal_goes_through_gate(self, tmp_path, monkeypatch):
        # BBB has an assignment but no longer passes → candidate drops it →
        # replay gate decides; here the gate approves the removal.
        old = tmp_path / "strategies" / "old_bbb.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps(BASE_STRATEGY))
        universe_path = self.setup_universe(tmp_path, {"BBB": str(old)})
        report = make_report({}, researched=["AAA", "BBB"])
        self.patch_pipeline(monkeypatch, report, fake_result(1.0, 1.5), fake_result(1.0, 1.6))

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
        )

        assert result.outcome == "adopted"
        assert result.removed == ["BBB"]
        assert json.loads(universe_path.read_text())["symbol_strategies"] == {}

    def test_digest_written_every_cycle(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        report = make_report({}, researched=["AAA", "BBB"])
        monkeypatch.setattr(auto_research, "run_cluster_research", lambda *a, **k: report)

        run_auto_research(
            universe_path,
            store=None,
            end=END,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
        )
        digests = list((tmp_path / "research").glob("auto_research_*.json"))
        assert len(digests) == 1
        assert json.loads(digests[0].read_text())["outcome"] == "unchanged"
