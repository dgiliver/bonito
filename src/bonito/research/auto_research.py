"""Autonomous research cycle: keep symbol_strategies current without a human.

This is the zero-intervention layer on top of per-symbol research. Weekly
(or on demand) it:

1. Re-runs the per-symbol grid sweep with a ROLLING holdout window, so the
   out-of-sample boundary advances with the calendar instead of decaying
   into in-sample data.
2. Rebuilds the symbol_strategies map STATELESSLY: an override exists only
   while its winner currently passes the holdout kill filter AND made money
   out-of-sample. Symbols whose winners stop passing revert to the default
   strategy (the longest-validated config).
3. Gates the whole bundle on the account replay — the same pre-registered
   criterion used for manual experiments (docs/EXPERIMENT_LOG.md): neither
   the train nor the holdout window may degrade vs the current config, and
   no new kill-filter failures may appear. All-or-nothing per cycle; a
   rejected bundle leaves universe.json untouched and is retried next run.
4. Writes a digest to livetrade/research/ either way, so every automated
   decision has an audit trail.

This module never touches mode, live_enabled, or risk caps — only
symbol_strategies. Those flags remain human-only by construction.
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
    run_cluster_research,
    save_report,
)
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import (
    AccountBacktestResult,
    ReplayStore,
    backtest_account,
)

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


class AutoResearchResult(BaseModel):
    """Digest of one autonomous research cycle — the audit record."""

    generated_at: datetime
    universe_path: str
    start: datetime
    holdout: datetime
    end: datetime
    outcome: Literal["unchanged", "adopted", "rejected"]
    reasons: list[str] = Field(default_factory=list)
    previous_assignments: dict[str, str]
    candidate_assignments: dict[str, str]
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
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


def run_auto_research(
    universe_path: Path,
    store,
    end: datetime | None = None,
    grid: GridSpec | None = None,
    apply: bool = False,
    strategies_dir: Path = Path("strategies"),
    research_dir: Path = Path("livetrade/research"),
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
    previous = {s.upper(): p for s, p in universe.symbol_strategies.items()}

    result = AutoResearchResult(
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
        report_path=str(report_path),
    )

    if candidate_map == previous:
        _cleanup(created, candidate_map)
        _save_digest(result, research_dir)
        return result

    # The bundle gate: replay the account under both maps over identical bars.
    candidate_universe = universe.model_copy(update={"symbol_strategies": candidate_map})
    replay = ReplayStore.from_store(store, candidate_universe, end)
    baseline = backtest_account(universe, replay, start, end)
    candidate = backtest_account(candidate_universe, replay, start, end)
    adopted, reasons, comparisons = decide_adoption(baseline, candidate, start, holdout, end)

    result.reasons = reasons
    result.comparisons = comparisons
    result.baseline_final_equity = round(baseline.final_equity, 2)
    result.candidate_final_equity = round(candidate.final_equity, 2)
    result.outcome = "adopted" if adopted else "rejected"

    if adopted and apply:
        config = json.loads(universe_path.read_text())
        config["symbol_strategies"] = dict(sorted(candidate_map.items()))
        universe_path.write_text(json.dumps(config, indent=2) + "\n")
    else:
        # Rejected, or a dry run: universe.json keeps the previous map, so
        # strategy files written this cycle must not linger unreferenced.
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
