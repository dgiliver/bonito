"""Grade a universe+strategy against the market — the 2026-10 profitability review's harness.

The weekly research loop asks "did Sharpe degrade vs the current config?" on a
universe assembled from names that had already run up. That question can't detect
a timing layer that loses to simply holding the index. This one asks the question
that matters, with the criterion pre-registered in docs/PROFITABILITY_REVIEW_2026-10.md:

    BEATS iff, against the reference benchmark (default QQQ):
      full window : strategy CAGR > benchmark CAGR, Sharpe > benchmark Sharpe,
                    max drawdown <= MAX_DD_RATIO (1.25) x benchmark max drawdown
                    (user decision 2026-10-14: "higher return, similar risk")
      sub-window  : CAGR and Sharpe both beat it again (fresh account from sub_start)
      robustness  : re-run WITHOUT the top-N P&L contributors still beats its CAGR

Defaults are chosen for diagnosis, not trading: the kill switch is OFF (a latched
halt would make the replay measure "sat in cash after a drawdown", not the
strategy). "hold-universe" (equal-weight hold of the same symbols) is reported as
the timing-value check — on a hindsight-picked list it is the honest bar.

Report-only. Nothing here touches config, ledgers or the trading path.
"""

import math
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from bonito.trading.benchmarks import HOLD_UNIVERSE, benchmark_series
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import ReplayStore, backtest_account

TRADING_DAYS = 252
# Drawdown allowance vs the benchmark (docs/STRATEGY_SEARCH_2026-10.md).
MAX_DD_RATIO = 1.25


class CurveStats(BaseModel):
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float


def curve_stats(dates: list[date], values: list[float]) -> CurveStats | None:
    """Return/CAGR/Sharpe(all days, sqrt 252)/max drawdown for one value series."""
    pairs = [(d, v) for d, v in zip(dates, values, strict=True) if v and v > 0]
    if len(pairs) < 3:
        return None
    ds, vs = zip(*pairs, strict=True)
    rets = [b / a - 1 for a, b in zip(vs[:-1], vs[1:], strict=True)]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0.0
    years = max((ds[-1] - ds[0]).days / 365.25, 1e-9)
    peak, mdd = vs[0], 0.0
    for v in vs:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    return CurveStats(
        total_return_pct=round((vs[-1] / vs[0] - 1) * 100, 2),
        cagr_pct=round(((vs[-1] / vs[0]) ** (1 / years) - 1) * 100, 2),
        sharpe=round(mean / sd * math.sqrt(TRADING_DAYS), 3) if sd > 0 else 0.0,
        max_drawdown_pct=round(mdd * 100, 2),
    )


class WindowEval(BaseModel):
    label: str
    start: date
    end: date
    strategy: CurveStats | None
    benchmarks: dict[str, CurveStats | None] = Field(default_factory=dict)
    trades: int = 0
    win_rate: float = 0.0
    pct_days_in_market: float = 0.0
    halted: bool = False
    per_symbol_pnl: dict[str, float] = Field(
        default_factory=dict,
        description="Realized P&L plus unrealized on positions still open at the end — "
        "a winner held to the end is a top contributor too",
    )


class BenchmarkEval(BaseModel):
    universe_name: str
    generated_at: datetime
    vs: str
    kill_switch: bool
    windows: list[WindowEval]
    excluded_top: list[str] = Field(default_factory=list)
    ex_top: WindowEval | None = None
    yearly: dict[int, dict[str, float | None]] = Field(default_factory=dict)
    checks: dict[str, bool | None] = Field(default_factory=dict)
    timing_beats_hold_universe: bool | None = Field(
        None, description="Informational: does timing beat equal-weight holding the same names?"
    )
    verdict: Literal["BEATS", "DOES_NOT_BEAT", "INCONCLUSIVE"]


def judge(
    full: WindowEval,
    sub: WindowEval | None,
    ex_top: WindowEval | None,
    vs: str,
    max_dd_ratio: float = MAX_DD_RATIO,
) -> tuple[dict[str, bool | None], str]:
    """Apply the pre-registered criterion.

    All six checks are ALWAYS present: a window that wasn't run (sub-window outside
    the range or disabled, ex-top skipped) or lacks data is ``None``. Any failed
    check → DOES_NOT_BEAT; otherwise any ``None`` → INCONCLUSIVE; only all six
    passing → BEATS. A partial run can never pass.
    """

    def beats(w: WindowEval | None, *, sharpe: bool, dd: bool) -> dict[str, bool | None]:
        s = w.strategy if w else None
        b = w.benchmarks.get(vs) if w else None
        if s is None or b is None:
            keys = ["cagr"] + (["sharpe"] if sharpe else []) + (["dd"] if dd else [])
            return dict.fromkeys(keys)
        out: dict[str, bool | None] = {"cagr": s.cagr_pct > b.cagr_pct}
        if sharpe:
            out["sharpe"] = s.sharpe > b.sharpe
        if dd:
            out["dd"] = s.max_drawdown_pct <= max_dd_ratio * b.max_drawdown_pct
        return out

    checks: dict[str, bool | None] = {}
    for k, v in beats(full, sharpe=True, dd=True).items():
        checks[f"full_{k}"] = v
    for k, v in beats(sub, sharpe=True, dd=False).items():
        checks[f"sub_{k}"] = v
    checks["ex_top_cagr"] = beats(ex_top, sharpe=False, dd=False)["cagr"]
    if any(v is False for v in checks.values()):
        return checks, "DOES_NOT_BEAT"
    if any(v is None for v in checks.values()):
        return checks, "INCONCLUSIVE"
    return checks, "BEATS"


