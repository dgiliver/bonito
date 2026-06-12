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
    per_symbol_pnl: dict[str, float] | None = None,
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
        per_symbol_pnl=per_symbol_pnl or {},
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


def make_report(
    assignments: dict[str, dict],
    researched: list[str],
    eligible: dict[str, int] | None = None,
) -> ResearchReport:
    """Report with one singleton cluster per researched symbol."""
    clusters = []
    for symbol in researched:
        cluster = ClusterResult(
            name=symbol,
            members=[symbol],
            volatility={symbol: 0.3},
            candidates_evaluated=1,
            candidates_eligible=(eligible or {}).get(symbol, 1),
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


class AutoResearchHarness:
    """Shared setup: universe on disk, sweep + replays monkeypatched."""

    @pytest.fixture(autouse=True)
    def _guard_real_live_config(self):
        """Fail loudly if a test ever mutates the repo's real live config."""
        real = Path("config/universe.live.json")
        before = real.read_text() if real.exists() else None
        yield
        after = real.read_text() if real.exists() else None
        assert before == after, "test leaked into the real config/universe.live.json"

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

    def patch_pipeline(self, monkeypatch, report, baseline, *candidates, swap=None):
        """Stub the sweep + replays. `candidates` are consumed by successive
        bundle replays (graded fallback); `swap` stubs propose_default_swap."""
        monkeypatch.setattr(auto_research, "run_cluster_research", lambda *a, **k: report)
        monkeypatch.setattr(
            auto_research, "propose_default_swap", lambda *a, **k: swap or (None, None, None)
        )
        monkeypatch.setattr(
            auto_research.ReplayStore, "from_store", classmethod(lambda cls, *a, **k: cls({}))
        )
        results = iter([baseline, *candidates])
        monkeypatch.setattr(auto_research, "backtest_account", lambda *a, **k: next(results))


class TestRunAutoResearch(AutoResearchHarness):
    """Core orchestration paths."""

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
            live_path=tmp_path / "universe.live.json",
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
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "rejected"
        assert any("holdout" in r for r in result.reasons)
        assert universe_path.read_text() == before
        assert list((tmp_path / "strategies").glob("auto_*.json")) == []

    def test_unchanged_map_skips_replay(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        report = make_report({}, researched=["AAA", "BBB"])
        monkeypatch.setattr(auto_research, "run_cluster_research", lambda *a, **k: report)
        monkeypatch.setattr(
            auto_research, "propose_default_swap", lambda *a, **k: (None, None, None)
        )

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
            live_path=tmp_path / "universe.live.json",
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
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "adopted"
        assert result.removed == ["BBB"]
        assert json.loads(universe_path.read_text())["symbol_strategies"] == {}

    def test_digest_written_every_cycle(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        report = make_report({}, researched=["AAA", "BBB"])
        monkeypatch.setattr(auto_research, "run_cluster_research", lambda *a, **k: report)
        monkeypatch.setattr(
            auto_research, "propose_default_swap", lambda *a, **k: (None, None, None)
        )

        run_auto_research(
            universe_path,
            store=None,
            end=END,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )
        digests = list((tmp_path / "research").glob("auto_research_*.json"))
        assert len(digests) == 1
        assert json.loads(digests[0].read_text())["outcome"] == "unchanged"


class TestBenching(AutoResearchHarness):
    def test_zero_eligible_symbol_gets_benched(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        report = make_report({}, researched=["AAA", "BBB"], eligible={"BBB": 0})
        # First bundle (assignments+bench) passes the gate.
        self.patch_pipeline(monkeypatch, report, fake_result(1.0, 1.5), fake_result(1.0, 1.6))

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "adopted"
        assert result.benched == ["BBB"]
        assert json.loads(universe_path.read_text())["entry_blocklist"] == ["BBB"]

    def test_profitable_volatile_symbol_never_benched(self, tmp_path, monkeypatch):
        # Zero eligible candidates (fails per-symbol filters at 100% capital)
        # but a top account-level contributor — must NOT be proposed for the
        # bench, so the cycle is a no-op without burning a bundle replay.
        universe_path = self.setup_universe(tmp_path)
        report = make_report({}, researched=["AAA", "BBB"], eligible={"BBB": 0})
        self.patch_pipeline(
            monkeypatch,
            report,
            fake_result(1.0, 1.5, per_symbol_pnl={"BBB": 1247.0}),
        )

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "unchanged"
        assert result.benched == []
        assert "entry_blocklist" not in json.loads(universe_path.read_text())

    def test_bad_bench_falls_back_to_assignments_only(self, tmp_path, monkeypatch):
        # Bench bundle degrades holdout (an IREN-style false positive);
        # the assignments-only fallback passes, so benching is dropped.
        universe_path = self.setup_universe(tmp_path)
        report = make_report(
            {"AAA": {"hash": "aaa111", "config": BASE_STRATEGY}},
            researched=["AAA", "BBB"],
            eligible={"BBB": 0},
        )
        self.patch_pipeline(
            monkeypatch,
            report,
            fake_result(1.0, 1.5),
            fake_result(1.2, 1.0),  # assignments+bench: holdout degrades
            fake_result(1.2, 1.7),  # assignments-only: passes
        )

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "adopted"
        assert result.adopted_bundle == "assignments-only"
        assert result.benched == []
        config = json.loads(universe_path.read_text())
        assert config["entry_blocklist"] == []
        assert "AAA" in config["symbol_strategies"]

    def test_healed_symbol_is_unbenched(self, tmp_path, monkeypatch):
        strategy_path = tmp_path / "default.json"
        strategy_path.write_text(json.dumps(BASE_STRATEGY))
        universe_path = tmp_path / "universe.json"
        universe_path.write_text(
            json.dumps(
                {
                    "name": "auto-test",
                    "symbols": ["AAA", "BBB"],
                    "strategy_path": str(strategy_path),
                    "entry_blocklist": ["BBB"],
                    "data": {"timeframe": "1d", "start_date": "2022-01-01"},
                    "risk": {"starting_cash_usd": 5000.0},
                }
            )
        )
        report = make_report({}, researched=["AAA", "BBB"])  # BBB eligible again
        self.patch_pipeline(monkeypatch, report, fake_result(1.0, 1.5), fake_result(1.1, 1.6))

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "adopted"
        assert result.unbenched == ["BBB"]
        assert json.loads(universe_path.read_text())["entry_blocklist"] == []


class TestDefaultSwap(AutoResearchHarness):
    def test_gated_default_swap_rewrites_strategy_path(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        new_default = tmp_path / "strategies" / "auto_default_new123.json"
        new_default.parent.mkdir(parents=True, exist_ok=True)
        new_default.write_text(json.dumps({**BASE_STRATEGY, "name": "new_default"}))
        report = make_report({}, researched=["AAA", "BBB"])
        self.patch_pipeline(
            monkeypatch,
            report,
            fake_result(1.0, 1.5),
            fake_result(1.3, 1.8),  # swap bundle passes immediately
            swap=("new_default", str(new_default), None),
        )

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "adopted"
        assert result.default_swapped
        assert result.default_swap == "new_default"
        assert json.loads(universe_path.read_text())["strategy_path"] == str(new_default)

    def test_bad_swap_falls_back_to_current_default(self, tmp_path, monkeypatch):
        universe_path = self.setup_universe(tmp_path)
        original = json.loads(universe_path.read_text())["strategy_path"]
        new_default = tmp_path / "strategies" / "auto_default_new123.json"
        new_default.parent.mkdir(parents=True, exist_ok=True)
        new_default.write_text(json.dumps({**BASE_STRATEGY, "name": "new_default"}))
        report = make_report(
            {"AAA": {"hash": "aaa111", "config": BASE_STRATEGY}}, researched=["AAA", "BBB"]
        )
        self.patch_pipeline(
            monkeypatch,
            report,
            fake_result(1.0, 1.5),
            fake_result(1.4, 1.2),  # swap+assignments: holdout degrades
            fake_result(1.1, 1.6),  # assignments-only: passes
            swap=("new_default", str(new_default), None),
        )

        result = run_auto_research(
            universe_path,
            store=None,
            end=END,
            apply=True,
            strategies_dir=tmp_path / "strategies",
            research_dir=tmp_path / "research",
            live_path=tmp_path / "universe.live.json",
        )

        assert result.outcome == "adopted"
        assert not result.default_swapped
        assert result.default_swap is None  # cleared: the swap did not ship
        config = json.loads(universe_path.read_text())
        assert config["strategy_path"] == original
        assert "AAA" in config["symbol_strategies"]


class TestSyncLiveConfig:
    def test_structure_synced_human_levers_untouched(self, tmp_path):
        paper = tmp_path / "universe.json"
        live = tmp_path / "universe.live.json"
        paper.write_text(
            json.dumps(
                {
                    "name": "paper",
                    "symbols": ["AAA", "BBB"],
                    "strategy_path": "strategies/new_default.json",
                    "symbol_strategies": {"AAA": "strategies/auto_AAA_x.json"},
                    "entry_blocklist": ["BBB"],
                    "risk": {"starting_cash_usd": 5000.0, "max_position_usd": 2500.0},
                }
            )
        )
        live.write_text(
            json.dumps(
                {
                    "name": "live",
                    "mode": "live",
                    "live_enabled": False,
                    "symbols": ["OLD"],
                    "strategy_path": "strategies/old.json",
                    "symbol_strategies": {},
                    "entry_allowlist": ["COST"],
                    "risk": {"starting_cash_usd": 150.0, "max_position_usd": 30.0},
                }
            )
        )

        changed = auto_research.sync_live_config(paper, live)

        assert changed
        synced = json.loads(live.read_text())
        assert synced["symbols"] == ["AAA", "BBB"]
        assert synced["strategy_path"] == "strategies/new_default.json"
        assert synced["entry_blocklist"] == ["BBB"]
        # Human-only levers preserved exactly.
        assert synced["mode"] == "live"
        assert synced["live_enabled"] is False
        assert synced["entry_allowlist"] == ["COST"]
        assert synced["risk"]["max_position_usd"] == 30.0

    def test_missing_live_config_is_noop(self, tmp_path):
        paper = tmp_path / "universe.json"
        paper.write_text(json.dumps({"symbols": ["AAA"]}))
        assert not auto_research.sync_live_config(paper, tmp_path / "nope.json")


class TestGridEdgeFlags:
    def winner_config(self, fast=10, slow=26, rsi=68.0, atr=2.0):
        return {
            "indicators": [
                {"type": "ema", "name": "ema_fast", "params": {"period": fast}},
                {"type": "ema", "name": "ema_slow", "params": {"period": slow}},
                {"type": "rsi", "name": "rsi_14", "params": {"period": 14}},
            ],
            "entry_rules": [
                {
                    "conditions": [
                        {"left": "ema_fast", "comparison": "gt", "right": "ema_slow"},
                        {"left": "rsi_14", "comparison": "lt", "right": rsi},
                    ]
                }
            ],
            "stop_loss": {"type": "trailing_atr", "value": atr, "atr_period": 14},
        }

    def report_with_winner(self, config) -> ResearchReport:
        report = make_report({"AAA": {"hash": "h1", "config": config}}, researched=["AAA"])
        return report

    def test_edge_winner_flagged(self):
        # Edges of the EXTENDED grid: ema (5,13), rsi 50, atr 1.0.
        report = self.report_with_winner(self.winner_config(fast=5, slow=13, atr=1.0, rsi=50.0))
        flags = auto_research.grid_edge_flags(report)
        assert len(flags) == 1
        assert "AAA" in flags[0]
        assert "atr=1" in flags[0] and "rsi<50" in flags[0] and "ema=(5, 13)" in flags[0]

    def test_interior_winner_not_flagged(self):
        # 8/21, rsi 60, atr 1.5 were edges of the ORIGINAL grid — the
        # 2026-06-12 extension moved them to the interior.
        report = self.report_with_winner(self.winner_config(fast=8, slow=21, atr=1.5, rsi=60.0))
        assert auto_research.grid_edge_flags(report) == []

    def test_non_passing_winner_not_flagged(self):
        report = self.report_with_winner(self.winner_config(fast=5, slow=13, atr=1.0))
        report.clusters[0].verdicts[0].holdout_reasons = ["DD 40%>25%"]
        assert auto_research.grid_edge_flags(report) == []
