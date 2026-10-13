"""2026-10-13 profitability review: run the DEPLOYED strategy on a hindsight-free universe.

Universe = ~29 largest NASDAQ-100 names as of mid-2016, fixed before any result was seen
(WBA/CELG-style later delistings can't be fetched — residual survivorship bias, which favours
the strategy, so the conclusion is conservative). Kill switch disabled to measure the strategy
itself. Compares against equal-weight hold of the same names, QQQ and SPY.

Usage:  python scripts/experiments/2026-10-13_hindsight_free_strategy.py ingest [DIR]
        python scripts/experiments/2026-10-13_hindsight_free_strategy.py <name> <stop> <tp> [DIR]
          stop: keep | none | <ATR multiple>;  tp: keep | none | <fraction>
Result (2016-06 -> 2026-10, baseline): strategy CAGR +10.4% vs hold-same +19.7%, QQQ +21.2%, SPY +15.3%.
"""
import sys, json, shutil, numpy as np, pathlib
from datetime import datetime
from bonito.data.store import MarketDataStore
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import ReplayStore, backtest_account
MEGA = ["AAPL","MSFT","AMZN","GOOGL","META","INTC","CMCSA","CSCO","AMGN","GILD","KHC","CHTR","QCOM","SBUX","COST",
        "PYPL","BKNG","TXN","AVGO","MDLZ","ADBE","NVDA","NFLX","TMUS","BIIB","ADP","REGN","EBAY","TSLA"]

if len(sys.argv) > 1 and sys.argv[1] == "ingest":
    import pathlib as _p
    from datetime import datetime as _dt
    from bonito.data.store import MarketDataStore as _M
    _dir = _p.Path(sys.argv[2]) if len(sys.argv) > 2 else _p.Path("data/hindsight_free"); _dir.mkdir(parents=True, exist_ok=True)
    _st = _M(db_path=_dir / "mega.duckdb")
    for _s in MEGA + ["SPY", "QQQ"]:
        try: print(_s, _st.ingest_from_yahoo(_s, _dt(2015, 1, 1), _dt(2026, 10, 14), "1d"))
        except Exception as _e: print(_s, "FAILED", _e)
    sys.exit(0)
name, stop, tp = sys.argv[1], sys.argv[2], sys.argv[3]  # e.g. base keep keep | nostop none keep | x 3.0 none
S = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else pathlib.Path("data/hindsight_free")
d = json.load(open("strategies/deployed_strategy.json"))
if stop != "keep": d["stop_loss"] = None if stop == "none" else {"type": "trailing_atr", "value": float(stop), "atr_period": 14}
if tp != "keep": d["take_profit"] = None if tp == "none" else {"type": "percent", "value": float(tp)}
sp = S / f"mega_{name}.json"; json.dump(d, open(sp, "w"))
u0 = UniverseConfig.load("config/universe.json")
u = u0.model_copy(update={"symbols": MEGA, "strategy_path": str(sp), "symbol_strategies": {}, "entry_blocklist": [], "entry_allowlist": None,
    "data": u0.data.model_copy(update={"start_date": "2015-01-01"}), "risk": u0.risk.model_copy(update={"max_drawdown_halt": 1.0})})
db = S / f"mega_{name}.duckdb"; shutil.copy(S / "mega.duckdb", db)
store = MarketDataStore(db_path=db); END = datetime(2026, 10, 12)
rp = ReplayStore.from_store(store, u, END)
px = {s: {t.date(): float(c) for t, c in zip(b.timestamps, b.closes)} for s in MEGA + ["QQQ", "SPY"] if (b := store.get_bars(s, datetime(2015,1,1), END, "1d")) is not None}
out = {"name": name}
for label, start in [("10y", datetime(2016, 6, 1)), ("2022+", datetime(2022, 1, 3)), ("live", datetime(2026, 7, 15))]:
    r = backtest_account(u, rp, start, END, intraday_stops=True)
    dates = [x.date() for x in r.equity_dates]; eq = np.asarray(r.equity_curve, float)
    def stt(v):
        v = np.asarray(v, float); rr = np.diff(v) / v[:-1]; yrs = (dates[-1] - dates[0]).days / 365.25
        return dict(ret=v[-1]/v[0]-1, cagr=(v[-1]/v[0])**(1/yrs)-1, sharpe=rr.mean()/rr.std()*252**.5, mdd=float((1-v/np.maximum.accumulate(v)).max()))
    ew = [1.0]
    for a, b_ in zip(dates[:-1], dates[1:]):
        rr = [px[s][b_]/px[s][a]-1 for s in MEGA if a in px[s] and b_ in px[s]]; ew.append(ew[-1]*(1+np.mean(rr)))
    out[label] = {"strategy": stt(eq), "EW": stt(ew), "QQQ": stt([px["QQQ"][x] for x in dates]), "SPY": stt([px["SPY"][x] for x in dates]),
                  "trades": len(r.trades), "win": r.win_rate, "inmkt": r.pct_days_in_market}
json.dump(out, open(S / f"mega_{name}.out.json", "w"), indent=1); print("done", name)
