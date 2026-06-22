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
| A-1 | Planner | Map paper-fill-price vs replay-fill-price flow; ranked falsifiable hypothesis tree for ARM both-legs ~10% gap; investigation/fix plan | architect | in progress |
| A-2 | Builder | Confirm root cause + minimal fix (or documented "legitimate") | debugger | blocked on A-1 |
| A-3 | Tester | Regression test | tdd-developer | blocked on A-2 |
| A-4 | Validator | Independent re-verify + PASS/FAIL | code-reviewer | blocked on A-3 |

## Decisions log

(none yet)

## Run log

- Orchestrator: created coordination doc, dispatched Planner (A-1).
