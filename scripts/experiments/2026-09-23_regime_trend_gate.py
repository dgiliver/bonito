"""Pre-registered experiment: add a medium-term trend confirmation to the regime gate.

Scratch-only: monkeypatches `signals.regime_allows_long` for the candidate run.
No repository code is changed. If the candidate is ADOPTED, it gets built
properly (config field + engine parity + tests) through the normal pipeline.
"""

import sys
from datetime import datetime

import numpy as np

PRE_REGISTRATION = """
================ PRE-REGISTRATION (fixed before any result is computed) ================
Hypothesis : SPY > SMA200 separates bull from bear, but not trend from chop. Requiring
             SPY to ALSO be above its 50-day SMA should keep the EMA-cross momentum
             system flat through intermediate pullbacks, where breakouts fail most.
Baseline   : deployed strategies as-is (entry gate: SPY close > SMA200).
Candidate  : entry gate = SPY close > SMA200  AND  SPY close > SMA50.
             Strictly more restrictive: can only REMOVE entries. Exits/stops/TP never
             gated (unchanged). 50 = the conventional intermediate-trend lookback,
             chosen before seeing results -- NOT tuned. One shot: no 30/40/60 retries.
Harness    : canonical paper research config (config/universe.json, $5,000 start,
             45 symbols), intraday stops ON, one continuous replay per arm, windows
             from auto_research.rolling_windows(end=2026-09-18) -- the same windows
             weekly research uses. Holdout = last 540 days (includes the live window).
Criterion  : ADOPT iff ALL of:
             (a) auto_research.decide_adoption passes -- Sharpe does not degrade in
                 train OR holdout, and no new kill-filter failures in either window;
             (b) train Sharpe STRICTLY improves (EXPERIMENT_LOG protocol wording);
             (c) the candidate does not trip the 25% kill switch where the baseline
                 did not (2026-06-28 precedent: a halt dominates everything).
             Otherwise REJECT. Return/DD/trades are reported for context only.
=========================================================================================
"""


def main() -> int:
    print(PRE_REGISTRATION, flush=True)

    from bonito.data.store import MarketDataStore
    from bonito.research.auto_research import decide_adoption, rolling_windows
    from bonito.trading import signals
    from bonito.trading.live_runner import UniverseConfig
    from bonito.trading.portfolio_backtest import ReplayStore, backtest_account

    universe = UniverseConfig.load("config/universe.json")
    end = datetime(2026, 9, 18)
    start, holdout, end = rolling_windows(universe, end)
    print(
        f"windows: train {start:%Y-%m-%d} -> {holdout:%Y-%m-%d} | "
        f"holdout {holdout:%Y-%m-%d} -> {end:%Y-%m-%d}",
        flush=True,
    )

    replay = ReplayStore.from_store(MarketDataStore(), universe, end)
    print(f"replay symbols loaded: {len(replay.bars)}", flush=True)

    print("\n--- running BASELINE (SPY > SMA200) ---", flush=True)
    base = backtest_account(universe, replay, start, end, intraday_stops=True)

    original = signals.regime_allows_long

    def trend_confirmed(regime, regime_data):
        if not original(regime, regime_data):  # keeps the SMA200 check + fail-closed rules
            return False
        closes = np.asarray(regime_data.closes, dtype=float)
        if len(closes) < 50:
            return False
        return float(closes[-1]) > float(np.mean(closes[-50:]))

    signals.regime_allows_long = trend_confirmed
    try:
        print("--- running CANDIDATE (SPY > SMA200 AND > SMA50) ---", flush=True)
        cand = backtest_account(universe, replay, start, end, intraday_stops=True)
    finally:
        signals.regime_allows_long = original

    ok, reasons, comps = decide_adoption(base, cand, start, holdout, end)

    print("\n================================ RESULTS ================================")
    for arm, r in (("BASELINE ", base), ("CANDIDATE", cand)):
        print(
            f"{arm} full: return {r.total_return * 100:+8.1f}%  Sharpe {r.sharpe:5.2f}  "
            f"maxDD {r.max_drawdown * 100:5.1f}%  trades {len(r.trades):4d}  "
            f"win {r.win_rate * 100:4.1f}%  PF {r.profit_factor:4.2f}  "
            f"halted={r.halted}{' (' + r.halt_reason[:40] + ')' if r.halted else ''}"
        )
    print()
    for c in comps:
        print(
            f"{c.window:8} Sharpe {c.baseline_sharpe:6.3f} -> {c.candidate_sharpe:6.3f}   "
            f"return {c.baseline_return * 100:+7.1f}% -> {c.candidate_return * 100:+7.1f}%   "
            f"kill-failures base={c.baseline_failures} cand={c.candidate_failures}"
        )

    train = next(c for c in comps if c.window == "train")
    crit_a = ok
    crit_b = train.candidate_sharpe > train.baseline_sharpe
    crit_c = not (cand.halted and not base.halted)
    print("\n--- pre-registered criterion ---")
    print(f"(a) decide_adoption passes      : {crit_a}  {reasons if reasons else ''}")
    print(f"(b) train Sharpe strictly better: {crit_b}")
    print(f"(c) no new kill-switch halt     : {crit_c}")
    verdict = "ADOPT" if (crit_a and crit_b and crit_c) else "REJECT"
    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
