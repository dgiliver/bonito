"""Pre-registered strategy search (docs/STRATEGY_SEARCH_2026-10.md), run exactly as registered.

Two phases, deliberately separate:

    python scripts/experiments/2026-10-14_momentum_rotation_search.py --prepare
        Ingest prices and run the DATA checks only: membership integrity and price
        coverage of every pool symbol over its membership span. No strategy run.
        Use it to fix ticker mapping against data before the one-shot run.

    python scripts/experiments/2026-10-14_momentum_rotation_search.py --run
        The ONE-SHOT test. Refuses if the report already exists (no silent re-runs),
        records git SHA / dirty flag / data fingerprint.
        1. Four fixed variants on the DESIGN window; select the highest-Sharpe variant
           among those passing the criterion vs QQQ there. None pass → REJECTED and the
           holdout is never run (not even as "context").
        2. Selected variant: ONE holdout run + an ex-top-2 rerun.

Data-cleaning rules (amended before any strategy result, after the pre-run review):
- RENAMES: ONLY ticker changes of the SAME legal entity, so a symbol is never scored
  on another company's prices. (VIAB→PARA and MYL→VTRS were removed: Yahoo's PARA
  history before 2019-12 is CBS, and VTRS starts at the 2020 Viatris merger.)
- SECONDARY_CLASSES: one share class per company (keep GOOGL, drop GOOG, ...).
- Unfetchable members are survivorship gaps; they bias results IN FAVOUR of the
  strategy and are reported with per-year coverage.
"""

import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from bonito.data.store import MarketDataStore
from bonito.research.benchmark_eval import MAX_DD_RATIO, curve_stats
from bonito.research.rotation import (
    PointInTimePool,
    RotationConfig,
    RotationResult,
    run_rotation,
)

RENAMES = {
    "FB": "META",
    "PCLN": "BKNG",
    "CTRP": "TCOM",
    "FISV": "FI",
    "SYMC": "GEN",
    "NLOK": "GEN",
    "DISCA": "WBD",
    "QVCA": "QRTEA",
    "WLTW": "WTW",
    "BRK.B": "BRK-B",
}
SECONDARY_CLASSES = {
    "GOOG", "FOX", "LBTYK", "LBTYB", "LILAK", "DISCK", "DISCB", "LMCK", "NWS", "QVCB",
    "LBRDK", "FWONK", "BATRK",
}  # fmt: skip

DESIGN = (date(2016, 1, 4), date(2021, 12, 31))
HOLDOUT = (date(2022, 1, 3), date(2026, 10, 13))
VARIANTS = [
    RotationConfig(name="M6-T5", lookback_months=6, top_n=5),
    RotationConfig(name="M6-T10", lookback_months=6, top_n=10),
    RotationConfig(name="M12-T5", lookback_months=12, top_n=5),
    RotationConfig(name="M12-T10", lookback_months=12, top_n=10),
]
MEMBERSHIP = Path("data/reference/ndx_membership.json")
ADDITIONS = Path("data/reference/universe_additions.json")
DB = Path("data/research/rotation.duckdb")
OUT = Path("livetrade/research/strategy_search_2026-10.json")
COVERAGE_OUT = Path("livetrade/research/strategy_search_2026-10_coverage.json")
MEMBER_COUNT_BOUNDS = (95, 115)  # NASDAQ-100 has ~100-108 securities


def check_membership() -> list[str]:
    """Integrity: one snapshot per quarter with no holes, plausible member counts."""
    snaps = json.loads(MEMBERSHIP.read_text())["snapshots"]
    problems = []
    dates = sorted(date.fromisoformat(d) for d in snaps)
    quarters, q = [], dates[0]
    while q <= dates[-1]:
        quarters.append(q)
        q = date(q.year + (q.month == 10), (q.month % 12) + 3 if q.month != 10 else 1, 1)
    for q in quarters:
        if q.isoformat() not in snaps:
            problems.append(f"missing quarter {q}")
    lo, hi = MEMBER_COUNT_BOUNDS
    for d, v in snaps.items():
        if not lo <= len(v["tickers"]) <= hi:
            problems.append(f"{d}: {len(v['tickers'])} tickers outside {MEMBER_COUNT_BOUNDS}")
    return problems


def build_pool() -> PointInTimePool:
    pool = PointInTimePool.from_files(MEMBERSHIP, ADDITIONS, renames=RENAMES)
    pool.drop_symbols(SECONDARY_CLASSES)
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


def coverage_report(pool: PointInTimePool, closes: pd.DataFrame) -> dict:
    """Per-snapshot share of members with a price, and per-symbol span gaps."""
    by_snapshot = {}
    for d, members in zip(pool._dates, pool._sets, strict=True):
        if d < DESIGN[0] - timedelta(days=400):
            continue
        ts = pd.Timestamp(d)
        window = closes.loc[ts - pd.Timedelta(days=7) : ts + pd.Timedelta(days=7)]
        priced = [s for s in members if s in window.columns and window[s].notna().any()]
        by_snapshot[d.isoformat()] = {
            "members": len(members),
            "priced": len(priced),
            "unpriced": sorted(set(members) - set(priced)),
        }
    spans = {}
    for s in pool.all_symbols():
        in_snaps = [d for d, m in zip(pool._dates, pool._sets, strict=True) if s in m]
        if not in_snaps or s not in closes.columns:
            continue
        col = closes[s].dropna()
        first_member, last_member = in_snaps[0], in_snaps[-1]
        late_start = col.index[0].date() > max(first_member, DESIGN[0]) + timedelta(days=45)
        early_end = col.index[-1].date() < last_member - timedelta(days=45)
        if late_start or early_end:
            spans[s] = {
                "member": [first_member.isoformat(), last_member.isoformat()],
                "prices": [col.index[0].date().isoformat(), col.index[-1].date().isoformat()],
            }
    return {"by_snapshot": by_snapshot, "span_gaps": spans}


