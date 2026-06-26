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
- The search space is deliberately small (~450 configs) and structured;
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


class ADXTrendGrid(BaseModel):
    """ADX(14) trend-strength gate + directional EMA filter (no crossover).

    Diversifies from EMA-cross: requires a confirmed strong trend (ADX
    above threshold) AND price above a single trend EMA, instead of a
    fast/slow EMA crossover.
    """

    adx_threshold: list[float] = [15.0, 20.0, 25.0]
    ema_period: list[int] = [30, 50, 100]
    atr_mult: list[float] = [1.5, 2.0, 2.5]


class MACDCrossGrid(BaseModel):
    """MACD line/signal crossover, RSI-filtered against overbought entries.

    Pure momentum-crossover signal — structurally distinct from both the
    EMA-cross and ADX-trend templates.
    """

    macd_params: list[tuple[int, int, int]] = [(12, 26, 9), (8, 17, 9), (5, 35, 5)]
    rsi_max: list[float] = [60.0, 70.0]
    atr_mult: list[float] = [1.5, 2.0, 2.5]


class BBandsMeanRevGrid(BaseModel):
    """Bollinger Band mean-reversion: buy the lower-band touch (RSI-confirmed
    oversold), exit at the mid-band.

    The one non-trend-following template — expected to behave differently
    across regimes than the other three (see the regime breakdown report
    before trusting any single aggregate Sharpe number for this family).
    """

    bb_period: list[int] = [14, 20]
    bb_std: list[float] = [2.0, 2.5]
    rsi_max: list[float] = [30.0, 35.0]
    atr_mult: list[float] = [1.5, 2.0]


class GridSpec(BaseModel):
    """The candidate search space. Keep it small on purpose.

    Extended 2026-06-12 after grid-edge flags: every adopted winner sat at
    the ema/rsi/atr minimums, so each flagged axis gained headroom below
    (ema (5,13), rsi 50/55, atr 1.0/1.25). 450 candidates total — growth
    is deliberate and one-time; auto-research flags edges, humans extend.

    Extended 2026-06-18: three opt-in template families (adx, macd,
    bbands) alongside the original EMA-cross template, each its own small
    grid (16-27 candidates). All default to None (disabled) —
    candidate_grid() with no args still returns exactly the same 450
    EMA-only candidates as before. Enable a template explicitly (e.g.
    GridSpec(adx=ADXTrendGrid())) to include it; auto research / --apply
    runs stay on the EMA-only default until a human deliberately opts in,
    same philosophy as the grid-size growth above.
    """

    ema_pairs: list[tuple[int, int]] = [(5, 13), (8, 21), (10, 26), (12, 26), (20, 50)]
    rsi_max: list[float] = [50.0, 55.0, 60.0, 68.0, 75.0]
    atr_mult: list[float] = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    take_profit: list[float | None] = [0.10, 0.20, None]

    adx: ADXTrendGrid | None = None
    macd: MACDCrossGrid | None = None
    bbands: BBandsMeanRevGrid | None = None


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


def _ema_cross_candidates(grid: GridSpec) -> list[StrategyConfig]:
    """Original template: EMA fast/slow cross entry + RSI filter + EMA-cross
    exit + ATR trailing stop. ~450 candidates at default grid size."""
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


def _adx_trend_candidates(grid: ADXTrendGrid) -> list[StrategyConfig]:
    """ADX(14) trend-strength gate + directional EMA filter.

    Entry requires both a confirmed strong trend (ADX above threshold) and
    price above the trend EMA. Exit on either condition failing — trend
    weakens or price falls back below the EMA, whichever comes first.
    """
    candidates = []
    for threshold in grid.adx_threshold:
        for ema_period in grid.ema_period:
            for atr in grid.atr_mult:
                candidates.append(
                    StrategyConfig(
                        name=f"c_adx{int(threshold)}_ema{ema_period}_atr{atr}",
                        description=(
                            f"ADX(14)>{int(threshold)} trend-strength gate + close>EMA"
                            f"{ema_period}, {atr}x ATR(14) trailing stop, SPY>SMA200 regime gate"
                        ),
                        version="1.0",
                        symbols=["SPY"],
                        timeframe="1d",
                        indicators=[
                            {"type": "adx", "name": "adx", "params": {"length": 14}},
                            {
                                "type": "ema",
                                "name": "ema_trend",
                                "params": {"period": ema_period},
                            },
                        ],
                        entry_rules=[
                            {
                                "conditions": [
                                    {"left": "adx_adx", "comparison": "gt", "right": threshold},
                                    {"left": "close", "comparison": "gt", "right": "ema_trend"},
                                ],
                                "logic": "AND",
                                "side": "long",
                            }
                        ],
                        exit_rules=[
                            {
                                "conditions": [
                                    {"left": "adx_adx", "comparison": "lt", "right": threshold},
                                    {"left": "close", "comparison": "lt", "right": "ema_trend"},
                                ],
                                "logic": "OR",
                                "side": "long",
                            }
                        ],
                        position_size={"type": "percent_equity", "value": 98.0},
                        max_positions=1,
                        stop_loss={"type": "trailing_atr", "value": atr, "atr_period": 14},
                        take_profit=None,
                        regime_filter={"symbol": "SPY", "sma_period": 200},
                    )
                )
    return candidates


