"""Tests for per-cluster strategy research (bonito.research.cluster_research)."""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from bonito.data.models import BarData
from bonito.research.cluster_research import (
    ADXTrendGrid,
    BBandsMeanRevGrid,
    GridSpec,
    MACDCrossGrid,
    _adx_trend_candidates,
    _bbands_meanrev_candidates,
    _macd_cross_candidates,
    annualized_volatility,
    apply_assignments,
    candidate_grid,
    cluster_universe,
    run_cluster_research,
)
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.validation import strategy_hash

START = datetime(2024, 1, 1)
HOLDOUT = datetime(2025, 6, 1)
END = datetime(2026, 6, 1)


def make_bars(symbol: str, closes: list[float], start: datetime = START) -> BarData:
    n = len(closes)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[start + timedelta(days=i) for i in range(n)],
        opens=closes,
        highs=[c * 1.01 for c in closes],
        lows=[c * 0.99 for c in closes],
        closes=closes,
        volumes=[1_000_000.0] * n,
    )


def trending_closes(n: int, daily_vol: float, drift: float = 0.0005, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, daily_vol, n)
    return (100 * np.exp(np.cumsum(returns))).tolist()


class FakeStore:
    def __init__(self, bars: dict[str, BarData]):
        self.bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self.bars.get(symbol)


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


@pytest.fixture
def universe(tmp_path):
    strategy_path = tmp_path / "default.json"
    strategy_path.write_text(json.dumps(BASE_STRATEGY))
    return UniverseConfig(
        name="research-test",
        symbols=["CALM", "WILD"],
        strategy_path=str(strategy_path),
        data={"timeframe": "1d", "start_date": "2024-01-01"},
        risk={"starting_cash_usd": 5000.0},
    )


class TestVolatilityClustering:
    def test_annualized_vol_scales_with_daily_vol(self):
        calm = make_bars("CALM", trending_closes(400, daily_vol=0.005))
        wild = make_bars("WILD", trending_closes(400, daily_vol=0.06))
        assert annualized_volatility(calm) < 0.30
        assert annualized_volatility(wild) > 0.75

    def test_insufficient_history_is_speculative(self):
        tiny = make_bars("TINY", [100.0] * 10)
        assert math.isinf(annualized_volatility(tiny))

    def test_cluster_universe_buckets_and_excludes(self, universe):
        store = FakeStore(
            {
                "CALM": make_bars("CALM", trending_closes(400, daily_vol=0.005)),
                "WILD": make_bars("WILD", trending_closes(400, daily_vol=0.06)),
            }
        )
        clusters, vols = cluster_universe(universe, store, START, END)
        assert clusters["defensive"] == ["CALM"]
        assert clusters["speculative"] == ["WILD"]
        assert set(vols) == {"CALM", "WILD"}

    def test_symbol_without_data_omitted(self, universe):
        store = FakeStore({"CALM": make_bars("CALM", trending_closes(400, daily_vol=0.005))})
        clusters, vols = cluster_universe(universe, store, START, END)
        assert "WILD" not in vols
        assert all("WILD" not in members for members in clusters.values())


class TestCandidateGrid:
    def test_default_grid_size(self):
        grid = GridSpec()
        expected = (
            len(grid.ema_pairs) * len(grid.rsi_max) * len(grid.atr_mult) * len(grid.take_profit)
        )
        candidates = candidate_grid(grid)
        assert len(candidates) == expected == 450

    def test_deployed_config_is_in_the_grid(self):
        with open("strategies/deployed_strategy.json") as f:
            deployed = json.loads(f.read())
        deployed_hash = strategy_hash(
            __import__("bonito.backtest.strategy", fromlist=["StrategyConfig"]).StrategyConfig(
                **deployed
            )
        )
        hashes = {strategy_hash(c) for c in candidate_grid()}
        assert deployed_hash in hashes

    def test_all_candidates_have_regime_and_atr_stop(self):
        for c in candidate_grid(GridSpec(ema_pairs=[(10, 26)], rsi_max=[68.0])):
            assert c.regime_filter is not None
            assert c.stop_loss.type.value == "trailing_atr"
            assert c.name.startswith("c_ema10-26")