def evaluate(result: RotationResult, closes: pd.DataFrame) -> dict:
    s = curve_stats(result.dates, result.equity)
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in result.dates])
    q = closes["QQQ"].reindex(idx).ffill()
    b = curve_stats(result.dates, list(q.values))
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


def provenance(closes: pd.DataFrame) -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    dirty = bool(
        subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
    )
    fp = hashlib.sha256(MEMBERSHIP.read_bytes() + ADDITIONS.read_bytes())
    fp.update(pd.util.hash_pandas_object(closes.fillna(-1), index=True).values.tobytes())
    return {"git_sha": sha.strip(), "dirty_tree": dirty, "data_fingerprint": fp.hexdigest()}


def line(name: str, ev: dict) -> str:
    s, q = ev["strategy"], ev["QQQ"]
    return (
        f"  {name:8} CAGR {s['cagr_pct']:+6.1f}% Sharpe {s['sharpe']:.2f} "
        f"DD {s['max_drawdown_pct']:5.1f}% | QQQ {q['cagr_pct']:+6.1f}% {q['sharpe']:.2f} "
        f"{q['max_drawdown_pct']:5.1f}% | {ev['checks']} → {'PASS' if ev['passes'] else 'fail'}"
    )


def main() -> None:
    mode = "--run" if "--run" in sys.argv else "--prepare" if "--prepare" in sys.argv else None
    if mode is None:
        sys.exit("usage: --prepare | --run   (see module docstring)")
    problems = check_membership()
    if problems:
        sys.exit("membership integrity FAILED:\n  " + "\n  ".join(problems))

    pool = build_pool()
    symbols = sorted(pool.all_symbols() | {"QQQ", "SPY"})
    print(f"pool: {len(symbols)} symbols ever eligible; {len(pool._dates)} snapshots", flush=True)
    opens, closes, missing = load_prices(symbols, ingest=(mode == "--prepare"))
    cov = coverage_report(pool, closes)
    cov["unfetchable"] = missing
    COVERAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_OUT.write_text(json.dumps(cov, indent=1))
    worst = min(cov["by_snapshot"].items(), key=lambda kv: kv[1]["priced"] / kv[1]["members"])
    print(f"unfetchable ({len(missing)}): {missing}")
    print(f"lowest snapshot coverage: {worst[0]} {worst[1]['priced']}/{worst[1]['members']}")
    print(f"span gaps ({len(cov['span_gaps'])}): {sorted(cov['span_gaps'])}")
    if mode == "--prepare":
        print(f"coverage written to {COVERAGE_OUT}. No strategy was run.")
        return

    if OUT.exists():
        sys.exit(f"{OUT} exists — the pre-registered test is ONE-SHOT. Not re-running.")
    report: dict = {
        "generated_at": datetime.now().isoformat(),
        "pre_registration": "docs/STRATEGY_SEARCH_2026-10.md",
        "provenance": provenance(closes),
        "coverage_file": str(COVERAGE_OUT),
        "design": {},
        "selected": None,
        "holdout": None,
        "verdict": None,
    }
    print("\n== DESIGN window", DESIGN, "==")
    for cfg in VARIANTS:
        ev = evaluate(run_rotation(cfg, pool, opens, closes, *DESIGN), closes)
        report["design"][cfg.name] = ev
        print(line(cfg.name, ev), flush=True)

    passing = [n for n, ev in report["design"].items() if ev["passes"]]
    if not passing:
        report["verdict"] = "REJECTED (no variant passes the design window; holdout not run)"
    else:
        best = max(passing, key=lambda n: report["design"][n]["strategy"]["sharpe"])
        report["selected"] = best
        cfg = next(c for c in VARIANTS if c.name == best)
        print(f"\nselected on design window: {best}\n== HOLDOUT (single run)", HOLDOUT, "==")
        r = run_rotation(cfg, pool, opens, closes, *HOLDOUT)
        hold = evaluate(r, closes)
        ranked = sorted(r.per_symbol_pnl.items(), key=lambda kv: -kv[1])
        top2 = [k for k, v in ranked[:2] if v > 0]
        ex = evaluate(
            run_rotation(cfg, pool, opens, closes, *HOLDOUT, exclude=frozenset(top2)), closes
        )
        adds = set(json.loads(ADDITIONS.read_text())["additions"])
        hold["ex_top2"] = {
            "excluded": top2,
            "cagr_pct": ex["strategy"]["cagr_pct"],
            "beats_qqq_cagr": ex["strategy"]["cagr_pct"] > hold["QQQ"]["cagr_pct"],
        }
        hold["pnl_from_45_name_additions"] = round(
            sum(v for k, v in r.per_symbol_pnl.items() if k in adds), 2
        )
        hold["total_pnl"] = round(sum(r.per_symbol_pnl.values()), 2)
        report["holdout"] = hold
        ok = hold["passes"] and hold["ex_top2"]["beats_qqq_cagr"]
        report["verdict"] = "ADOPTED FOR PAPER" if ok else "REJECTED (holdout)"
        print(line(best, hold))
        print(
            f"  ex-top-2 {top2}: CAGR {ex['strategy']['cagr_pct']:+.1f}% "
            f"(beats QQQ: {hold['ex_top2']['beats_qqq_cagr']})"
        )
        print(
            f"  P&L from the 45 hand-picked additions: {hold['pnl_from_45_name_additions']} "
            f"of {hold['total_pnl']}"
        )
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nVERDICT: {report['verdict']}\nreport: {OUT}")


if __name__ == "__main__":
    main()