def _macd_cross_candidates(grid: MACDCrossGrid) -> list[StrategyConfig]:
    """MACD line/signal crossover, RSI-filtered against overbought entries."""
    candidates = []
    for fast, slow, signal in grid.macd_params:
        for rsi in grid.rsi_max:
            for atr in grid.atr_mult:
                candidates.append(
                    StrategyConfig(
                        name=f"c_macd{fast}-{slow}-{signal}_rsi{int(rsi)}_atr{atr}",
                        description=(
                            f"MACD({fast},{slow},{signal}) line crosses signal + RSI<{int(rsi)}, "
                            f"{atr}x ATR(14) trailing stop, SPY>SMA200 regime gate"
                        ),
                        version="1.0",
                        symbols=["SPY"],
                        timeframe="1d",
                        indicators=[
                            {
                                "type": "macd",
                                "name": "macd",
                                "params": {
                                    "fast_period": fast,
                                    "slow_period": slow,
                                    "signal_period": signal,
                                },
                            },
                            {"type": "rsi", "name": "rsi_14", "params": {"period": 14}},
                        ],
                        entry_rules=[
                            {
                                "conditions": [
                                    {
                                        "left": "macd_line",
                                        "comparison": "crosses_above",
                                        "right": "macd_signal",
                                    },
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
                                        "left": "macd_line",
                                        "comparison": "crosses_below",
                                        "right": "macd_signal",
                                    }
                                ],
                                "logic": "AND",
                                "side": "long",
                            }
                        ],
                        position_size={"type": "percent_equity", "value": 98.0},
                        max_positions=1,
                        stop_loss={"type": "trailing_atr", "value": atr, "atr_period": 14},
                        take_profit=None,
                        regime_filter={"symbol": "SPY", "sma_period": 200},
                    )
                )
    return candidates


def _bbands_meanrev_candidates(grid: BBandsMeanRevGrid) -> list[StrategyConfig]:
    """Bollinger Band mean-reversion: buy the lower-band touch (RSI-confirmed
    oversold), exit at the mid-band. The one non-trend-following template."""
    candidates = []
    for period in grid.bb_period:
        for std in grid.bb_std:
            for rsi in grid.rsi_max:
                for atr in grid.atr_mult:
                    candidates.append(
                        StrategyConfig(
                            name=f"c_bb{period}-{std}_rsi{int(rsi)}_atr{atr}",
                            description=(
                                f"Bollinger({period},{std}) lower-band touch + RSI<{int(rsi)} "
                                f"entry, mid-band exit, {atr}x ATR(14) trailing stop, "
                                f"SPY>SMA200 regime gate"
                            ),
                            version="1.0",
                            symbols=["SPY"],
                            timeframe="1d",
                            indicators=[
                                {
                                    "type": "bbands",
                                    "name": "bb",
                                    "params": {"period": period, "std_dev": std},
                                },
                                {"type": "rsi", "name": "rsi_14", "params": {"period": 14}},
                            ],
                            entry_rules=[
                                {
                                    "conditions": [
                                        {
                                            "left": "close",
                                            "comparison": "crosses_below",
                                            "right": "bb_lower",
                                        },
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
                                            "left": "close",
                                            "comparison": "crosses_above",
                                            "right": "bb_middle",
                                        }
                                    ],
                                    "logic": "AND",
                                    "side": "long",
                                }
                            ],
                            position_size={"type": "percent_equity", "value": 98.0},
                            max_positions=1,
                            stop_loss={"type": "trailing_atr", "value": atr, "atr_period": 14},
                            take_profit=None,
                            regime_filter={"symbol": "SPY", "sma_period": 200},
                        )
                    )
    return candidates


def candidate_grid(grid: GridSpec | None = None) -> list[StrategyConfig]:
    """Materialize the search space as concrete strategy configs.

    Always includes the EMA-cross template. The adx/macd/bbands template
    families are opt-in — pass a GridSpec with that field set (e.g.
    GridSpec(adx=ADXTrendGrid())) to include them. With no args this
    returns exactly the original 450 EMA-only candidates.
    """
    grid = grid or GridSpec()
    candidates = _ema_cross_candidates(grid)
    if grid.adx is not None:
        candidates += _adx_trend_candidates(grid.adx)
    if grid.macd is not None:
        candidates += _macd_cross_candidates(grid.macd)
    if grid.bbands is not None:
        candidates += _bbands_meanrev_candidates(grid.bbands)
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