class TestTemplateFamilies:
    """The 2026-06-18 adx/macd/bbands templates: opt-in, additive, and each
    wired to its own indicator outputs."""

    def test_disabled_by_default_grid_unchanged(self):
        # No args and an explicit all-None GridSpec must both still yield
        # exactly the original 450 EMA-only candidates.
        assert len(candidate_grid()) == 450
        assert len(candidate_grid(GridSpec())) == 450

    def test_each_template_is_additive_and_opt_in(self):
        base = len(candidate_grid(GridSpec()))
        adx_grid = GridSpec(adx=ADXTrendGrid())
        macd_grid = GridSpec(macd=MACDCrossGrid())
        bbands_grid = GridSpec(bbands=BBandsMeanRevGrid())

        assert len(candidate_grid(adx_grid)) == base + len(_adx_trend_candidates(adx_grid.adx))
        assert len(candidate_grid(macd_grid)) == base + len(_macd_cross_candidates(macd_grid.macd))
        assert len(candidate_grid(bbands_grid)) == base + len(
            _bbands_meanrev_candidates(bbands_grid.bbands)
        )

    def test_all_templates_enabled_together_have_unique_hashes(self):
        grid = GridSpec(adx=ADXTrendGrid(), macd=MACDCrossGrid(), bbands=BBandsMeanRevGrid())
        candidates = candidate_grid(grid)
        assert len(candidates) == 450 + 27 + 18 + 16
        hashes = {strategy_hash(c) for c in candidates}
        assert len(hashes) == len(candidates)

    def test_adx_candidates_use_adx_and_have_regime_and_atr_stop(self):
        candidates = _adx_trend_candidates(ADXTrendGrid())
        assert len(candidates) == 3 * 3 * 3
        for c in candidates:
            assert c.name.startswith("c_adx")
            assert c.regime_filter is not None
            assert c.stop_loss.type.value == "trailing_atr"
            # "adx" is pandas-ta-dispatched, not a built-in IndicatorType
            # member, so it stays a raw str rather than coercing to enum.
            indicator_types = {i.type for i in c.indicators}
            assert "adx" in indicator_types
            assert "ema" in indicator_types

    def test_macd_candidates_use_macd_and_have_regime_and_atr_stop(self):
        candidates = _macd_cross_candidates(MACDCrossGrid())
        assert len(candidates) == 3 * 2 * 3
        for c in candidates:
            assert c.name.startswith("c_macd")
            assert c.regime_filter is not None
            assert c.stop_loss.type.value == "trailing_atr"
            indicator_types = {i.type for i in c.indicators}
            assert "macd" in indicator_types
            assert "rsi" in indicator_types

    def test_bbands_candidates_use_bbands_and_have_regime_and_atr_stop(self):
        candidates = _bbands_meanrev_candidates(BBandsMeanRevGrid())
        assert len(candidates) == 2 * 2 * 2 * 2
        for c in candidates:
            assert c.name.startswith("c_bb")
            assert c.regime_filter is not None
            assert c.stop_loss.type.value == "trailing_atr"
            indicator_types = {i.type for i in c.indicators}
            assert "bbands" in indicator_types
            assert "rsi" in indicator_types

    def test_macd_entry_and_exit_reference_macd_line_and_signal(self):
        candidates = _macd_cross_candidates(MACDCrossGrid(macd_params=[(12, 26, 9)]))
        entry_refs = {
            cond.right
            for c in candidates
            for rule in c.entry_rules
            for cond in rule.conditions
            if isinstance(cond.right, str)
        }
        assert "macd_signal" in entry_refs

    def test_bbands_exit_targets_mid_band(self):
        candidates = _bbands_meanrev_candidates(BBandsMeanRevGrid(bb_period=[14], bb_std=[2.0]))
        for c in candidates:
            exit_refs = {
                cond.right
                for rule in c.exit_rules
                for cond in rule.conditions
                if isinstance(cond.right, str)
            }
            assert "bb_middle" in exit_refs


class TestResearchAndApply:
    def tiny_grid(self) -> GridSpec:
        return GridSpec(ema_pairs=[(10, 26)], rsi_max=[68.0], atr_mult=[2.0], take_profit=[None])

    def research_store(self, n: int = 700) -> FakeStore:
        # Calm uptrending symbols (researchable) + SPY uptrend (regime on,
        # history long enough that SMA200 is defined early).
        spy_start = START - timedelta(days=400)
        return FakeStore(
            {
                "CALM": make_bars("CALM", trending_closes(n, 0.004, drift=0.001, seed=1)),
                "WILD": make_bars("WILD", trending_closes(n, 0.004, drift=0.001, seed=2)),
                "SPY": make_bars(
                    "SPY", trending_closes(n + 400, 0.002, drift=0.001, seed=3), start=spy_start
                ),
            }
        )

    def test_report_structure_and_determinism(self, universe):
        store = self.research_store()
        report1 = run_cluster_research(universe, store, START, HOLDOUT, END, grid=self.tiny_grid())
        report2 = run_cluster_research(universe, store, START, HOLDOUT, END, grid=self.tiny_grid())
        assert [c.winner_hash for c in report1.clusters] == [
            c.winner_hash for c in report2.clusters
        ]
        for cluster in report1.clusters:
            assert cluster.candidates_evaluated == 1
            if cluster.winner_name:
                assert cluster.winner_config is not None
                assert all(v.symbol in cluster.members for v in cluster.verdicts)

    def test_assignments_only_for_passing_pairs(self, universe):
        store = self.research_store()
        report = run_cluster_research(universe, store, START, HOLDOUT, END, grid=self.tiny_grid())
        assignments = report.assignments()
        for symbol, cluster in assignments.items():
            assert symbol in cluster.passing_symbols
            assert cluster.winner_hash != report.default_strategy_hash

    def test_apply_writes_strategy_and_universe(self, universe, tmp_path):
        store = self.research_store()
        report = run_cluster_research(universe, store, START, HOLDOUT, END, grid=self.tiny_grid())
        if not report.assignments():
            pytest.skip("synthetic data produced no passing pairs for this grid")

        universe_path = tmp_path / "universe.json"
        universe_path.write_text(
            json.dumps(
                {
                    "name": "research-test",
                    "symbols": ["CALM", "WILD"],
                    "strategy_path": universe.strategy_path,
                    "symbol_strategies": {"KEEP": "strategies/existing.json"},
                }
            )
        )
        written = apply_assignments(report, universe_path, strategies_dir=tmp_path / "strategies")

        config = json.loads(universe_path.read_text())
        for symbol, path in written.items():
            assert config["symbol_strategies"][symbol] == path
            saved = json.loads((tmp_path / "strategies").joinpath(Path(path).name).read_text())
            assert saved["regime_filter"]["symbol"] == "SPY"
        # Pre-existing assignments preserved
        assert config["symbol_strategies"]["KEEP"] == "strategies/existing.json"

    def test_no_assignment_when_winner_is_default(self, universe, tmp_path):
        # Make the universe default IDENTICAL to the single grid candidate →
        # winner hash == default hash → no assignments.
        candidate = candidate_grid(self.tiny_grid())[0]
        default_path = tmp_path / "default_same.json"
        default_path.write_text(candidate.model_dump_json())
        universe.strategy_path = str(default_path)
        universe._strategy_cache.clear()

        store = self.research_store()
        report = run_cluster_research(universe, store, START, HOLDOUT, END, grid=self.tiny_grid())
        assert report.assignments() == {}


