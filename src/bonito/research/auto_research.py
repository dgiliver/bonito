"""Autonomous research cycle: keep the WHOLE config current without a human.

This is the zero-intervention layer. Weekly (or on demand) it re-validates
every part of the trading config that can go stale, and adopts changes only
through the account-replay gate:

1. **Rolling holdout** — the out-of-sample boundary advances with the
   calendar (end - HOLDOUT_DAYS) instead of decaying into in-sample data.
2. **Per-symbol assignments, stateless** — an override exists only while
   its winner currently passes the holdout kill filter AND made money
   out-of-sample. Winners that stop passing revert to the default.
3. **The default strategy itself** — each cycle the grid is also scored
   cross-sectionally over the whole universe (the original cluster-mode
   machinery, majority train-pass + median Sharpe). A new cross-sectional
   winner becomes a candidate default swap.
4. **Benching** — a symbol where ZERO grid candidates pass the train kill
   filter AND whose baseline-replay P&L is non-positive is proposed for
   the entry_blocklist (entries blocked, exits never gated); it is
   unbenched the same way when it heals. Volatility alone never benches:
   high-vol names fail per-symbol filters at 100% capital while being top
   account-level contributors under slot caps.
5. **The gate** — candidate bundles are replayed against the current
   config with GRADED FALLBACK: (default swap + assignments + bench) →
   (default swap + assignments) → (assignments only). The first bundle
   where neither train nor holdout degrades and no new kill failures
   appear is adopted; if none pass, nothing changes and next cycle
   retries. This keeps a bad bench or default proposal from blocking
   good assignment updates.
6. **Grid-edge detection** — winners sitting on a grid boundary are
   flagged in the digest so a human can decide whether to extend the
   search space. The grid itself never auto-grows (multiplicity is the
   enemy); this is the deliberate human touchpoint.
7. **Live config sync** — on adoption, the validated structure (symbols,
   strategy_path, symbol_strategies, entry_blocklist) is mirrored into
   universe.live.json. mode, live_enabled, risk caps, and the
   entry_allowlist are NEVER synced — those stay human-only.

Every cycle writes an audit digest to livetrade/research/ either way.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from bonito.research.cluster_research import (
    GridSpec,
    ResearchReport,
    research_cluster,
    run_cluster_research,
    save_report,
)
from bonito.research.cluster_research import (
    candidate_grid as build_grid,
)
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import (
    AccountBacktestResult,
    ReplayStore,
    backtest_account,
)
from bonito.trading.validation import strategy_hash

logger = logging.getLogger(__name__)

# Rolling out-of-sample window. ~17.7 months matches the boundary the manual
# research used on 2026-06-12, and is long enough that the kill filter's
# min-trades gate (7/yr) stays statistically meaningful.
HOLDOUT_DAYS = 540
# The train window must keep at least this much history or the sweep aborts.
MIN_TRAIN_DAYS = 365
# Sharpe tolerance when comparing replays — absorbs float noise only; any
# real degradation rejects the bundle.
SHARPE_EPS = 1e-9


class WindowComparison(BaseModel):
    """Baseline vs candidate replay metrics for one window."""

    window: str
    baseline_sharpe: float
    candidate_sharpe: float
    baseline_return: float
    candidate_return: float
    baseline_failures: list[str]
    candidate_failures: list[str]


class Bundle(BaseModel):
    """One candidate configuration to gate against the baseline."""

    name: str
    strategy_path: str
    symbol_strategies: dict[str, str]
    entry_blocklist: list[str]


class AutoResearchResult(BaseModel):
    """Digest of one autonomous research cycle — the audit record."""

    generated_at: datetime
    universe_path: str
    start: datetime
    holdout: datetime
    end: datetime
    outcome: Literal["unchanged", "adopted", "rejected"]
    adopted_bundle: str | None = None
    reasons: list[str] = Field(
        default_factory=list, description="Gate failures, per rejected bundle"
    )
    previous_assignments: dict[str, str]
    candidate_assignments: dict[str, str]
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    default_swap: str | None = Field(
        default=None, description="Proposed new default strategy name, when one emerged"
    )
    default_swapped: bool = False
    benched: list[str] = Field(default_factory=list)
    unbenched: list[str] = Field(default_factory=list)
    grid_edge_flags: list[str] = Field(
        default_factory=list,
        description="Winners sitting on a grid boundary — human cue to extend the grid",
    )
    comparisons: list[WindowComparison] = Field(default_factory=list)
    baseline_final_equity: float | None = None
    candidate_final_equity: float | None = None
    report_path: str | None = None


def rolling_windows(universe: UniverseConfig, end: datetime) -> tuple[datetime, datetime, datetime]:
    """(start, holdout, end) with the holdout boundary tracking the calendar."""
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")
    holdout = end - timedelta(days=HOLDOUT_DAYS)
    if (holdout - start).days < MIN_TRAIN_DAYS:
        raise ValueError(
            f"train window too short: {start:%Y-%m-%d} → {holdout:%Y-%m-%d} "
            f"(< {MIN_TRAIN_DAYS} days); not enough history for a meaningful sweep"
        )
    return start, holdout, end


def decide_adoption(
    baseline: AccountBacktestResult,
    candidate: AccountBacktestResult,
    start: datetime,
    holdout: datetime,
    end: datetime,
) -> tuple[bool, list[str], list[WindowComparison]]:
    """The pre-registered gate, as a pure function.

    Adopt only if, in BOTH the train and holdout windows:
    - the candidate's Sharpe is not lower than the baseline's, and
    - the candidate introduces no kill-filter failure the baseline
      didn't already have.
    """
    reasons: list[str] = []
    comparisons: list[WindowComparison] = []
    windows = [("train", start, holdout - timedelta(days=1)), ("holdout", holdout, end)]
    for name, w_start, w_end in windows:
        base_m = baseline.window_metrics(w_start, w_end)
        cand_m = candidate.window_metrics(w_start, w_end)
        base_fail = baseline.verdict(w_start, w_end)
        cand_fail = candidate.verdict(w_start, w_end)
        comparisons.append(
            WindowComparison(
                window=name,
                baseline_sharpe=round(base_m.sharpe, 4),
                candidate_sharpe=round(cand_m.sharpe, 4),
                baseline_return=round(base_m.total_return, 4),
                candidate_return=round(cand_m.total_return, 4),
                baseline_failures=base_fail,
                candidate_failures=cand_fail,
            )
        )
        if cand_m.sharpe < base_m.sharpe - SHARPE_EPS:
            reasons.append(f"{name} Sharpe degrades: {cand_m.sharpe:.3f} < {base_m.sharpe:.3f}")
        new_failures = set(cand_fail) - set(base_fail)
        if new_failures:
            reasons.append(f"{name} introduces kill failures: {sorted(new_failures)}")
    return not reasons, reasons, comparisons


def build_candidate_map(
    universe: UniverseConfig,
    report: ResearchReport,
    strategies_dir: Path,
) -> tuple[dict[str, str], list[Path]]:
    """Stateless rebuild of symbol_strategies from this cycle's research.

    - Researched symbol with a passing winner → assigned (file written).
    - Researched symbol with no passing winner → reverts to default.
    - Symbol the sweep couldn't research (no data) → keeps its existing
      assignment; the daily runner skips it anyway until data returns.

    Returns:
        (candidate map, files created this cycle — for cleanup on reject).
    """
    researched = {c.name.upper() for c in report.clusters}
    candidate: dict[str, str] = {
        sym.upper(): path
        for sym, path in universe.symbol_strategies.items()
        if sym.upper() not in researched
    }
    created: list[Path] = []
    strategies_dir.mkdir(parents=True, exist_ok=True)
    for symbol, cluster in sorted(report.assignments().items()):
        assert cluster.winner_hash and cluster.winner_config
        path = strategies_dir / f"auto_{symbol}_{cluster.winner_hash}.json"
        if not path.exists():
            path.write_text(json.dumps(cluster.winner_config, indent=2))
            created.append(path)
        candidate[symbol.upper()] = str(path)
    return candidate, created


def build_bench_list(
    universe: UniverseConfig,
    report: ResearchReport,
    baseline: AccountBacktestResult,
) -> list[str]:
    """Stateless rebuild of the entry blocklist.

    A researched symbol is benched when BOTH hold: zero grid candidates
    passed its train kill filter (the strategy family is currently unsound
    on it) AND its baseline-replay P&L contribution is non-positive (it is
    actually costing the account — high-vol names fail the 100%-capital
    per-symbol filter while being top contributors at slot-capped account
    level, and must not be benched for volatility alone). Unresearched
    symbols keep their existing bench status. The replay gate still has
    the final word.
    """
    researched = {c.name.upper(): c for c in report.clusters}
    pnl = {s.upper(): v for s, v in baseline.per_symbol_pnl.items()}
    bench = {s.upper() for s in universe.entry_blocklist if s.upper() not in researched}
    bench |= {
        sym
        for sym, c in researched.items()
        if c.candidates_eligible == 0 and pnl.get(sym, 0.0) <= 0.0
    }
    return sorted(bench)


def propose_default_swap(
    universe: UniverseConfig,
    store,
    start: datetime,
    holdout: datetime,
    end: datetime,
    grid: GridSpec | None,
    report: ResearchReport,
    strategies_dir: Path,
    progress=None,
) -> tuple[str | None, str | None, Path | None]:
    """Cross-sectional re-validation of the DEFAULT strategy.

    Runs the original cluster machinery over the whole researched universe
    as one cluster: a candidate default must pass the train kill filter on
    a majority of symbols and is ranked by median train Sharpe. A winner
    that differs from the current default becomes a swap proposal (the
    replay gate decides whether it actually ships).

    Returns:
        (winner name, strategy path, created file) — Nones when the
        cross-sectional winner IS the current default or nothing qualifies.
    """
    members = sorted(c.name for c in report.clusters)
    if not members:
        return None, None, None
    vols = {s: v for c in report.clusters for s, v in c.volatility.items()}
    cluster = research_cluster(
        "__universe__",
        members,
        vols,
        build_grid(grid),
        store,
        universe,
        start,
        holdout,
        end,
        initial_capital=universe.risk.starting_cash_usd,
        progress=progress,
    )
    current_hash = strategy_hash(universe.load_strategy())
    if cluster.winner_hash is None or cluster.winner_hash == current_hash:
        return None, None, None
    assert cluster.winner_config and cluster.winner_name
    strategies_dir.mkdir(parents=True, exist_ok=True)
    path = strategies_dir / f"auto_default_{cluster.winner_hash}.json"
    created = None
    if not path.exists():
        path.write_text(json.dumps(cluster.winner_config, indent=2))
        created = path
    return cluster.winner_name, str(path), created


def grid_edge_flags(report: ResearchReport, grid: GridSpec | None = None) -> list[str]:
    """Flag adopted-candidate winners whose parameters sit on a grid boundary.

    A winner at the edge of an axis suggests the optimum may lie outside
    the search space. The grid never auto-extends — this is the human cue.
    """
    grid = grid or GridSpec()
    flags: list[str] = []
    edges = {
        "ema": {str(grid.ema_pairs[0]), str(grid.ema_pairs[-1])},
        "rsi": {min(grid.rsi_max), max(grid.rsi_max)},
        "atr": {min(grid.atr_mult), max(grid.atr_mult)},
    }
    for cluster in report.clusters:
        if cluster.winner_config is None or not cluster.passing_symbols:
            continue
        cfg = cluster.winner_config
        periods = [i["params"]["period"] for i in cfg["indicators"] if i["type"] == "ema"]
        rsi_lim = next(
            (
                float(c["right"])
                for r in cfg["entry_rules"]
                for c in r["conditions"]
                if c["left"].startswith("rsi")
            ),
            None,
        )
        atr_mult = cfg["stop_loss"]["value"] if cfg.get("stop_loss") else None
        at_edge = []
        if len(periods) == 2 and str(tuple(periods)) in edges["ema"]:
            at_edge.append(f"ema={tuple(periods)}")
        if rsi_lim is not None and rsi_lim in edges["rsi"]:
            at_edge.append(f"rsi<{rsi_lim:g}")
        if atr_mult is not None and atr_mult in edges["atr"]:
            at_edge.append(f"atr={atr_mult:g}")
        if at_edge:
            flags.append(f"{cluster.name}: winner at grid edge ({', '.join(at_edge)})")
    return flags


def sync_live_config(universe_path: Path, live_path: Path) -> bool:
    """Mirror the validated STRUCTURE into the live config draft.

    Synced: symbols, strategy_path, symbol_strategies, entry_blocklist —
    everything the replay gate validated. NEVER synced: mode, live_enabled,
    risk caps, entry_allowlist (human-only levers).

    Returns:
        True when the live config changed.
    """
    if not live_path.exists():
        return False
    paper = json.loads(universe_path.read_text())
    live = json.loads(live_path.read_text())
    before = json.dumps(live, sort_keys=True)
    for key in ("symbols", "strategy_path", "symbol_strategies", "entry_blocklist"):
        if key in paper:
            live[key] = paper[key]
    if json.dumps(live, sort_keys=True) == before:
        return False
    live_path.write_text(json.dumps(live, indent=2) + "\n")
    return True


def run_auto_research(
    universe_path: Path,
    store,
    end: datetime | None = None,
    grid: GridSpec | None = None,
    apply: bool = False,
    strategies_dir: Path = Path("strategies"),
    research_dir: Path = Path("livetrade/research"),
    live_path: Path = Path("config/universe.live.json"),
    progress=None,
) -> AutoResearchResult:
    """One full autonomous research cycle. See module docstring."""
    universe = UniverseConfig.load(universe_path)
    end = end or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start, holdout, end = rolling_windows(universe, end)

    report = run_cluster_research(
        universe, store, start, holdout, end, grid=grid, per_symbol=True, progress=progress
    )
    report_path = save_report(report, research_dir)

    candidate_map, created = build_candidate_map(universe, report, strategies_dir)
    swap_name, swap_path, swap_created = propose_default_swap(
        universe, store, start, holdout, end, grid, report, strategies_dir, progress=progress
    )
    if swap_created is not None:
        created.append(swap_created)

    previous = {s.upper(): p for s, p in universe.symbol_strategies.items()}
    previous_bench = sorted(s.upper() for s in universe.entry_blocklist)

    def make_result(bench: list[str]) -> AutoResearchResult:
        return AutoResearchResult(
            generated_at=datetime.now(),
            universe_path=str(universe_path),
            start=start,
            holdout=holdout,
            end=end,
            outcome="unchanged",
            previous_assignments=previous,
            candidate_assignments=candidate_map,
            added=sorted(set(candidate_map) - set(previous)),
            removed=sorted(set(previous) - set(candidate_map)),
            updated=sorted(
                s for s in set(previous) & set(candidate_map) if previous[s] != candidate_map[s]
            ),
            default_swap=swap_name,
            benched=sorted(set(bench) - set(previous_bench)),
            unbenched=sorted(set(previous_bench) - set(bench)),
            grid_edge_flags=grid_edge_flags(report, grid),
            report_path=str(report_path),
        )

    # Cheap skip: the baseline replay (which the bench decision needs) only
    # runs when this cycle could possibly change anything — new assignments,
    # a default proposal, a bench candidate, or a benched symbol that healed.
    bench_possible = any(c.candidates_eligible == 0 for c in report.clusters)
    healed_possible = any(
        c.candidates_eligible > 0 and c.name.upper() in set(previous_bench) for c in report.clusters
    )
    if (
        candidate_map == previous
        and swap_path is None
        and not bench_possible
        and not healed_possible
    ):
        result = make_result(previous_bench)
        _cleanup(created, candidate_map)
        _save_digest(result, research_dir)
        return result

    replay = ReplayStore.from_store(store, universe, end)
    baseline = backtest_account(universe, replay, start, end)
    bench = build_bench_list(universe, report, baseline)
    result = make_result(bench)
    result.baseline_final_equity = round(baseline.final_equity, 2)

    # Graded fallback: most ambitious bundle first; the first one that
    # clears the gate ships. A bad bench or default proposal must not
    # block good assignment updates.
    bundles: list[Bundle] = []

    def add_bundle(name: str, path: str, assignments: dict[str, str], blocklist: list[str]):
        b = Bundle(
            name=name, strategy_path=path, symbol_strategies=assignments, entry_blocklist=blocklist
        )
        unchanged = (
            path == universe.strategy_path
            and assignments == previous
            and sorted(blocklist) == previous_bench
        )
        if not unchanged and not any(
            x.strategy_path == b.strategy_path
            and x.symbol_strategies == b.symbol_strategies
            and x.entry_blocklist == b.entry_blocklist
            for x in bundles
        ):
            bundles.append(b)

    if swap_path is not None:
        add_bundle("default-swap+assignments+bench", swap_path, candidate_map, bench)
        add_bundle("default-swap+assignments", swap_path, candidate_map, previous_bench)
    add_bundle("assignments+bench", universe.strategy_path, candidate_map, bench)
    add_bundle("assignments-only", universe.strategy_path, candidate_map, previous_bench)

    if not bundles:
        _cleanup(created, candidate_map)
        _save_digest(result, research_dir)
        return result

    winner: Bundle | None = None
    for bundle in bundles:
        candidate_universe = universe.model_copy(
            update={
                "strategy_path": bundle.strategy_path,
                "symbol_strategies": bundle.symbol_strategies,
                "entry_blocklist": bundle.entry_blocklist,
            }
        )
        candidate = backtest_account(candidate_universe, replay, start, end)
        adopted, reasons, comparisons = decide_adoption(baseline, candidate, start, holdout, end)
        if adopted:
            winner = bundle
            result.adopted_bundle = bundle.name
            result.comparisons = comparisons
            result.candidate_final_equity = round(candidate.final_equity, 2)
            break
        result.reasons.extend(f"[{bundle.name}] {r}" for r in reasons)

    if winner is None:
        result.outcome = "rejected"
        _cleanup(created, previous)
        _save_digest(result, research_dir)
        return result

    result.outcome = "adopted"
    result.default_swapped = winner.strategy_path != universe.strategy_path
    if not result.default_swapped:
        result.default_swap = None
    if sorted(winner.entry_blocklist) == previous_bench:
        result.benched, result.unbenched = [], []

    if apply:
        config = json.loads(universe_path.read_text())
        config["strategy_path"] = winner.strategy_path
        config["symbol_strategies"] = dict(sorted(winner.symbol_strategies.items()))
        config["entry_blocklist"] = sorted(winner.entry_blocklist)
        universe_path.write_text(json.dumps(config, indent=2) + "\n")
        _cleanup(created, {**winner.symbol_strategies, "__default__": winner.strategy_path})
        sync_live_config(universe_path, live_path)
    else:
        _cleanup(created, previous)
    _save_digest(result, research_dir)
    return result


def _cleanup(created: list[Path], kept_map: dict[str, str]) -> None:
    """Delete files written this cycle that the surviving map doesn't reference."""
    kept = {str(p) for p in kept_map.values()}
    for path in created:
        if str(path) not in kept:
            path.unlink(missing_ok=True)


def _save_digest(result: AutoResearchResult, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"auto_research_{result.generated_at.strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path
