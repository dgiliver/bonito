# RFC: Live-vs-paper account-management fidelity

Status: **DRAFT — decisions open (§8)**
Author: orchestrator + 4-role pipeline (proposed)
Related: `docs/RFC_SETTLED_BAR_GUARD.md` (precedent), `tasks/todo.md` (pre-live gate),
`src/bonito/trading/{live_runner,paper,tracking}.py`

## 1. Summary (TL;DR)

Before `live_enabled` flips, real-money account management must behave like paper
and the backtest **with no silent divergence**. The good news: the architecture
already makes most of this true *by construction*, and the tooling to *measure*
it already exists. The risk is the handful of things that only happen with a real
broker and that nothing currently **forces** us to catch.

- **Backtest ≡ Paper** — structurally guaranteed (`backtest_account` replays the
  exact `generate_intents → execute_paper` code) and now determinism-tested
  (`tests/test_methodology_guards.py`). Solved.
- **Live ≡ Paper/Backtest** — *measurable today*: `bonito live tracking` is
  ledger-agnostic (`_load_ledger` keys off `universe.mode`, `cli.py:964`), so
  `bonito live tracking -u config/universe.live.json` runs the **live** ledger's
  real fills through the same fidelity engine (per-fill bps gap, decision
  divergence, equity gap; `tracking.py`). The engine is built; the *discipline
  and the live-only edge cases* are not.

This RFC adds: (a) **reconcile as a fail-closed gate**, (b) **fill-recording
fidelity** (actual filled qty, partial fills, rejections), (c) **live-calibrated
tracking thresholds**, (d) **real-price equity marking for the kill switch**, and
(e) a **small-size live rehearsal protocol** that becomes the go-live gate. No
strategy/intent logic changes; `live_enabled`/`mode`/risk caps stay human-only.

## 2. Problem — where live diverges, with exact touchpoints

The paper path *assumes a perfect broker*. Live does not. The divergence axes:

1. **Quantity drift (fractional fills / partial fills).** `execute_paper` sets
   `quantity = intent.dollar_amount / fill_price` (`paper.py:160`). A real
   Robinhood order fills a *broker-decided* fractional quantity (rounding, or a
   partial fill). The ledger then records a qty the broker didn't actually fill →
   every downstream mark, the kill-switch equity, and the next sizing decision
   are off until reconciled. `record-fill` today passes a price but the qty is
   still derived, not the broker's actual.
2. **Rejections / unfilled intents.** Paper *always* fills. Live orders can be
   rejected (buying power, fractional restriction, halted symbol, PDT) or simply
   not fill (limit away from market). Nothing logs "intent generated, order did
   not fill" — so tracking can't distinguish "we chose not to trade" from "we
   tried and couldn't," and the ledger may assume a position that doesn't exist.
3. **Position drift is detected but not gated.** `reconcile_positions`
   (`live_runner.py:704`) compares ledger vs broker, but it's a manual command
   that prints a report. Nothing makes the *next cycle* refuse to trade on drift,
   so an error compounds across cycles.
4. **Stale equity marks feed the kill switch.** The 25% halt computes
   `ledger.equity(prices)` (`live_runner.py:262`), and `equity()` falls back to
   `pos.entry_price` when a symbol is missing from `prices` (`paper.py:126`). On
   a real account the halt must mark off *current broker-confirmed* values, or it
   can fail to fire (or fire spuriously).
5. **Settlement / buying power.** Paper assumes instant cash. Live has T+1
   settlement; a buy can be blocked by unsettled funds even though the
   sells-before-buys intent ordering freed the cash on paper.
6. **Threshold realism.** `tracking.py`'s bands (mean ≤50 bps, decision
   divergence ≤20%, equity gap ≤3%) were calibrated for *paper-vs-replay*. Real
   spread + slippage may warrant a different live band — and possibly a *tighter*
   one as a safety tripwire.

## 3. Scope & non-goals

**In scope:** execution/account-management fidelity between the live broker and
the paper/backtest model — gating, fill-recording accuracy, drift detection,
kill-switch marking, and the rehearsal protocol that proves it.

**Non-goals:** no change to strategy DSL, signal evaluation, intent generation,
or sizing *policy*; no change to `live_enabled`/`mode`/risk caps (human-only); not
re-implementing tracking/reconcile (they exist — we gate and extend them).

## 4. What already exists (do not rebuild)

- `bonito live tracking` — ledger-agnostic fidelity engine (works on the live
  ledger as-is). `tracking.py`: `FillComparison`, bps gaps, decision divergence,
  equity gap, OK/WARN/INSUFFICIENT verdict.
- `reconcile_positions` (`live_runner.py:704`) — ledger vs broker positions.
- `record-fill` (`cli.py:1368`) — records a real fill with `broker_order_id`.
- `preflight` / `PreflightReport` (`live_runner.py:587/618`) — fail-closed gate
  (kill switch, flag mismatch, data outage). The natural home for a drift gate.
- `execute_paper`, `PaperLedger` (with `PaperFill.broker_order_id`,
  `paper.py:42`) — the live ledger reuses the same model.
- The **settled-bar guard** (this session) — live never acts on a forming bar.

## 5. Design

### 5.1 Reconcile as a fail-closed preflight gate
Add a reconcile step to the live cycle that **blocks trading on drift**.
`preflight` gains a `position_drift` check: given broker positions (from the
Robinhood MCP `get_equity_positions`), compare to the ledger; if any symbol
differs beyond the tolerance (Decision D1), `PreflightReport.ok = False` with a
reason, and `bonito live run` refuses. Exits are never gated (a flatten must
always be allowed), mirroring the entry-blocklist/settled-bar pattern.

