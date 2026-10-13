"""2026-10-13 profitability review: monthly cross-sectional momentum, ONE-SHOT.

Usage: python scripts/experiments/2026-10-13_momentum_rotation.py data/hindsight_free/mega.duckdb [EXCLUDE ...]
Result: all 29 names CAGR +33.2% vs QQQ +21.1% (10y); excluding NVDA,TSLA +22.0%;
excluding NVDA,TSLA,AVGO,NFLX +13.0% -> the edge is concentration in a few mega-winners.
"""
# ONE-SHOT, parameters fixed before running (textbook, not tuned): universe = mid-2016 NASDAQ-100 top-29
# (hindsight-free), signal = 12-1 month return, hold top 5 equal-weight, monthly rebalance on prior close,
# 10 bps cost per unit turnover.
import numpy as np, duckdb, sys
from datetime import date
c = duckdb.connect(sys.argv[1], read_only=True)
rows = c.execute("select symbol, cast(timestamp as date), close from bars where timeframe='1d' order by 2").fetchall()
px = {}
for s, d, v in rows: px.setdefault(s, {})[d] = v
dates = [d for d in sorted(px["SPY"]) if d >= date(2015, 1, 2)]
MEGA = [s for s in px if s not in ("SPY", "QQQ", *sys.argv[2:])]
spy = np.array([px["SPY"][d] for d in dates]); sma200 = np.array([spy[max(0, i-199):i+1].mean() for i in range(len(spy))])
def run(gate):
    eq = [1.0]; hold = []; ods = []
    for i in range(1, len(dates)):
        d0, d1 = dates[i-1], dates[i]
        if d1 < date(2016, 6, 1): continue
        if not ods or d1.month != ods[-1].month:
            j = i - 1
            k12 = max(k for k in range(j) if (dates[j]-dates[k]).days >= 365)
            k1 = max(k for k in range(j) if (dates[j]-dates[k]).days >= 21)
            score = {s: px[s][dates[k1]]/px[s][dates[k12]]-1 for s in MEGA if dates[k12] in px[s] and dates[k1] in px[s]}
            new = sorted(score, key=score.get, reverse=True)[:5]
            if gate and spy[j] <= sma200[j]: new = []
            eq[-1] *= 1 - 0.001 * len(set(new) ^ set(hold)) / 5; hold = new
        r = np.mean([px[s][d1]/px[s][d0]-1 for s in hold if d0 in px[s] and d1 in px[s]]) if hold else 0.0
        eq.append(eq[-1]*(1+r)); ods.append(d1)
    return np.array(eq[1:]), ods
def st(v, ds, start):
    i0 = next(i for i, d in enumerate(ds) if d >= start); v = v[i0:]; ds = ds[i0:]
    r = np.diff(v)/v[:-1]; yrs = (ds[-1]-ds[0]).days/365.25
    return f"CAGR {(v[-1]/v[0])**(1/yrs)-1:+6.1%} Shrp {r.mean()/r.std()*252**.5:4.2f} DD {(1-v/np.maximum.accumulate(v)).max():5.1%}"
for gate in (False, True):
    v, ds = run(gate); q = np.array([px["QQQ"][d] for d in ds]); s = np.array([px["SPY"][d] for d in ds])
    for lab, s0 in (("10y", date(2016, 6, 1)), ("2022+", date(2022, 1, 3)), ("live", date(2026, 7, 15))):
        print(f"momentum top-5{' +SMA200' if gate else '        '} {lab:5}: {st(v, ds, s0)} | QQQ {st(q, ds, s0)} | SPY {st(s, ds, s0)}")
