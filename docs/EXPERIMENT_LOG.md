# Experiment Log — live pipeline optimization

Canonical record of account-level experiments. **Check this before proposing
an optimization** — rejected ideas come back looking clever every time the
attribution tables are re-read.

## Protocol

Every candidate change is judged by `bonito live backtest-account` (the
replay of the real pipeline code), never by raw P&L attribution.

**The routine version of this protocol is automated**: the weekly
`Weekly strategy research` workflow runs `bonito research auto --apply`
(`src/bonito/research/auto_research.py`) — rolling-holdout per-symbol
sweep, stateless symbol_strategies rebuild, and an account-replay gate
that adopts a bundle only if neither train nor holdout degrades. Rejected
or adopted cycles open a visibility issue; every cycle commits a digest
to `livetrade/research/auto_research_*.json`. Manual experiments (new
ideas, structural changes) still follow the steps below by hand:

1. **Pre-register the criterion before running**: adopt only if the TRAIN
   window improves AND the holdout does not degrade.
2. One shot per idea — no variant shopping after seeing results. A sign
   flip ("momentum failed, try inverse momentum!") is a new idea that needs
   its own independent justification, not a free retry.
3. Structural changes (capital allocation, diversification) are held to the
   same bar but are more trustworthy when the improvement is monotone
   across a parameter family (e.g. 5→6→7→8 slots).
4. Compare against the last saved result in `livetrade/research/`.

## Adopted

