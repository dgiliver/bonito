"""Pre-registered strategy search (docs/STRATEGY_SEARCH_2026-10.md), run exactly as registered.

    python scripts/experiments/2026-10-14_momentum_rotation_search.py [--skip-ingest]

1. Pool: point-in-time NASDAQ-100 (data/reference/ndx_membership.json, quarterly
   Wikipedia snapshots) ∪ the 45 names from their add dates
   (data/reference/universe_additions.json).
2. Prices: Yahoo daily OHLC into data/research/rotation.duckdb.
3. Four fixed variants on the DESIGN window (2016-01-04 → 2021-12-31); select the
   highest-Sharpe variant among those passing the criterion vs QQQ there. None pass →
   REJECTED, holdout never run.
4. Selected variant: ONE holdout run (2022-01-03 → 2026-10-13) + ex-top-2 rerun.
5. Writes livetrade/research/strategy_search_2026-10.json and prints the verdict.

Data-cleaning rules, fixed before any result was computed:
- RENAMES map historical tickers to their current Yahoo symbol (same company).
- SECONDARY_CLASSES: one share class per company (e.g. keep GOOGL, drop GOOG), so
  the top-N can't hold the same company twice.
- Members whose prices can't be fetched (acquired/delisted) are listed in the
  output as survivorship gaps; they bias results IN FAVOUR of the strategy.
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from bonito.data.store import MarketDataStore
from bonito.research.benchmark_eval import MAX_DD_RATIO, curve_stats
from bonito.research.rotation import PointInTimePool, RotationConfig, run_rotation

RENAMES = {
    "FB": "META",
    "PCLN": "BKNG",
    "MYL": "VTRS",
    "CTRP": "TCOM",
    "FISV": "FI",
    "SYMC": "GEN",
    "NLOK": "GEN",
    "DISCA": "WBD",
    "QVCA": "QRTEA",
    "VIAB": "PARA",
    "VIAC": "PARA",
    "BRK.B": "BRK-B",
}
SECONDARY_CLASSES = {
    "GOOG",
    "FOX",
    "LBTYK",
    "LBTYB",
    "LILAK",
    "DISCK",
    "DISCB",
    "LMCK",
    "NWS",
    "QVCB",
    "LBRDK",
    "FWONK",
    "BATRK",
}

DESIGN = (date(2016, 1, 4), date(2021, 12, 31))
HOLDOUT = (date(2022, 1, 3), date(2026, 10, 13))
VARIANTS = [
    RotationConfig(name="M6-T5", lookback_months=6, top_n=5),
    RotationConfig(name="M6-T10", lookback_months=6, top_n=10),
    RotationConfig(name="M12-T5", lookback_months=12, top_n=5),
    RotationConfig(name="M12-T10", lookback_months=12, top_n=10),
]
DB = Path("data/research/rotation.duckdb")
OUT = Path("livetrade/research/strategy_search_2026-10.json")


def build_pool() -> PointInTimePool:
    pool = PointInTimePool.from_files(
        Path("data/reference/ndx_membership.json"),
        Path("data/reference/universe_additions.json"),
        renames=RENAMES,
    )
    # drop secondary share classes everywhere
    pool._sets = [frozenset(s - SECONDARY_CLASSES) for s in pool._sets]
    return pool


def load_prices(symbols: list[str], ingest: bool) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    DB.parent.mkdir(parents=True, exist_ok=True)
    store = MarketDataStore(db_path=DB)
    missing: list[str] = []
    opens, closes = {}, {}
    for s in symbols:
        if ingest:
            try:
                store.ingest_from_yahoo(s, datetime(2014, 6, 1), datetime(2026, 10, 15), "1d")
            except Exception as e:  # noqa: BLE001 — record and continue
                print(f"  ingest failed {s}: {type(e).__name__}", flush=True)
        b = store.get_bars(s, datetime(2014, 6, 1), datetime(2026, 10, 15), "1d")
        if b is None or len(b) == 0:
            missing.append(s)
            continue
        idx = pd.DatetimeIndex([pd.Timestamp(t.date()) for t in b.timestamps])
        opens[s] = pd.Series(b.opens, index=idx)
        closes[s] = pd.Series(b.closes, index=idx)
    o = pd.DataFrame(opens).sort_index()
    c = pd.DataFrame(closes).sort_index()
    return o[~o.index.duplicated()], c[~c.index.duplicated()], missing


def stats_on(dates: list[date], values: list[float]):
    return curve_stats(dates, values)


def evaluate(result, closes: pd.DataFrame) -> dict:
    s = stats_on(result.dates, result.equity)
    q = closes["QQQ"].reindex(pd.DatetimeIndex([pd.Timestamp(d) for d in result.dates])).ffill()
    b = stats_on(result.dates, list(q.values))
    checks = {
        "cagr": s.cagr_pct > b.cagr_pct,
        "sharpe": s.sharpe > b.sharpe,
        "dd": s.max_drawdown_pct <= MAX_DD_RATIO * b.max_drawdown_pct,
    }
    return {
        "strategy": s.model_dump(),
        "QQQ": b.model_dump(),
        "checks": checks,
        "passes": all(checks.values()),
        "rebalances": result.rebalances,
        "weeks_in_cash": result.weeks_in_cash,
        "turnover": result.turnover,
    }


def main() -> None:
    ingest = "--skip-ingest" not in sys.argv
    pool = build_pool()
    symbols = sorted(pool.all_symbols() | {"QQQ", "SPY"})
    print(
        f"pool: {len(symbols)} symbols ever eligible; {len(pool._dates)} snapshots "
        f"{pool._dates[0]} → {pool._dates[-1]}",
        flush=True,
    )
    opens, closes, missing = load_prices(symbols, ingest)
    print(
        f"prices: {closes.shape[1]} symbols loaded; {len(missing)} unfetchable "
        f"(survivorship gaps): {missing}",
        flush=True,
    )

    report: dict = {
        "generated_at": datetime.now().isoformat(),
        "pre_registration": "docs/STRATEGY_SEARCH_2026-10.md",
        "survivorship_gaps": missing,
        "design": {},
        "selected": None,
        "holdout": None,
        "verdict": None,
    }

    print("\n== DESIGN window", DESIGN, "==")
    for cfg in VARIANTS:
        r = run_rotation(cfg, pool, opens, closes, *DESIGN)
        ev = evaluate(r, closes)
        report["design"][cfg.name] = ev
        s, q = ev["strategy"], ev["QQQ"]
        print(
            f"  {cfg.name:8} CAGR {s['cagr_pct']:+6.1f}% Sharpe {s['sharpe']:.2f} "
            f"DD {s['max_drawdown_pct']:5.1f}% | QQQ {q['cagr_pct']:+6.1f}% {q['sharpe']:.2f} "
            f"{q['max_drawdown_pct']:5.1f}% | checks {ev['checks']} → "
            f"{'PASS' if ev['passes'] else 'fail'}",
            flush=True,
        )

    passing = [n for n, ev in report["design"].items() if ev["passes"]]
    if not passing:
        report["verdict"] = "REJECTED (no variant passes the design window)"
    else:
        best = max(passing, key=lambda n: report["design"][n]["strategy"]["sharpe"])
        report["selected"] = best
        cfg = next(c for c in VARIANTS if c.name == best)
        print(f"\nselected on design window: {best}\n== HOLDOUT (single run)", HOLDOUT, "==")
        r = run_rotation(cfg, pool, opens, closes, *HOLDOUT)
        hold = evaluate(r, closes)
        top2 = [k for k, v in sorted(r.per_symbol_pnl.items(), key=lambda kv: -kv[1])[:2] if v > 0]
        ex = run_rotation(cfg, pool, opens, closes, *HOLDOUT, exclude=frozenset(top2))
        ex_ev = evaluate(ex, closes)
        hold["ex_top2"] = {
            "excluded": top2,
            "cagr_pct": ex_ev["strategy"]["cagr_pct"],
            "beats_qqq_cagr": ex_ev["strategy"]["cagr_pct"] > hold["QQQ"]["cagr_pct"],
        }
        report["holdout"] = hold
        ok = hold["passes"] and hold["ex_top2"]["beats_qqq_cagr"]
        report["verdict"] = "ADOPTED FOR PAPER" if ok else "REJECTED (holdout)"
        s, q = hold["strategy"], hold["QQQ"]
        print(
            f"  {best:8} CAGR {s['cagr_pct']:+6.1f}% Sharpe {s['sharpe']:.2f} "
            f"DD {s['max_drawdown_pct']:5.1f}% | QQQ {q['cagr_pct']:+6.1f}% {q['sharpe']:.2f} "
            f"{q['max_drawdown_pct']:5.1f}% | checks {hold['checks']}"
        )
        print(
            f"  ex-top-2 {top2}: CAGR {ex_ev['strategy']['cagr_pct']:+.1f}% "
            f"(beats QQQ: {hold['ex_top2']['beats_qqq_cagr']})"
        )

    full_cfg = next((c for c in VARIANTS if c.name == report["selected"]), VARIANTS[2])
    full = run_rotation(full_cfg, pool, opens, closes, DESIGN[0], HOLDOUT[1])
    report["context_full_period"] = {"variant": full_cfg.name, **evaluate(full, closes)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nVERDICT: {report['verdict']}\nreport: {OUT}")


if __name__ == "__main__":
    main()
