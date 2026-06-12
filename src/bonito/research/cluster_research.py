"""Per-cluster strategy research: populate universe.symbol_strategies responsibly.

Symbols are clustered by realized volatility, then each cluster is searched
over a small, fixed parameter grid around the deployed strategy family
(EMA cross + RSI gate + ATR trailing stop + SPY/200 regime filter).

Overfitting guardrails, in order of importance:
- Candidates are RANKED on the train window only ([start, holdout)).
  The holdout window ([holdout, end]) is touched exactly once, by the
  single winning candidate, as a pass/fail kill-filter gate — never for
  ranking, so it can't be mined.
- Cross-sectional sanity: a candidate is eligible only if it passes the
  train-window kill filter on at least half the cluster's members. A
  config that only works on one ticker's path is noise.
- The search space is deliberately small (~144 configs) and structured;
  the regime filter is always on (structural risk decision, not a knob).
- Assignments are written per symbol only where the winner passes the
  holdout kill filter for that symbol AND made money in the holdout.
  Everything else keeps the default.

The whole sweep is deterministic — same data in, same assignments out —
and the full report is written to livetrade/research/ for audit.
"""

import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData
from bonito.data.store import MarketDataStore
from bonito.trading.live_runner import REGIME_WARMUP_DAYS, UniverseConfig
from bonito.trading.validation import WindowMetrics, kill_verdict, strategy_hash, window_metrics

logger = logging.getLogger(__name__)

TRADING_DAYS = 252

# Volatility buckets (annualized stdev of daily returns) → cluster name.
DEFAULT_BUCKETS: list[tuple[float, str]] = [
    (0.30, "defensive"),
    (0.50, "core"),
    (0.75, "growth"),
    (float("inf"), "speculative"),
]


class GridSpec(BaseModel):
    """The candidate search space. Keep it small on purpose."""

    ema_pairs: list[tuple[int, int]] = [(8, 21), (10, 26), (12, 26), (20, 50)]
    rsi_max: list[float] = [60.0, 68.0, 75.0]
    atr_mult: list[float] = [1.5, 2.0, 2.5, 3.0]
    take_profit: list[float | None] = [0.10, 0.20, None]


class MemberVerdict(BaseModel):
    """Winner's holdout result for one cluster member."""

    symbol: str
    train: WindowMetrics
    holdout: WindowMetrics
    holdout_reasons: list[str]

    @property
    def passes(self) -> bool:
        return not self.holdout_reasons


class ClusterResult(BaseModel):
    name: str
    members: list[str]
    volatility: dict[str, float]
    candidates_evaluated: int
    candidates_eligible: int
    winner_name: str | None = None
    winner_hash: str | None = None
    winner_config: dict | None = None
    winner_train_score: float | None = None
    verdicts: list[MemberVerdict] = Field(default_factory=list)

    @property
    def passing_symbols(self) -> list[str]:
        return [v.symbol for v in self.verdicts if v.passes]


class ResearchReport(BaseModel):
    generated_at: datetime
    start: datetime
    holdout: datetime
    end: datetime
    default_strategy_hash: str
    clusters: list[ClusterResult]

    def assignments(self) -> dict[str, ClusterResult]:
        """Symbol → cluster result, only for pairs that pass the holdout gate
        with a winner that differs from the deployed default."""
        out: dict[str, ClusterResult] = {}
        for cluster in self.clusters:
            if cluster.winner_hash is None or cluster.winner_hash == self.default_strategy_hash:
                continue
            for symbol in cluster.passing_symbols:
                out[symbol] = cluster
        return out


def annualized_volatility(data: BarData) -> float:
    """Annualized stdev of daily close-to-close returns."""
    closes = np.asarray(data.closes, dtype=float)
    if len(closes) < 30:
        return float("inf")  # too little history to trust — bucket as speculative
    returns = np.diff(closes) / closes[:-1]
    return float(np.std(returns) * np.sqrt(TRADING_DAYS))


