# Audit follow-up phase 2 — overrides validation, GOOGL bench, logging (4-role)

**Task**: three deliverables, one strict 4-role pipeline (no role does another's
job; orchestrator is sole writer of this doc):
1. **Validate Q3** — independently re-verify the orchestrator's scout finding
   that the per-symbol cluster overrides (AAPL/GOOGL/IREN) should be KEPT at the
   account level.
2. **Q4 — focused GOOGL bench** — a pre-registered experiment on whether GOOGL
   specifically should be benched (it was the one override with marginally
   negative attribution).
3. **Log it** — write the validated Q1 (regime RETAIN) and Q3 (overrides KEEP)
   findings to `docs/EXPERIMENT_LOG.md`, and the account-vs-per-symbol
   meta-lesson to `tasks/lessons.md`.

## Context

Scout findings to date (all account-level replay, 2022-01-03→2026-06-22,
holdout 2025-01-01, intraday-stops ON):
- **Q1 (done, Validator PASS):** RETAIN the SPY-200 regime gate — removing it
  trips the 25% kill switch in 2022 and the account dies.
- **Q3 (orchestrator scout, needs independent validation):** KEEP the per-symbol
  overrides. Pre-registered criterion (Sharpe(ON) ≥ Sharpe(OFF) on BOTH train
  AND holdout) passed: train 1.04 vs 0.93, holdout 2.50 vs 2.33; ON +485%
  vs OFF +409%; neither halts. Per-symbol realized-P&L attribution: IREN bespoke
  +$1,928 vs default +$384 (**+$1,544**); AAPL cluster +$7 vs default −$226
  (**+$234**, protective); **GOOGL cluster +$196 vs default +$248 (−$52, the one
  weak link)**. Reproducer: `scratchpad/q3/` (PREREGISTER.md, the two scratch
  universes, results.json).
- **Meta-pattern:** three times now (regime gate; overrides) per-symbol
  backtests pointed one way and the account replay the other — because per-symbol
  views miss the kill switch, capital competition, and concentration.

## Hard constraints (non-negotiable)

- **Live config & strategies are human-only.** Do NOT edit
  `config/universe.live.json`, `config/universe.json`,
  `strategies/deployed_strategy.json`, or any `strategies/*.json`. Q3/Q4 use
  scratch copies; verdicts are RECOMMENDATIONS only.
- **`docs/EXPERIMENT_LOG.md` and `tasks/lessons.md` ARE to be written** (user
  explicitly authorized) — they are documentation, not live config. Match the
  existing format of each file exactly.
- **Pre-register Q4 before running** (EXPERIMENT_LOG discipline); one shot, no
  variant-shopping.
- The account-level replay (`backtest_account`) is the judge — per-symbol
  engine backtests do not bind these decisions.

## Roles & sequencing (strict)

1. **Planner** (`architect`, read-only): design Q4 (GOOGL-bench A/B options +
   pre-registered criterion); specify exactly what the Validator must re-run to
   independently confirm Q3; read `docs/EXPERIMENT_LOG.md` + `tasks/lessons.md`
   and draft the exact entry text (Q1, Q3, meta-lesson) the Builder will write,
   matching each file's format. NO writes, NO experiment runs.
2. **Builder** (`backend-dev`): run Q4 against the pre-registered criterion;
   write the `EXPERIMENT_LOG.md` + `lessons.md` entries per the Planner's draft
   (these docs only — NOT live config). Owns experiment execution + the doc
   writes. Does NOT write the regression tests or do the independent re-verify.
3. **Tester** (`tdd-developer`): a durable regression test that locks the
   methodology the findings rest on — account-replay **determinism** (same
   inputs → identical result) and that every live universe strategy (default +
   the 3 overrides) **loads and validates**. Non-vacuous. Tests only.
4. **Validator** (`code-reviewer`, read-only): independently re-run Q3 AND Q4
   from scratch; confirm the criteria were honored as pre-registered; confirm
   the EXPERIMENT_LOG/lessons entries match the evidence (no overclaim); confirm
   the tests are non-vacuous (revert/restore); confirm no live config/strategy
   file was touched; ruff + full suite clean. PASS/FAIL, itemized. Does NOT fix.

## Task table

| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| B-1 | Planner | Design Q4 + pre-register; spec Q3 re-validation; draft EXPERIMENT_LOG/lessons text | architect | dispatched | |
| B-2 | Builder | Run Q4; write EXPERIMENT_LOG.md + lessons.md entries | backend-dev | pending | |
| B-3 | Tester | Account-replay determinism + live-strategy-load regression tests | tdd-developer | pending | |
| B-4 | Validator | Independently re-run Q3+Q4; verify docs + tests; PASS/FAIL | code-reviewer | pending | |

## Run log

- Orchestrator: user said "do all, 4 agent mode" after the Q3 scout (KEEP
  overrides, GOOGL the weak link). Created this doc; scoped to Q3 validation +
  Q4 (GOOGL bench, pre-registered) + logging Q1/Q3/meta-lesson. Live config
  human-only (recommendation only); EXPERIMENT_LOG/lessons explicitly in scope.
  (GitHub MCP disconnected this stretch — CI not queryable via MCP; git push
  unaffected.) Dispatching Planner (B-1).
