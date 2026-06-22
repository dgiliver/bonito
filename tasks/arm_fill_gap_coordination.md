# ARM fill-gap investigation — 4-role coordination

**Task**: Root-cause the paper-vs-replay tracking WARN, specifically the ARM
fill-price discrepancy. Fix if it's a code/data bug; document precisely if
it's a legitimate (expected) divergence. Driven by the strict 4-role
pipeline — no role does another's job; orchestrator is the single writer of
this doc.

## Trigger / evidence

`bonito live tracking` → **WARN** (report
`livetrade/research/tracking_2026-06-22_145653.json`):
- `mean fill gap 311bps > 50bps`
- `equity gap -7.5% > ±3%` (report self-annotates: "config changes during
  the paper window inflate this early on")
- `decision_divergence 0.1667` (2 of 12 paper fills unmatched in replay:
  ORCL buy, DELL sell)

Per-fill gaps — the WARN is dominated by **ARM**, not spread evenly:

| Symbol | Leg | Paper px | Replay px | Gap (bps) | Matched |
|--------|-----|----------|-----------|-----------|---------|
| MU   | buy  | 910.03  | 891.88  | +203.5  | ✓ |
| SNDK | buy  | 1625.98 | 1643.23 | −104.9  | ✓ |
| DELL | buy  | 373.70  | 369.83  | +104.6  | ✓ |
| **ORCL** | buy | 204.16 | — | — | **✗ (unmatched)** |
| **ARM** | buy | 309.93 | 342.23 | **−943.8** | ✓ |
| SNDK | sell | 1829.73 | 1807.55 | +122.7 | ✓ |
| **ARM** | sell | 342.23 | 376.45 | **−909.1** | ✓ |
| SNDK | buy  | 1881.51 | 1881.51 | 0.0    | ✓ |
| IREN | buy  | 56.71   | 59.77   | −512.0  | ✓ |
| **DELL** | sell | 413.46 | — | — | **✗ (unmatched)** |
| MU   | sell | 1074.23 | 1095.46 | −193.8 | ✓ |
| SNDK | sell | 2097.98 | 2101.12 | −15.0  | ✓ |

**Key anomalies to explain:**
1. ARM is off ~9–10% on **both** legs, same sign (paper < replay both times).
   Slippage is small and random-signed; this is systematic.
2. **Exact-price collision**: paper ARM *sell* (342.23) == replay ARM *buy*
   (342.23), byte-identical. Suggests replay entered ARM on a different
   bar/date than paper did.
3. The anomalies cluster in the **second entry batch of 2026-06-10**: ARM
   buy and ORCL buy share timestamp `16:13:52` (vs the first batch at
   `15:49:18`). ORCL (same batch) is *unmatched* entirely. Smells like a
   mid-window config change / intraday re-entry.

## Roles & sequencing (strict — no role does another's job)

1. **Planner** (`architect`, read-only): map the exact data flow for how a
   paper fill's price is set vs. how the replay derives the fill price for
   the same signal; produce a ranked, falsifiable hypothesis tree + a precise
   investigation/fix plan. NO code changes.
2. **Builder** (`debugger`): execute the plan, confirm the root cause with
   hard evidence, implement the minimal fix IF it's a bug — or document
   precisely if it's legitimate divergence. Owns `src/`.
3. **Tester** (`tdd-developer`): regression test that locks in correct
   behavior / would have caught this. Does not change `src/` logic.
4. **Validator** (`code-reviewer`, read-only): independently re-derive the
   root cause from raw data and re-verify the fix; PASS/FAIL with itemized
   findings. Does NOT fix.

## Task table

| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| A-1 | Planner | Map paper-fill-price vs replay-fill-price flow; ranked falsifiable hypothesis tree for ARM both-legs ~10% gap; investigation/fix plan | architect | done | Root cause = **no code bug** (conf ~0.95). ARM both-legs gap + 342.23 collision = paper intraday-quote entry 06-10 vs replay close entry 06-11 (one bar behind a sharp rally; replay sell = entry×1.10 TP = 376.45). −7.5% equity gap = mid-window config drift (5-slot/$1k → 8-slot/12.5% on 06-12). Unmatched ORCL = paper bought intraday 204.16 on a bar whose close (201.26) was BELOW ema_slow (203.02). H4/H5/H6 refuted. See Decision #1. |
| A-2 | Builder | Independently reproduce B1-B4 via REAL code paths to confirm/refute the no-bug diagnosis; NO source edits (fix is gated on a user policy decision) | debugger | done | **CONFIRMED** — all B1-B4 reproduced via real code paths, byte-identical, zero discrepancy, no repo files touched. B2 (load-bearing): real `backtest_account` enters ARM buy 06-11 @ 342.2300109863281 (= 06-11 close), sell @ 376.45301 (= ×1.10 TP), and produces ZERO ORCL buy events. B3: matcher pairs ARM paper-06-10 ↔ replay-06-11 as the ONLY candidate within ±1d (06-12 at 1d11h correctly excluded) — no off-by-one. B4: paper buys inside 06-10 [low,high] but ≠ close (intraday entries); SNDK 06-11 buy 0.0 bps refutes split/adjustment; ORCL gate False via real `indicators.ema/rsi` (close 201.26 < ema_slow 203.02, $1.76 margin). Bonus: replay round-trips ARM repeatedly to 06-17; matcher correctly consumes only the first pair. |
| A-3 | Tester | Characterization test locking in the matcher invariants the investigation relied on (±1d tolerance boundary, delta_bps sign convention, unmatched=decision-divergence); synthetic data, CI-deterministic, no live-DuckDB dependency | tdd-developer | done | 3 new tests in `tests/test_tracking.py::TestMatchFills`, exercising the REAL `match_fills` with synthetic CI-deterministic inputs: `test_two_days_apart_exceeds_tolerance_boundary` (the tight ±1d edge the pre-existing 4-day-gap test was too loose to catch), `test_delta_bps_negative_when_paper_below_replay`, `test_unmatched_fill_counts_toward_decision_divergence`. Verified existing coverage first (didn't duplicate). Non-vacuous: mutating `MATCH_TOLERANCE_DAYS`→2 and flipping the bps sign each failed the relevant test, then reverted. 3 passed; full file 16 passed; ruff clean. Orchestrator independently confirmed `src/` diff is empty post-revert; only `tests/test_tracking.py` touched. |
| A-4 | Validator | Independently re-verify the full deliverable (diagnosis grounded in source, test non-vacuous + CI-deterministic, lessons doc faithful, tree clean); PASS/FAIL. Read-only — fixes nothing | code-reviewer | done | **PASS** (independent, read-only). All 5 items substantiated: (1) invariants source-grounded — `MATCH_TOLERANCE_DAYS=1` @ `tracking.py:50`, `delta_bps` formula @ `:151`, config-drift annotation @ `:289`; (2) 3 tests call the real `match_fills`, each with an explicit breaking mutation, zero I/O deps — 16 passed, full suite 763 passed/1 skipped, no collateral breakage; (3) lessons doc faithful, no overstatement; (4) ORCL gate re-confirmed via fresh query+compute (close 201.260 < ema_slow 203.023 → False); (5) tree clean, `src/` zero changes. No issues found. |

## Decisions log

**#1 — Root cause is a legitimate divergence, not a bug (Planner, A-1; pending
Builder confirmation).** The tracking WARN has three fully-explained
components, none a math/code error:
- *ARM −944/−909 bps both legs + the 342.23 paper-sell==replay-buy collision*:
  paper opened ARM from an **intraday quote (309.93) on 06-10**; the close-based
  replay first enters ARM on the **06-11 close (342.23)** and rides the
  06-10→06-12 rally one bar behind, exiting at its 10% TP (342.23×1.10=376.45).
  Same-signed large gaps are the inevitable intraday-vs-next-day-close artifact
  during a sharp uptrend. Byte-stable across 3 weekly reports ⇒ structural.
- *−7.5% equity gap*: replay runs the CURRENT 8-slot/12.5% config over a window
  whose early fills were under the old 5-slot/$1k config (changed 06-12,
  `b8bb3a6`/`32d976c`). Equity gap grows (1.96→−5.73→−7.5%) while fill bps stay
  frozen ⇒ config-drift signature, already annotated in `tracking.py:289`.
- *Unmatched ORCL (+DELL)*: paper bought ORCL intraday at 204.16 on 06-10, but
  that bar's **close (201.26) was below ema_slow (203.02)** — the entry gate is
  False, so the close-based replay never enters ORCL ⇒ no replay buy to match.
- H4 (matcher off-by-one), H5 (adjusted/split mismatch — SNDK 06-11 buy is
  0.0 bps, refutes a global factor), H6 (wrong-fill pairing) all REFUTED.

**The one real signal — a USER POLICY DECISION, not an auto-fix:** the
paper/live pipeline opens positions from **intraday quotes on bars whose close
does not satisfy the entry rule** (ORCL is the clean example). The close-based
replay — and the weekly research gate that trusts it — will never reproduce
those entries. Options: (a) restrict entries to confirmed-close signals
[changes LIVE trading behavior]; (b) exclude config-change-window /
unconfirmed-close fills from tracking [changes the pre-live GATE semantics];
(c) accept + document as a known early-window artifact that washes out.
Per the live-status skill + CLAUDE.md (entry logic & gate semantics are
human-domain), (a)/(b) require explicit user sign-off; (c) is the safe
no-regret default. To be surfaced after independent Builder/Validator
confirmation.

## Run log

- Orchestrator: created coordination doc, dispatched Planner (A-1).
- Planner (A-1) → done. Root cause = no code bug (intraday-entry + config-drift
  artifact); one policy signal flagged. See Decision #1.
- Orchestrator: dispatched Builder (A-2) to independently reproduce B1-B4 via
  the real code paths and confirm/refute the no-bug diagnosis (no source edits
  — fix gated on user).
- Builder (A-2) → done. CONFIRMED no code bug; all B1-B4 reproduced
  byte-identically via real code paths, zero repo changes. Two independent
  agents now agree.
- Orchestrator: dispatched Tester (A-3) for a CI-deterministic characterization
  test of the matcher invariants the diagnosis relied on.
- Tester (A-3) → done. 3 non-vacuous tests added to `TestMatchFills`; full
  tracking file 16 passed; `src/` confirmed clean by orchestrator.
- Orchestrator: took safe option (c) — recorded the finding in
  `tasks/lessons.md` (no behavior change). Dispatched Validator (A-4) to
  independently re-verify the full deliverable before commit.
- Validator (A-4) → **PASS**. Independent third confirmation of the diagnosis,
  test non-vacuousness, doc faithfulness, and tree cleanliness. See Decision #2.
- Orchestrator: committed the deliverable; surfaced the (a)/(b)/(c) policy
  decision to the user. **Investigation CLOSED.**

## Outcome

Verdict (4 independent confirmations — Planner, Builder, Validator, + the
orchestrator's own pytest run): **the tracking WARN is not a code bug.** It is
a legitimate, self-correcting artifact of (1) paper entries priced off an
intraday/forming bar vs. the replay's settled-close entry one bar later, and
(2) mid-window config drift. Deliverable: a 3-test characterization lock on the
`match_fills` invariants + a `tasks/lessons.md` entry so it isn't
re-investigated. Option (c) (accept + document) taken; (a)/(b) put to the user.

**Decision #2 — Investigation closed; one open sub-question for the user.** The
WARN self-resolves as the config-change-window fills age off the trailing
window and matched fills accrue under the stable current config — so no action
is *required*. The one genuine fidelity signal — the pipeline opening a
position on an intraday/forming bar the close-based strategy wouldn't enter
(ORCL) — turns on whether that recurs in the AUTOMATED daily path (the Routine
fires 3:45pm ET, before the 4pm close, so `data.closes[-1]` may be a forming
bar) or was only a manual pre-live MCP rehearsal artifact. Recommended:
verify recurrence BEFORE any live-behavior change (a) or gate-semantics change
(b). That verification is itself a new, separate investigation — not folded
into this one.