def _contributions(result, replay: ReplayStore, end: datetime) -> dict[str, float]:
    """Per-symbol realized P&L + unrealized P&L marked at the last close <= end."""
    out = dict(result.per_symbol_pnl)
    for symbol, entry in result.open_position_entries.items():
        bars = replay.bars.get(symbol)
        closes = (
            [c for ts, c in zip(bars.timestamps, bars.closes, strict=True) if ts <= end]
            if bars
            else []
        )
        if closes:
            out[symbol] = out.get(symbol, 0.0) + (closes[-1] - entry.entry_price) * entry.quantity
    return {k: round(v, 2) for k, v in out.items()}


def _run_window(
    universe: UniverseConfig, store, replay: ReplayStore, label: str, start: datetime, end: datetime
) -> tuple[WindowEval, dict[date, float], dict[str, dict[date, float]]]:
    """One fresh-account replay of [start, end] plus every benchmark over the same span."""
    result = backtest_account(universe, replay, start, end, intraday_stops=True)
    dates = [d.date() for d in result.equity_dates]
    series = benchmark_series(store, universe, start, end)
    return (
        WindowEval(
            label=label,
            start=start.date(),
            end=end.date(),
            strategy=curve_stats(dates, list(result.equity_curve)),
            benchmarks={
                k: curve_stats(sorted(s), [s[d] for d in sorted(s)]) for k, s in series.items()
            },
            trades=len(result.trades),
            win_rate=round(result.win_rate, 4),
            pct_days_in_market=round(result.pct_days_in_market, 4),
            halted=result.halted,
            per_symbol_pnl=_contributions(result, replay, end),
        ),
        dict(zip(dates, result.equity_curve, strict=True)),
        series,
    )


def _yearly(strategy: dict[date, float], series: dict[str, dict[date, float]]) -> dict:
    out: dict[int, dict[str, float | None]] = {}
    for year in sorted({d.year for d in strategy}):
        row: dict[str, float | None] = {}
        for label, s in {"strategy": strategy, **series}.items():
            prior = [d for d in s if d.year < year]
            inside = [d for d in s if d.year == year]
            if not inside:
                row[label] = None
                continue
            first = max(prior) if prior else min(inside)
            row[label] = round((s[max(inside)] / s[first] - 1) * 100, 2) if s[first] else None
        out[year] = row
    return out


def evaluate_vs_benchmarks(
    universe: UniverseConfig,
    store,
    start: datetime,
    end: datetime,
    *,
    sub_start: datetime | None = datetime(2022, 1, 3),
    vs: str = "QQQ",
    kill_switch: bool = False,
    exclude_top: int = 2,
) -> BenchmarkEval:
    """Run the full window, the sub-window and the ex-top-N robustness run, then judge."""
    if not kill_switch:
        universe = universe.model_copy(
            update={"risk": universe.risk.model_copy(update={"max_drawdown_halt": 1.0})}
        )
    replay = ReplayStore.from_store(store, universe, end)
    full, full_curve, full_series = _run_window(universe, store, replay, "full", start, end)
    windows = [full]
    sub = None
    if sub_start is not None and start < sub_start < end:
        sub = _run_window(universe, store, replay, "sub", sub_start, end)[0]
        windows.append(sub)

    excluded: list[str] = []
    ex_top = None
    if exclude_top > 0:
        winners = sorted(full.per_symbol_pnl.items(), key=lambda kv: kv[1], reverse=True)
        excluded = [s for s, pnl in winners[:exclude_top] if pnl > 0]
        remaining = [s for s in universe.symbols if s not in excluded]
        if excluded and remaining:
            reduced = universe.model_copy(update={"symbols": remaining})
            ex_top = _run_window(reduced, store, replay, f"ex-top-{len(excluded)}", start, end)[0]

    checks, verdict = judge(full, sub, ex_top, vs)
    s, h = full.strategy, full.benchmarks.get(HOLD_UNIVERSE)
    return BenchmarkEval(
        universe_name=universe.name,
        generated_at=datetime.now(),
        vs=vs,
        kill_switch=kill_switch,
        windows=windows,
        excluded_top=excluded,
        ex_top=ex_top,
        yearly=_yearly(full_curve, full_series),
        checks=checks,
        timing_beats_hold_universe=None if s is None or h is None else s.cagr_pct > h.cagr_pct,
        verdict=verdict,  # type: ignore[arg-type]
    )


def save_benchmark_eval(
    report: BenchmarkEval, directory: Path = Path("livetrade/research")
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"benchmark_eval_{report.generated_at:%Y-%m-%d_%H%M%S}.json"
    path.write_text(report.model_dump_json(indent=2))
    return path
