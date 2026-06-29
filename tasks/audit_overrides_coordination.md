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
| B-1 | Planner | Design Q4 + pre-register; spec Q3 re-validation; draft EXPERIMENT_LOG/lessons text | architect | done | 3-arm Q4 (status-quo / GOOGL→default / GOOGL→blocklist), pre-registered criterion (bench only if an arm beats status-quo Sharpe by >0.05 on BOTH train+holdout; else inconclusive→keep; kill-switch override). **Load-bearing correction (orchestrator-verified):** the anticipated "arm-b re-introduces a regime gate" confound is FALSE — deployed, cluster_GOOGL, cluster_AAPL and iren ALL carry the identical SPY-200 regime_filter, so arm (b) is a clean params-vs-params test. Builder must write the corrected note, not the anticipated caveat. Q3 re-validation spec'd (incl. the Q1=Q3-ON determinism cross-check). Verbatim EXPERIMENT_LOG (Q1 + Q3 as Rejected-table rows = "rejecting the removal") and lessons.md (account-vs-per-symbol meta-lesson) drafts produced. |
| B-2 | Builder | Run Q4; write EXPERIMENT_LOG.md + lessons.md entries | backend-dev | done | **Q4 → INCONCLUSIVE → keep GOOGL→cluster_GOOGL (status quo)**, as pre-registered. 3 arms, none halt: (a) status-quo train 1.0421/holdout 2.5015; (b) GOOGL→default 0.9552/2.6181 (helps holdout +0.12, hurts train −0.09); (c) GOOGL→blocklist 1.0886/2.4988 (helps train +0.05, flat holdout −0.003). Neither alt clears the 0.05 floor on BOTH windows → no change. (Nice account-vs-per-symbol echo: GOOGL-alone P&L is *better* under default $485 vs $196, yet the account's train Sharpe drops.) Arm (a) reproduces Q3 ON to 1e-15 (determinism anchor). EXPERIMENT_LOG.md: 2 Rejected-table rows (Q1 regime, Q3 overrides w/ Q4 verdict). lessons.md: account-vs-per-symbol meta-lesson. Suite 837 passed; config/strategies untouched. Orchestrator verified the verdict from results.json + reviewed the doc diffs directly. |
| B-3 | Tester | Account-replay determinism + live-strategy-load regression tests | tdd-developer | dispatched | |
| B-4 | Validator | Independently re-run Q3+Q4; verify docs + tests; PASS/FAIL | code-reviewer | pending | |

## Run log

- Orchestrator: user said "do all, 4 agent mode" after the Q3 scout (KEEP
  overrides, GOOGL the weak link). Created this doc; scoped to Q3 validation +
  Q4 (GOOGL bench, pre-registered) + logging Q1/Q3/meta-lesson. Live config
  human-only (recommendation only); EXPERIMENT_LOG/lessons explicitly in scope.
  (GitHub MCP disconnected this stretch — CI not queryable via MCP; git push
  unaffected.) Dispatching Planner (B-1).
- Planner (B-1) done. Designed a 3-arm Q4 (status-quo / GOOGL→default /
  GOOGL→blocklist) with a pre-registered noise-floored criterion, spec'd the Q3
  re-validation (incl. a Q1=Q3-ON determinism cross-check), and drafted the
  verbatim EXPERIMENT_LOG (Q1 + Q3) and lessons.md entries. **Caught a
  load-bearing correction:** my dispatch anticipated arm (b) would re-introduce
  a regime gate; the Planner found — and the orchestrator independently
  confirmed via direct read — that deployed/cluster_GOOGL/cluster_AAPL/iren ALL
  carry the same SPY-200 regime_filter, so arm (b) has no gate confound. Also
  confirmed `entry_blocklist` is a real entry-gating field (arm (c) valid).
  Dispatching Builder (B-2) with the full plan + the corrected note.
- Builder (B-2) done. Q4 verdict INCONCLUSIVE → keep status quo (pre-registered
  criterion held; neither GOOGL→default nor GOOGL→blocklist cleared the 0.05
  Sharpe floor on both windows). Wrote the two EXPERIMENT_LOG rows + the
  lessons.md meta-lesson; live config/strategies untouched; suite green. The
  account-vs-per-symbol pattern recurred a *fourth* time within Q4 itself:
  GOOGL→default earns more on GOOGL alone ($485 vs $196) yet lowers account
  train Sharpe. Orchestrator independently confirmed the verdict from
  results.json (arms a/b/c Sharpes + the INCONCLUSIVE string) and reviewed the
  EXPERIMENT_LOG/lessons diffs directly (accurate, format-matching, the Q1
  precision nuance present). Committed the docs. Dispatching Tester (B-3).
