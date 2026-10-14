"""Pre-registered trend-timed QQQ leverage search (docs/STRATEGY_SEARCH_2026-10b_TREND_LEVERAGE.md).

    python scripts/experiments/2026-10-14b_trend_leverage_search.py --prepare   # data only
    python scripts/experiments/2026-10-14b_trend_leverage_search.py --run       # ONE-SHOT

--run refuses if its report exists, writes a "started" sentinel before computing, and
records git SHA / dirty flag / data fingerprint. If no variant passes the design window
(at SMA 200 AND 150 AND 250), the holdout is never run.
"""

import hashlib
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from bonito.data.store import MarketDataStore
from bonito.research.allocation import VARIANTS, run_allocation, trend_decider
from bonito.research.benchmark_eval import MAX_DD_RATIO, curve_stats

SYMBOLS = ["QQQ", "QLD", "TQQQ"]
DESIGN = (date(2016, 1, 4), date(2021, 12, 31))
HOLDOUT = (date(2022, 1, 3), date(2026, 10, 13))
SMA_MAIN, SMA_ROBUST = 200, (150, 250)
DB = Path("data/research/trend_leverage.duckdb")
OUT = Path("livetrade/research/strategy_search_2026-10b_trend_leverage.json")


def load(ingest: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    DB.parent.mkdir(parents=True, exist_ok=True)
    store = MarketDataStore(db_path=DB)
    opens, closes = {}, {}
    for s in SYMBOLS:
        if ingest:
            store.ingest_from_yahoo(s, datetime(2014, 6, 1), datetime(2026, 10, 15), "1d")
        b = store.get_bars(s, datetime(2014, 6, 1), datetime(2026, 10, 15), "1d")
        if b is None or len(b) == 0:
            sys.exit(f"no prices for {s}")
        idx = pd.DatetimeIndex([pd.Timestamp(t.date()) for t in b.timestamps])
        opens[s] = pd.Series(b.opens, index=idx)
        closes[s] = pd.Series(b.closes, index=idx)
    o, c = pd.DataFrame(opens).sort_index(), pd.DataFrame(closes).sort_index()
    return o[~o.index.duplicated()], c[~c.index.duplicated()]


def evaluate(r, closes: pd.DataFrame) -> dict:
    s = curve_stats(r.dates, r.equity)
    q = closes["QQQ"].reindex(pd.DatetimeIndex([pd.Timestamp(d) for d in r.dates])).ffill()
    b = curve_stats(r.dates, list(q.values))
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
        "rebalances": r.rebalances,
        "turnover": r.turnover,
    }


def run(variant: str, sma: int, window, opens, closes):
    return run_allocation(variant, trend_decider(closes, variant, sma), opens, closes, *window)


def fmt(name: str, ev: dict) -> str:
    s, q = ev["strategy"], ev["QQQ"]
    return (
        f"  {name:16} CAGR {s['cagr_pct']:+6.1f}% Sharpe {s['sharpe']:.2f} "
        f"DD {s['max_drawdown_pct']:5.1f}% | QQQ {q['cagr_pct']:+6.1f}% {q['sharpe']:.2f} "
        f"{q['max_drawdown_pct']:5.1f}% | {ev['checks']} → {'PASS' if ev['passes'] else 'fail'}"
    )


def main() -> None:
    mode = "--run" if "--run" in sys.argv else "--prepare" if "--prepare" in sys.argv else None
    if mode is None:
        sys.exit("usage: --prepare | --run")
    if mode == "--run" and OUT.exists():
        sys.exit(f"{OUT} exists — the pre-registered test is ONE-SHOT. Not re-running.")
    opens, closes = load(ingest=(mode == "--prepare"))
    span = {
        s: [str(closes[s].first_valid_index().date()), str(closes[s].last_valid_index().date())]
        for s in SYMBOLS
    }
    print(f"price spans: {span}; sessions {len(closes['QQQ'].dropna())}")
    for s in SYMBOLS:
        need = pd.Timestamp(DESIGN[0]) - pd.Timedelta(days=400)
        if closes[s].first_valid_index() > need:
            sys.exit(
                f"{s} history starts too late for SMA{max(SMA_ROBUST)} before the design window"
            )
    if mode == "--prepare":
        print("data OK. No strategy was run.")
        return

    OUT.write_text(json.dumps({"status": "started", "at": datetime.now().isoformat()}))
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
    fp = hashlib.sha256(pd.util.hash_pandas_object(closes.fillna(-1)).values.tobytes()).hexdigest()
    report: dict = {
        "generated_at": datetime.now().isoformat(),
        "pre_registration": "docs/STRATEGY_SEARCH_2026-10b_TREND_LEVERAGE.md",
        "provenance": {
            "git_sha": sha.strip(),
            "dirty_tree": bool(dirty.strip()),
            "dirty_paths": dirty.split(),
            "data_fingerprint": fp,
        },
        "price_spans": span,
        "design": {},
        "selected": None,
        "holdout": None,
    }
    print("\n== DESIGN window", DESIGN, "==")
    for v in VARIANTS:
        evs = {
            sma: evaluate(run(v, sma, DESIGN, opens, closes), closes)
            for sma in (SMA_MAIN, *SMA_ROBUST)
        }
        passes = all(e["passes"] for e in evs.values())
        report["design"][v] = {"by_sma": evs, "passes": passes}
        for sma, e in evs.items():
            print(fmt(f"{v} SMA{sma}", e))
        print(f"  → {v}: {'PASS (all three SMAs)' if passes else 'fail'}", flush=True)

    passing = [v for v, d in report["design"].items() if d["passes"]]
    if not passing:
        report["verdict"] = "REJECTED (no variant passes the design window; holdout not run)"
    else:
        best = max(
            passing, key=lambda v: report["design"][v]["by_sma"][SMA_MAIN]["strategy"]["sharpe"]
        )
        report["selected"] = best
        print(f"\nselected: {best}\n== HOLDOUT (single run)", HOLDOUT, "==")
        hold = evaluate(run(best, SMA_MAIN, HOLDOUT, opens, closes), closes)
        report["holdout"] = hold
        report["verdict"] = "ADOPTED FOR PAPER" if hold["passes"] else "REJECTED (holdout)"
        print(fmt(f"{best} SMA{SMA_MAIN}", hold))
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nVERDICT: {report['verdict']}\nreport: {OUT}")


if __name__ == "__main__":
    main()
