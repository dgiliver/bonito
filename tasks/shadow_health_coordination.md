# Shadow Health — 4-Role Pipeline Coordination

**Branch:** `claude/shadow-health` (from `main`)
**Orchestrator:** main session (sole writer of this doc, sole committer)
**Origin:** the 2026-09-20 live audit

## Problem (two defects, both found by the audit)

### D1 — `live resume` cannot actually restore a halted ledger
`PaperLedger.resume()` (`src/bonito/trading/paper.py:329`) clears `halted` and
`halt_reason` but does **not** re-baseline `peak_equity`. The kill switch
(`live_runner.py:303-308`) computes `drawdown = note_equity(equity)` against that
same stale peak. So whenever equity is still below `peak × (1 - threshold)`,
resume clears the halt and **the very next cycle re-halts immediately** — resume
is a no-op in exactly the scenario it exists for.

Live proof: paper peak `$6,004.60`, equity `$4,468.86` → drawdown 25.58% ≥ the
25% cap. Resuming today would flap: resume → halt → resume → halt.

### D2 — no staleness alarm; a dead shadow reports success
The paper shadow kill-switched **2026-08-18** and has held zero positions and
produced zero fills for **33 days**. The daily paper cycle kept committing
`daily paper cycle … (total fills: 128)` every day — fill count frozen, run
green. Nothing alerted. The pre-live fidelity gate is therefore structurally
unable to pass, and live traded a month with no working shadow.

## Scope

| File | Change |
|------|--------|
| `src/bonito/trading/paper.py` | `resume()` gains the ability to re-baseline `peak_equity` |
| `src/bonito/cli.py` | `live resume` exposes it; NEW non-gating health/staleness command |
| `src/bonito/trading/live_runner.py` (or a small module) | staleness/halt detection logic |
| `.github/workflows/paper-trading.yml` | alarm → GitHub issue, hardened like `weekly-research.yml` |
| `tests/` | non-vacuous tests for both defects |

## Hard constraints (every role held to these)

1. **The alarm NEVER gates trading.** It must not live in `preflight` or any path
   that aborts a cycle. Alarm ≠ gate. A health check that halts the pipeline is
   the opposite of the fix.
2. **`resume` stays human-only** (CLAUDE.md: "Human-only, never automated:
   `bonito live resume`"). Re-baselining the peak must be an explicit, opt-in
   human action — never automatic, never reachable from a Routine/Action.
3. **Exits are never gated**; `mode`/`live_enabled`/risk caps/`config/universe*.json`
   /`strategies/*.json` are untouched.
4. **Paper determinism preserved** — no behavior change to `execute_paper`,
   `preflight`, or `PaperLedger.equity`. Default paths byte-identical.
5. Losing the halt signal is a REGRESSION: a genuine 25% drawdown is real
   information. Do not auto-resume, and do not weaken the kill switch.
6. 100-char lines, `ruff format`/`ruff check` clean, mypy advisory, full
   `pytest -m "not slow"` green.

## Roles

1. **Planner** (`architect`, read-only): re-verify touchpoints file:line-exact; resolve the design questions below; produce an exact diff plan + test plan. No code.
2. **Builder** (`backend-dev`): implement the plan exactly. Owns `src/` + the workflow. No tests, no self-validation.
3. **Tester** (`tdd-developer`): non-vacuous tests — each must fail if its guard regresses, proven by mutation. Tests only.
4. **Validator** (`code-reviewer`, read-only): independently re-derive every claim; reproduce non-vacuity; confirm constraints. PASS/FAIL. No fixes.

## Design questions for the Planner

- Re-baseline as a `--reset-peak` flag on `live resume`, or default behavior with a printed warning? (Flag is safer/explicit; default is more likely to actually work when a human uses it. Recommend and justify.)
- What exactly counts as "stale"? Zero fills for N **trading** days vs calendar days; what N avoids false alarms during legitimately quiet stretches on a 45-symbol universe?
- Where does the check live — new `bonito live health`, or extend `status`? (Must NOT be `preflight`.)
- Exit-code semantics so CI can alarm without failing the trading job.
- Should it check the live ledger too (same command, `-u` selects)?

## Task table

| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| P | Planner | file:line diff + test plan | dispatched | — |
| B | Builder | implement plan | blocked on P | — |
| T | Tester | non-vacuous tests | blocked on B | — |
| V | Validator | independent PASS/FAIL | blocked on T | — |

## Run log

- Audit 2026-09-20 surfaced D1 + D2. Branch cut from `main`. Coordination doc committed. Planner dispatched.
