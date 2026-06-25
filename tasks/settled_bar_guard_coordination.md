# Settled-vs-forming bar guard — 4-role coordination

**Task**: Implement the settled-vs-forming bar guard specified in
`docs/RFC_SETTLED_BAR_GUARD.md` (§5) and fix the live Routine's documented
schedule time (§4), per the user's resolved decisions (RFC §8, 2026-06-23):
detection = **D1** (ET-clock heuristic, stdlib `zoneinfo`, no new
dependency); build order = **both** the code guard and the schedule fix in
this pass; preflight severity = **soft WARN**. Driven by the strict 4-role
pipeline — no role does another's job; orchestrator is the single writer of
this doc.

## Context

Closes the prospective hazard flagged by the ARM fill-gap investigation
(`tasks/arm_fill_gap_coordination.md`, Decision #3): the live cycle evaluates
strategy signals on `data.closes[-1]` unconditionally. When run intraday —
the documented Routine fires 3:45pm ET, 15 min before the 4pm close —
`refresh_data` (`live_runner.py:145`) has already ingested a same-day
**forming** bar (yfinance same-day row, last-trade-as-close), and nothing in
the daily path distinguishes it from a settled one. Full design, rationale,
and test plan are in the RFC; this doc tracks only the build.

**Exemption that must hold throughout**: the intraday stop sweep
(`live_sweep`/`_sweep_stops`/`check_stops`, `cli.py:1105-1171`) sources live
quotes directly and never calls `generate_intents` — it is exempt by
construction, not by a flag. No change here should touch that path.

## Roles & sequencing (strict — no role does another's job)

1. **Planner** (`architect`, read-only): re-verify the RFC's touchpoints
   against current `src/` (catch any drift since the RFC was written);
   produce the exact file:line diff plan for the Builder; pin a concrete
   schedule time for `docs/AUTONOMOUS_LIVE_ROUTINE.md` step 2 (or
   explicitly flag if it can't be pinned without observed Routine
   runtimes). NO code changes.
2. **Builder** (`backend-dev`): implement exactly the Planner's plan. Owns
   `src/` plus the two docs files if anything in them needs to change.
3. **Tester** (`tdd-developer`): the 5-part test plan from RFC §7 —
   `_is_forming` unit table, `generate_intents` integration (forming ⇒
   skip/hold, settled ⇒ fires), sweep-exemption regression, build-time tz
   check, non-vacuous proof (mutate-and-confirm-fail). Does not change
   `src/` logic beyond the tests themselves.
4. **Validator** (`code-reviewer`, read-only): independently re-derive
   settled-vs-forming (not calendar-day) correctness; re-confirm the sweep
   exemption via its own call-graph grep (not by trusting the Builder's
   claim); confirm tests are non-vacuous via revert/restore; confirm the
   post-close paper cron sees a no-op; ruff/mypy/full suite clean.
   PASS/FAIL with itemized findings. Does NOT fix.

## Task table

| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| C-1 | Planner | Re-verify RFC touchpoints vs. current `src/`; produce file:line diff plan; pin Routine schedule time | architect | dispatched | |
| C-2 | Builder | Implement C-1's plan: `_is_forming` helper + entry/exit/regime/preflight wiring + schedule doc update | backend-dev | pending | |
| C-3 | Tester | RFC §7 test plan (5 parts), non-vacuous | tdd-developer | pending | |
| C-4 | Validator | Independent re-verification; PASS/FAIL | code-reviewer | pending | |

## Run log

- Orchestrator: user resolved all 3 RFC §8 decisions, said "go for it".
  Created this coordination doc, dispatched Planner (C-1).