### 5.2 Fill-recording fidelity
`record-fill` accepts the **actual filled quantity** from the broker order
(`--shares`/`--quantity`) rather than only deriving `dollars/price`, and records
**partial fills** (a fill with `filled < intended` is recorded at the real qty
and flagged). An intent that is **rejected/unfilled** is recorded as a
`no_fill` event (Decision D3) so `tracking.py` counts it as an explicit decision
outcome, not a silent gap. The ledger's qty then always equals the broker's.

### 5.3 Live-calibrated tracking thresholds
`tracking.py` thresholds become mode-aware (a live band vs the paper band,
Decision D2). `bonito live tracking -u universe.live.json` is run **every cycle**
(not just weekly) during the rehearsal, and its WARN is wired into the same
digest/issue path the weekly research uses.

### 5.4 Real-price equity marking for the kill switch
The live cycle marks `ledger.equity(prices)` using **broker-confirmed** prices
(reconcile output / live quotes), never the `entry_price` fallback. If a position
can't be priced, preflight fails closed rather than letting the kill switch see a
stale mark.

### 5.5 Settlement / buying-power awareness (lightweight)
Before placing buys, optionally check broker buying power (MCP `get_accounts`);
if a buy intent exceeds settled buying power, defer it and log it as a
settlement-deferred divergence rather than a silent miss. (Decision D4: gate vs
log-only.)

## 6. Interaction with existing protection (no coverage gap)
- **Intraday stops** (broker-side GTC + the 15-min sweep) are unchanged and keep
  protecting 24/7; the drift gate only blocks *new entries*, never exits/flattens.
- **Settled-bar guard** still gates entries on forming bars; this RFC is
  orthogonal (execution fidelity, not signal timing).
- **Kill switch** gets *more* reliable (real marks), never less.

## 7. Test plan
1. **Drift gate unit tests** — ledger==broker → preflight ok; ledger≠broker
   beyond tolerance → `ok=False` with reason; exits still allowed under drift.
   Non-vacuous (revert the gate → test fails).
2. **Fill-recording tests** — partial fill records actual qty; rejected intent
   records `no_fill`; ledger qty == broker qty after record-fill.
3. **Kill-switch marking test** — a missing price triggers fail-closed, not an
   `entry_price` fallback that hides drawdown.
4. **Live-vs-replay tracking test** — synthetic live ledger with a known fill-bps
   gap → WARN at the live threshold, OK below it.
5. **Determinism/reconcile property test** — reconcile is symmetric and stable;
   tolerance boundary is exact. (Extends `test_methodology_guards.py`.)
6. **End-to-end dry run** — a recorded mock broker order set replayed through
   reconcile → preflight → run, asserting the gate and the tracking verdict.

## 8. Decisions (OPEN — for user sign-off before the build)

- **D1 — Drift gate severity & tolerance.** On ledger-vs-broker mismatch, does
  the cycle **hard-halt (fail-closed, refuse new entries)** or **WARN-and-continue**?
  And the tolerance: exact share match, ±1 share, or ±$ notional?
  *Recommendation: hard-halt on any mismatch beyond a tiny fractional epsilon
  (e.g. >0.5% of the position's shares) — safest; exits always allowed.*
- **D2 — Live fill-bps band.** Acceptable live-vs-replay mean fill gap before
  WARN? Keep paper's 50 bps, widen (real spread), or **tighten** as a tripwire?
  *Recommendation: start at paper's 50 bps mean / surface worst-fill; revisit
  with rehearsal data before scaling size.*
- **D3 — Fill recording shape.** Should `record-fill` require the **actual broker
  quantity** (and support partial / `no_fill`), or keep deriving qty from
  dollars/price and rely on reconcile to correct?
  *Recommendation: require actual qty + a `no_fill` outcome — make the ledger
  match the broker by construction, not by after-the-fact reconcile.*
- **D4 — Settlement/buying-power check.** Gate buys on settled buying power, or
  log-only and let the broker reject?
  *Recommendation: log-only for the rehearsal (broker rejection is the backstop),
  revisit if rejections appear.*
- **D5 — Go-live gate.** Replace "≥2 weeks paper tracking" with **"≥2 weeks of
  green live-vs-replay tracking at 1-share size, reconcile clean every cycle"**?
  *Recommendation: yes — live-at-min-size is far stronger evidence than paper.*

## 9. Rollout & gating
1. Resolve §8 decisions (user).
2. 4-role pipeline implements §5 + §7 (live config untouched; recommendation +
   code + tests only).
3. **Live rehearsal at 1-share size** (extends the RIVN round-trip already done):
   each cycle runs reconcile → preflight → run → place (MCP) → record actual fill
   → `live tracking -u universe.live.json`; assert OK every cycle.
4. ≥2 weeks green (D5) → user sign-off → flip `live_enabled` → scale size
   gradually, re-checking tracking at each step.

## 10. Touchpoint quick-reference
| Concern | Code | Change |
|---|---|---|
| Drift gate | `preflight`/`PreflightReport` `live_runner.py:587/618`; `reconcile_positions:704` | add `position_drift` fail-closed check |
| Fill qty / partial / no_fill | `record-fill` `cli.py:1368`; `execute_paper`/`PaperLedger` `paper.py:160` | accept actual qty; record `no_fill` |
| Live tracking thresholds | `tracking.py:53-58` | mode-aware band; run every cycle |
| Kill-switch marking | `generate_intents` `live_runner.py:262`; `equity()` `paper.py:119` | real-price marks, fail-closed on missing |
| Buying power | new (MCP `get_accounts`) | optional settlement check |
| Go-live gate | `tasks/todo.md` | live-vs-replay rehearsal criterion |
