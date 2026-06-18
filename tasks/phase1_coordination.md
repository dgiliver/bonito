# Phase 1 Coordination — process guardrails

Started 2026-06-18. Source of truth for scope: `tasks/todo.md` Phase 1
section. This doc is the single coordination point for a 4-role pipeline;
the orchestrating session (not any of the 4 roles) owns all writes to this
file — each role reports back, the orchestrator records it here. This
avoids two agents racing to edit the same doc.

## Roles (strict separation — no role does another's job)

| Role | Mandate | Explicitly NOT this role's job |
|------|---------|---------------------------------|
| **Planner** | Investigate the codebase, produce a concrete, file-level task breakdown with acceptance criteria, resolve open judgment calls | Writing/editing any code, tests, or docs |
| **Builder** | Implement the planner's spec (source + config + prose docs) | Writing new tests, running the full validation suite, signing off on its own work |
| **Tester** | Write the regression/smoke tests the plan calls for, run the full suite, report pass/fail in detail | Fixing implementation bugs it finds, implementing new features |
| **Validator** | Independent re-verification (suite, lint, types, scope check, review), explicit PASS/FAIL verdict with itemized findings | Fixing anything itself — kicks issues back to Builder/Tester |

## Status legend
`not-started` → `planning` → `building` → `testing` → `validating` → `done` (or `blocked`/`rework`)

## Task table

| ID | Task | Owner | Status | Notes |
|----|------|-------|--------|-------|
| P1-1 | Real CI workflow (`ci.yml`): pytest -m "not slow" + ruff + mypy on every PR/push | Builder | not-started | Check relationship to existing push-to-main workflow that excludes a test file/test by name |
| P1-2 | Re-enable mypy in `.pre-commit-config.yaml` or fix CLAUDE.md's claim that it runs | Builder | not-started | Decide: enable vs. document-as-off. 157 pre-existing mypy errors across the tree (confirmed 2026-06-18) — must not retroactively block unrelated commits |
| P1-3 | De-duplicate kill-filter/`strategy_hash`: `autoresearch_trading.py` vs `trading/validation.py::kill_verdict` | Builder | not-started | Reconcile `MIN_TRADES=30` absolute vs `MIN_TRADES_PER_YEAR=7.0` rate — pick one deliberately, document why |
| P1-4 | `rsi()`/`atr()` NaN-seed fix (same pattern as this week's `ema()` fix) | Builder (fix) + Tester (regression test) | not-started | See `ema()` fix in `backtest/indicators.py` from the regime-sweep session for the pattern to replicate |
| P1-5 | CLI-level smoke test: `bonito backtest` on a regime-filtered strategy end-to-end | Tester | not-started | This is the exact blind spot that let the missing-`regime_data` CLI bug ship undetected — pure test addition, underlying bug already fixed |
| P1-6 | Backfill `docs/EXPERIMENT_LOG.md` with this week's findings (MACD NaN bug, CLI `regime_data` bug, deployed-strategy kill-filter failure) | Builder | not-started | Source material is in `tasks/todo.md`'s 2026-06-18 review section |

## Decisions log
(Planner fills in via its report; orchestrator records resolution here.)

## Run log
- 2026-06-18: Doc created, task table seeded from `tasks/todo.md`. Kicking off Planner.