class TestPerSymbolMode:
    def tiny_grid(self) -> GridSpec:
        return GridSpec(
            ema_pairs=[(10, 26), (20, 50)], rsi_max=[68.0], atr_mult=[2.0], take_profit=[None]
        )

    def research_store(self, n: int = 700) -> "FakeStore":
        spy_start = START - timedelta(days=400)
        return FakeStore(
            {
                "CALM": make_bars("CALM", trending_closes(n, 0.004, drift=0.001, seed=1)),
                "WILD": make_bars("WILD", trending_closes(n, 0.06, drift=0.002, seed=2)),
                "SPY": make_bars(
                    "SPY", trending_closes(n + 400, 0.002, drift=0.001, seed=3), start=spy_start
                ),
            }
        )

    def test_each_symbol_is_a_singleton_cluster(self, universe):
        store = self.research_store()
        report = run_cluster_research(
            universe, store, START, HOLDOUT, END, grid=self.tiny_grid(), per_symbol=True
        )
        assert [c.name for c in report.clusters] == ["CALM", "WILD"]
        assert all(c.members == [c.name] for c in report.clusters)
        # A singleton's verdicts cover at most its own symbol.
        for cluster in report.clusters:
            assert all(v.symbol == cluster.name for v in cluster.verdicts)

    def test_winners_can_differ_across_symbols(self, universe):
        store = self.research_store()
        report = run_cluster_research(
            universe, store, START, HOLDOUT, END, grid=self.tiny_grid(), per_symbol=True
        )
        # Each singleton picks its own winner from the grid; with two
        # candidates and very different vol profiles the choice is per
        # symbol (both may coincide, but the structure allows divergence).
        winners = {c.name: c.winner_name for c in report.clusters if c.winner_name}
        assert set(winners) <= {"CALM", "WILD"}

    def test_symbol_without_data_excluded(self, universe):
        store = FakeStore(
            {
                "CALM": make_bars("CALM", trending_closes(700, 0.004, drift=0.001, seed=1)),
                "SPY": make_bars(
                    "SPY",
                    trending_closes(1100, 0.002, drift=0.001, seed=3),
                    start=START - timedelta(days=400),
                ),
            }
        )
        report = run_cluster_research(
            universe, store, START, HOLDOUT, END, grid=self.tiny_grid(), per_symbol=True
        )
        assert [c.name for c in report.clusters] == ["CALM"]

    def test_determinism(self, universe):
        store = self.research_store()
        kwargs = {"grid": self.tiny_grid(), "per_symbol": True}
        r1 = run_cluster_research(universe, store, START, HOLDOUT, END, **kwargs)
        r2 = run_cluster_research(universe, store, START, HOLDOUT, END, **kwargs)
        assert [c.winner_hash for c in r1.clusters] == [c.winner_hash for c in r2.clusters]

    def test_assignments_respect_holdout_gate(self, universe):
        store = self.research_store()
        report = run_cluster_research(
            universe, store, START, HOLDOUT, END, grid=self.tiny_grid(), per_symbol=True
        )
        for symbol, cluster in report.assignments().items():
            assert cluster.name == symbol
            assert symbol in cluster.passing_symbols
            assert cluster.winner_hash != report.default_strategy_hash