| Date | Change | Evidence |
|------|--------|----------|
| 2026-06-12 | `position_pct_equity` sizing (slots scale with equity instead of fixed $1k) | Fixed slots left 61% of equity idle by 2026; +156%→+196% with nothing else changed |
| 2026-06-12 | 8 slots × 12.5% equity, $2.5k/position cap (was 5 × 20%, $1k cap) | $14,823→$26,024 (+420.5%), Sharpe 1.36→1.55, max DD 21.6%. Monotone gain 5→6→7→8; train +83.4% AND holdout +181.5% both improve. 8 slots chosen over 7 for DD headroom (21.6% vs 23.7% against the 25% kill switch) at equal Sharpe |
| 2026-06-12 | Drop NVDA from the universe | Per-symbol research: all 144 grid candidates lose money in 2025–26 holdout (-19% to -40%); live attribution -$333 over 37 trades, 27 stop-outs |
| 2026-06-12 | IREN per-symbol strategy `iren_ema8-21_rsi68_atr1.5_tpnone` | Holdout Sharpe 2.98, +1269%, DD 24% OOS. **Caveat**: bypassed the train DD gate (57% in 2022-24) — justified only because a capped slot limits account exposure to ~12.5% |
| 2026-06-12 | AAPL/GOOGL per-symbol assignments via `research clusters --per-symbol` | Both passed holdout kill filter + profitable-holdout gate; account replay confirmed (AAPL -$254→-$36, GOOGL -$32→+$109) |
| 2026-07-17 | Re-add NVDA to the paper universe (symbols list), immediately blocklisted from new entries via `entry_blocklist` | Sourced from Renaissance Technologies' Q1 2026 13F, alongside DASH/MSTR/UNH/RBLX (those 4 have no prior history in this log). NVDA specifically was already dropped 2026-06-12 for cause (see row above) under the same default strategy family this re-add would otherwise use — no new evidence that situation has changed, so re-entering it blind isn't justified. `entry_blocklist` lets it accrue fresh data and get automatically re-evaluated by the weekly `bonito research auto` cron's EMA-cross grid (450 candidates on wider axes than the original 144, but the same structural family that already failed it — `research_auto()` passes no `grid=` override, so it stays on `GridSpec()`'s EMA-only default; ADX/MACD/BBands templates exist but are opt-in only via the manual `bonito research clusters --templates`, never part of the automatic weekly cycle) without opening new positions until a candidate actually passes. Self-unbenches via `auto_research.py` the same way any other blocklisted symbol does if it heals. Paper only — `config/universe.live.json` untouched. Caught by `pr-reviewer` before merge (PR #19) — round 1 caught the missing blocklist, round 2 caught this entry's own wrong claim about which grid re-evaluates NVDA, an instance of exactly the prose-vs-code mismatch this log exists to prevent. |
| 2026-07-18 | Mirror the same 5-symbol addition (DASH/MSTR/UNH/RBLX/NVDA + NVDA's `entry_blocklist`) into `config/universe.live.json` | Explicit user authorization for live, given after the agent raised the same two concerns as the paper addition (13F-holdings-vs-strategy-fit mismatch; universe-order slot-competition risk) plus a live-specific one (doing this while the account had an unresolved missing-stop-loss incident) — user heard all three and reaffirmed the decision regardless. `mode`/`live_enabled`/all `risk` fields confirmed byte-identical before and after by `pr-reviewer` (PR #21) — this changes only `symbols` and `entry_blocklist`, nothing else. Same structural addition as the paper version, verified identical by direct comparison, not re-derived from scratch. |

## Rejected

| Date | Idea | Why it looked good | Why it failed |
|------|------|--------------------|----------------|
| 2026-06-12 | Remove the EMA cross-below exit rule | Exit arm shows -$1,684 raw P&L over 34 trades | Account replay DEGRADES without it (+191.9% vs +196.5%). Attribution misses opportunity cost: those exits free capital for better re-entries |
| 2026-06-12 | Momentum-ranked entry competition (21-day momentum decides who gets slots instead of universe list order) | Train improved +83.4%→+121.8% | Holdout collapsed to **-20.1%** and the 25% kill switch fired (DD 26.3%). Ranking by momentum buys the most extended signals and concentrates into correlated high-beta names. Classic overfit: better in-sample, fatal out-of-sample |
| 2026-06-12 | Per-symbol grid winner for MSFT | Passed the kill filter on holdout | Holdout return was **-10.1%** — the kill filter checks structure (trades/DD/Sharpe ceiling), not profitability. Led to the profitable-holdout gate now in `cluster_research.py` |
| 2026-06-28 | Remove the SPY-200 regime gate from the deployed strategy | A regime-free entry rule trades far more and "buys the dip" in any tape | At the account level it is fatal. Intraday-stops ON: gated +485.3% (Sharpe 1.63, DD 21.6%, no halt); ungated trips the 25% kill switch 2022-12-22 (DD 25.8%, equity $4,027 vs peak $5,428), halts, ends −19.5% with 0% holdout (dead capital). Independent no-intraday-stops confirmatory pair reproduces the kill (ungated halts 2022-10-14, DD 26.3%; gated +500%/1.60, no halt). Pre-registered: RETAIN if Sharpe(ON)≥Sharpe(OFF) on train+holdout OR a DD/give-up leg; kill-switch override checked first and dominates. RETAIN rests on the kill-switch override plus the confirmatory pair — NOT three orthogonal signals (the Sharpe and DD legs are downstream of the same halt). Validator PASS. (Reproducer: scratchpad/q1/.) |
| 2026-06-28 | Strip the per-symbol cluster overrides (AAPL/GOOGL/IREN → all default) | ~30 of 33 symbols already run the default; one override (GOOGL) attributes slightly negative (−$52) | Account replay says KEEP. Pre-registered criterion (Sharpe(ON)≥Sharpe(OFF) on BOTH train AND holdout) passes: train 1.04 vs 0.93, holdout 2.50 vs 2.33; full +485.3% vs +409.2%; neither halts. Per-symbol attribution: IREN +$1,928 vs +$384 (+$1,544), AAPL +$7 vs −$226 (+$234, protective), GOOGL +$196 vs +$248 (−$52, the one weak link). Q4 examined GOOGL specifically (pre-registered: status-quo vs default vs entry_blocklist) — INCONCLUSIVE → kept GOOGL→cluster_GOOGL (status quo). Neither alt arm cleared the 0.05-Sharpe noise floor on BOTH windows simultaneously: default improved holdout (+0.12) but degraded train (−0.09); entry_blocklist improved train (+0.05) but was flat-to-negative on holdout (−0.003); no halts in any arm. GOOGL's −$52 is noise, not signal. (Reproducer: scratchpad/q3/, scratchpad/q4/.) |

## Bugs found & risk findings

| Date | Bug | Impact | Fix |
|------|-----|--------|-----|
| 2026-06-18 | `ema()` seeded its recursive computation from `np.mean(prices[:period])`, assuming index 0 is always valid | MACD's `signal_line` (an `ema()` of `macd_line`, which itself starts with `slow_period-1` NaNs) seeded on NaN and propagated NaN forever — `signal_line`/`histogram` were 100% NaN for every strategy that has ever used a MACD crossover rule. `crosses_above`/`crosses_below` against an all-NaN series never fires, so the rule was silently inert, not erroring. `macd_line` itself was unaffected (built from two raw-price EMAs valid at index 0) | Seed from the first window of *valid* (non-NaN) values instead of index 0 (`d1b75e2`). `rsi()`/`atr()` had the same class of bug — `atr()` failed visibly (100% NaN output), `rsi()` failed silently (`np.where(deltas > 0, deltas, 0)` evaluated NaN comparisons as `False`, silently zeroing leading NaN deltas instead of propagating them, corrupting the rolling average with wrong non-NaN numbers). Both given the same first-valid-window seeding; `rsi()` additionally NaN-guarded its gain/loss split |
| 2026-06-18 | `bonito backtest` never fetched or passed `regime_data` | Any strategy with a `regime_filter` crashed inside the engine — including `strategies/deployed_strategy.json`, the actual live/paper strategy | Fetch the regime symbol's bars (with the same `REGIME_WARMUP_DAYS` padding `live_runner.py` already uses) before `engine.run()` (`f77d428`) |
| 2026-06-19 | `research/autoresearch_trading.py` carried its own kill filter with an absolute `MIN_TRADES = 30`, duplicating but diverging from `trading/validation.py::kill_verdict()`'s rate-based `MIN_TRADES_PER_YEAR = 7.0` | The two filters could disagree on the same strategy/window — an absolute count conflates short and long backtest windows where a rate doesn't. `cluster_research.py` and `regime_sweep.py` (the paths that actually gate live promotion) already called the canonical `kill_verdict()`; only the standalone `autoresearch_trading.py` loop was evaluating candidates against the divergent, non-canonical threshold | Deleted the local `MIN_TRADES`/`MAX_DRAWDOWN`/`MAX_SHARPE` constants and duplicated filter logic; `apply_kill_filters()` now builds a `WindowMetrics` via `window_metrics()` and delegates to `kill_verdict()`, keeping only the autoresearch-specific indicator-count check local |
| 2026-07-18 | Broker-side GTC stop orders are rejected outright for this account | Every position is fractional by construction ($18-ish slots on a $150 account); Robinhood rejected all 3 real GTC stop attempts (PLTR/HOOD/ASML) with "Invalid time in force for fractional order." Confirmed via the routine's own step-8 verification logic (added earlier the same day) correctly catching and reporting the failure instead of silently claiming success — the fix that found this bug is the same fix that made it safe to find. Researched extensively (5 parallel web-research passes: official Robinhood docs, `robin_stocks` source/issues, Alpaca's own docs as a cross-broker comparison, Reddit/forums where reachable) before concluding this needs empirical testing, not more searching — evidence is genuinely mixed on whether GFD (not just GTC) is the actual boundary, and the order in question routed through Robinhood's official "Agentic Trading MCP," live only since ~May 2026, which has no public track record yet; all historical community knowledge (robin_stocks etc.) describes the older, unofficial, reverse-engineered API instead. Also could not test this directly myself: no working Robinhood order-tool access from this interactive session (isolated precisely — reads and non-trade writes work, all trade-tool attempts fail identically), and a subagent given the user's own explicit authorization verbatim twice still soundly declined to route around the same gate, reasoning correctly that a tool-category-level approval wall is a deliberate human-in-the-loop checkpoint, not a session-specific bug to work around | Switched step 8 to GFD instead of GTC — explicitly documented as an unconfirmed experiment, not a verified fix, pending real market-hours testing (Monday). Even if accepted, GFD does not restore full 24/7 protection: it expires at every session close and creates a real gap between market open and whenever that day's cycle runs, which GTC never had — corrected the "Intraday stops under a Routine" section's prior overstated "24/7, doesn't lapse" claim to say this plainly rather than leave it standing as fact. If continuous, gap-free protection matters enough to justify the cost, the "second Routine for intraday polling" option (discussed and deliberately deferred earlier the same day) is the real fix, not a TIF parameter |

## Grid changes

| Date | Change | Trigger |
|------|--------|---------|
| 2026-06-12 | Extended GridSpec 144 → 450 candidates: ema +(5,13), rsi +50/+55, atr +1.0/+1.25 | Grid-edge flags: every adopted winner sat at the ema/rsi/atr minimums. One-time human-approved extension; the gate judges the new region like any other candidate |

## Standing conclusions

- **Universe list order for entry competition is a tested decision** — do
  not "fix" it without new evidence (see momentum rejection above).
- **The exit rule stays** even though its raw P&L is negative.
- **Kill-filter PASS ≠ deployable**: assignments additionally require
  positive holdout return (enforced in code since 2026-06-12).
- **Silent NaN-handling bugs are a recurring risk class in indicator
  code** — `np.where` collapsing a NaN comparison to its default branch,
  or seeding a recursive computation at index 0 instead of the first valid
  value, doesn't crash; it just produces wrong numbers (or, worse, makes a
  rule silently never fire). And rate-based thresholds (trades/year) beat
  absolute ones (raw trade count) whenever the windows being compared
  vary in length.
- Full replay artifacts: `livetrade/research/account_backtest_*.json`;
  research reports: `livetrade/research/cluster_report_*.json`.
