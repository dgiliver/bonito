# Phase 2 Coordination — near-term hardening

Started 2026-06-19, immediately following Phase 1's PASS verdict (see
`tasks/phase1_coordination.md`). Source of truth for scope: `tasks/todo.md`
Phase 2 section (8 items). Same operating model as Phase 1: a 4-role
pipeline (Planner → Builder → Tester → Validator), strict separation, no
role does another's job. The orchestrating session owns all writes to this
file — each role reports back, the orchestrator records it here.

## Roles (strict separation — no role does another's job)

| Role | Mandate | Explicitly NOT this role's job |
|------|---------|---------------------------------|
| **Planner** | Investigate the codebase, produce a concrete, file-level task breakdown with acceptance criteria, resolve open judgment calls, flag risk/sequencing | Writing/editing any code, tests, or docs |
| **Builder** | Implement the planner's spec (source + config + prose docs) | Writing new tests, running the full validation suite, signing off on its own work |
| **Tester** | Write the regression/smoke tests the plan calls for, run the full suite, report pass/fail in detail | Fixing implementation bugs it finds, implementing new features |
| **Validator** | Independent re-verification (suite, lint, types, scope check, review), explicit PASS/FAIL verdict with itemized findings | Fixing anything itself — kicks issues back to Builder/Tester |

## Status legend
`not-started` → `planning` → `building` → `testing` → `validating` → `done` (or `blocked`/`rework`)

## Task table

| ID | Task | Owner | Status | Notes |
|----|------|-------|--------|-------|
| P2-1 | Test `trading/monitor.py` (P&L/drawdown, zero coverage today) + `autoresearch_trading.py`'s pure functions (`split_data`, `validate_no_lookahead`, `apply_kill_filters`) | Tester | not-started | |
| P2-2 | Deliberate `str, Enum` → `enum.StrEnum` migration for the 7 domain enums behind the `UP042` ignore | Builder | not-started | Risk: `StrEnum` changes `str(member)` formatting; enums are embedded in JSON strategy configs — needs a compat check before migrating. |
| P2-3 | Reconcile ruff versions: pre-commit pin (v0.8.2) vs `.venv` vs `pyproject.toml` floor | Builder | not-started | Cosmetic only (assert-wrapping style); CI unaffected either way. |
| P2-4 | Add `broker_order_id` to `PaperFill`/`TradeIntent`; require for live-mode fills; reject `record-fill` in paper mode | Builder | not-started | Touches live-trading ledger — extra scrutiny per standing trading-safety rules. |
| P2-5 | Add a confirmation requirement to `PaperLedger.resume()` (currently human-only by convention, not enforced) | Builder | not-started | Same ledger-safety scrutiny as P2-4. |
| P2-6 | Document the Robinhood account-scoping boundary (••••8597, cash-only) as non-code-enforceable in `docs/AUTONOMOUS_LIVE_ROUTINE.md`; add a runbook check if MCP exposes account identity | Builder | not-started | Docs-only. |
| P2-7 | Frontend: delete dead `IntelligentChart.tsx` V1 + test + re-export; align `useEffect` deps to `[height, config]`; type `any` in `ChartContainer.tsx`/`BaseChartPanel.ts`; fix ~8 default-export violations | Builder | not-started | Frontend-only, no backend/trading-logic risk. |
| P2-8 | Scaffold a minimal Playwright config + 1-2 smoke specs (currently zero exist despite doc/skill references implying otherwise) | Tester | not-started | |

## Decisions log

| # | Question | Resolution |
|---|----------|------------|

## Run log
- 2026-06-19: Doc created, task table seeded from `tasks/todo.md` Phase 2 section (8 items). Kicking off Planner.