def cluster_universe(
    universe: UniverseConfig,
    store: MarketDataStore,
    start: datetime,
    end: datetime,
    buckets: list[tuple[float, str]] | None = None,
) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Bucket universe symbols by realized volatility.

    Returns:
        (cluster name → symbols, symbol → annualized vol). Symbols without
        data are omitted entirely (they can't be researched or validated).
    """
    buckets = buckets or DEFAULT_BUCKETS
    clusters: dict[str, list[str]] = {name: [] for _, name in buckets}
    vols: dict[str, float] = {}
    for symbol in universe.symbols:
        data = store.get_bars(symbol, start, end, universe.data.timeframe)
        if data is None or len(data) < 30:
            logger.warning(f"{symbol}: insufficient data, excluded from research")
            continue
        vol = annualized_volatility(data)
        vols[symbol] = round(vol, 4)
        for ceiling, name in buckets:
            if vol < ceiling:
                clusters[name].append(symbol)
                break
    return {name: members for name, members in clusters.items() if members}, vols


def candidate_grid(grid: GridSpec | None = None) -> list[StrategyConfig]:
    """Materialize the search space as concrete strategy configs."""
    grid = grid or GridSpec()
    candidates = []
    for fast, slow in grid.ema_pairs:
        for rsi in grid.rsi_max:
            for atr in grid.atr_mult:
                for tp in grid.take_profit:
                    tp_label = f"{int(tp * 100)}" if tp is not None else "none"
                    candidates.append(
                        StrategyConfig(
                            name=f"c_ema{fast}-{slow}_rsi{int(rsi)}_atr{atr}_tp{tp_label}",
                            description=(
                                f"EMA {fast}/{slow} cross + RSI<{int(rsi)}, {atr}x ATR(14) "
                                f"trailing stop, TP {tp_label}%, SPY>SMA200 regime gate"
                            ),
                            version="1.0",
                            symbols=["SPY"],
                            timeframe="1d",
                            indicators=[
                                {"type": "ema", "name": "ema_fast", "params": {"period": fast}},
                                {"type": "ema", "name": "ema_slow", "params": {"period": slow}},
                                {"type": "rsi", "name": "rsi_14", "params": {"period": 14}},
                            ],
                            entry_rules=[
                                {
                                    "conditions": [
                                        {
                                            "left": "ema_fast",
                                            "comparison": "gt",
                                            "right": "ema_slow",
                                        },
                                        {"left": "close", "comparison": "gt", "right": "ema_slow"},
                                        {"left": "rsi_14", "comparison": "lt", "right": rsi},
                                    ],
                                    "logic": "AND",
                                    "side": "long",
                                }
                            ],
                            exit_rules=[
                                {
                                    "conditions": [
                                        {
                                            "left": "ema_fast",
                                            "comparison": "crosses_below",
                                            "right": "ema_slow",
                                        }
                                    ],
                                    "logic": "AND",
                                    "side": "long",
                                }
                            ],
                            position_size={"type": "percent_equity", "value": 98.0},
                            max_positions=1,
                            stop_loss={"type": "trailing_atr", "value": atr, "atr_period": 14},
                            take_profit=(
                                {"type": "percent", "value": tp} if tp is not None else None
                            ),
                            regime_filter={"symbol": "SPY", "sma_period": 200},
                        )
                    )
    return candidates


def research_cluster(
    name: str,
    members: list[str],
    vols: dict[str, float],
    candidates: list[StrategyConfig],
    store: MarketDataStore,
    universe: UniverseConfig,
    start: datetime,
    holdout: datetime,
    end: datetime,
    initial_capital: float = 5000.0,
    progress=None,
) -> ClusterResult:
    """Rank candidates on the train window, gate the single winner on holdout."""
    engine = BacktestEngine(
        BacktestConfig(start_date=start, end_date=end, initial_capital=initial_capital)
    )
    regime_data = store.get_bars(
        "SPY", start - timedelta(days=REGIME_WARMUP_DAYS), end, universe.data.timeframe
    )
    bars = {s: store.get_bars(s, start, end, universe.data.timeframe) for s in members}
    train_end = holdout - timedelta(days=1)
    majority = (len(members) + 1) // 2

    # One simulation per (candidate, member); results kept so the winner's
    # holdout gate reuses them instead of re-running.
    eligible = 0
    best_score: float | None = None
    best: tuple[StrategyConfig, dict] | None = None
    for candidate in candidates:
        results = {}
        train_sharpes = []
        for symbol in members:
            data = bars[symbol]
            if data is None or len(data) < 50:
                continue
            per_symbol = candidate.model_copy(update={"symbols": [symbol]})
            result = engine.run(per_symbol, data, regime_data=regime_data)
            results[symbol] = result
            train = window_metrics(result, start, train_end)
            if not kill_verdict(train):
                train_sharpes.append(train.sharpe)
        if progress is not None:
            progress()
        if len(train_sharpes) < majority:
            continue
        eligible += 1
        score = statistics.median(train_sharpes)
        if best_score is None or score > best_score:
            best_score = score
            best = (candidate, results)

    cluster = ClusterResult(
        name=name,
        members=members,
        volatility={s: vols.get(s, 0.0) for s in members},
        candidates_evaluated=len(candidates),
        candidates_eligible=eligible,
    )
    if best is None:
        return cluster

    winner, results = best
    cluster.winner_name = winner.name
    cluster.winner_hash = strategy_hash(winner)
    cluster.winner_config = winner.model_dump(mode="json")
    cluster.winner_train_score = round(best_score, 4) if best_score is not None else None
    for symbol in members:
        result = results.get(symbol)
        if result is None:
            continue
        hold = window_metrics(result, holdout, end)
        reasons = kill_verdict(hold)
        # Assignment-specific gate on top of the kill filter: never switch a
        # symbol off the default onto a config that LOST money out-of-sample.
        if hold.total_return <= 0:
            reasons.append(f"holdout return {hold.total_return * 100:+.1f}%≤0")
        cluster.verdicts.append(
            MemberVerdict(
                symbol=symbol,
                train=window_metrics(result, start, train_end),
                holdout=hold,
                holdout_reasons=reasons,
            )
        )
    return cluster


def run_cluster_research(
    universe: UniverseConfig,
    store: MarketDataStore,
    start: datetime,
    holdout: datetime,
    end: datetime,
    grid: GridSpec | None = None,
    progress=None,
    per_symbol: bool = False,
) -> ResearchReport:
    """Full sweep: cluster the universe, research each cluster independently.

    With per_symbol=True every ticker becomes its own singleton cluster, so
    each symbol gets the grid winner ranked on ITS OWN train window. The
    cross-sectional sanity vote degenerates to 1-of-1 — the holdout kill
    filter is then the only out-of-sample protection, so treat per-symbol
    assignments with more suspicion than cluster-level ones.
    """
    clusters, vols = cluster_universe(universe, store, start, end)
    if per_symbol:
        clusters = {s: [s] for s in sorted(vols)}
    candidates = candidate_grid(grid)
    results = [
        research_cluster(
            name,
            members,
            vols,
            candidates,
            store,
            universe,
            start,
            holdout,
            end,
            initial_capital=universe.risk.starting_cash_usd,
            progress=progress,
        )
        for name, members in clusters.items()
    ]
    return ResearchReport(
        generated_at=datetime.now(),
        start=start,
        holdout=holdout,
        end=end,
        default_strategy_hash=strategy_hash(universe.load_strategy()),
        clusters=results,
    )


def apply_assignments(
    report: ResearchReport,
    universe_path: Path,
    strategies_dir: Path = Path("strategies"),
) -> dict[str, str]:
    """Write winning strategies to disk and merge into universe.symbol_strategies.

    Only pairs that passed the holdout gate are assigned; existing
    assignments for other symbols are preserved. Open positions are
    unaffected — they exit under the strategy pinned at entry.

    Returns:
        Symbol → strategy path that was assigned.
    """
    assignments = report.assignments()
    if not assignments:
        return {}

    strategies_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    paths_by_hash: dict[str, str] = {}
    for symbol, cluster in sorted(assignments.items()):
        assert cluster.winner_hash and cluster.winner_config
        if cluster.winner_hash not in paths_by_hash:
            path = strategies_dir / f"cluster_{cluster.name}_{cluster.winner_hash}.json"
            path.write_text(json.dumps(cluster.winner_config, indent=2))
            paths_by_hash[cluster.winner_hash] = str(path)
        written[symbol] = paths_by_hash[cluster.winner_hash]

    config = json.loads(universe_path.read_text())
    config.setdefault("symbol_strategies", {}).update(written)
    universe_path.write_text(json.dumps(config, indent=2) + "\n")
    return written


def save_report(report: ResearchReport, directory: Path = Path("livetrade/research")) -> Path:
    """Persist the full research report for audit."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"cluster_report_{report.generated_at.strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(report.model_dump_json(indent=2))
    return path
