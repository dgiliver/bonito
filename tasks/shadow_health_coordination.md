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
| P | Planner | file:line diff + test plan | ✅ done | verified; D1 reproduced by orchestrator |
| B | Builder | implement plan | ✅ done | f8c54e4 |
| T | Tester | non-vacuous tests | dispatched | — |
| V | Validator | independent PASS/FAIL | blocked on T | — |

## Planner output — key decisions (orchestrator-verified)

**Orchestrator spot-check PASSED — D1 reproduced independently:**
`resume(confirm=True)` alone → next `generate_intents` re-halts (`halted=True`, **0 buys**, peak still 6004.60). With `peak_equity` re-baselined to 4468.86 → `halted=False`, **entries generated**. Resume is confirmed a no-op in exactly its intended case.

**Design decisions resolved by the Planner:**
- **Re-baseline by DEFAULT + required `--yes`**, *not* a `--reset-peak` opt-in. A flag reproduces the bug for anyone unaware of it — the un-flagged call would still "succeed" and silently re-halt. `--yes` gives explicitness without a silent-wrong default; without it the command *previews* and exits 1 printing the exact command. `--keep-peak` preserves today's behaviour.
- **Staleness = 10 trading sessions** (not calendar). Evidence: longest *legitimate* no-fill gap before the halt was **2 sessions** (paper) / 1 (live). N=10 is 5× that. The 08-18 halt would have alarmed **2026-09-01**, 19 days before the audit found it. ET session dates via `np.busday_count` (3 paper fills have a UTC date a day ahead of their ET session).
- **New `src/bonito/trading/health.py` + `bonito live health`** — NOT `preflight` (fail-closed gate; would abort cycles and stop exits being evaluated) and NOT `status` (exits 0, called inside `live run`/`performance`; changing its contract leaks into the trading path).
- **Exit codes: 0 OK / 3 ALARM / 1 cannot evaluate.** Not 2 — Click reserves 2 for usage errors. CI consumes the JSON `status` field; the trading job never depends on the code.
- Three independent booleans: `halted` (definitive defect) / `fills_stale` (investigate) / `cycle_idle` (the job itself stopped). Named `fills_stale` not `stale` — "stale" already means bar-age in preflight.

**Planner corrections to my brief:** kill switch is `live_runner.py:302-311` (not ~303-308); CLAUDE.md's "33-symbol universe" is **stale — it's 45** (do not "fix" here); paper-trading.yml's backticks are already escaped so injection is NOT its bug — its real gaps are **missing dedupe** (opens a new issue daily) and **no `continue-on-error`**. Flagged out-of-scope: `intraday-stops.yml:103` has an unguarded `gh issue list` (same latent `bash -e` abort weekly-research already fixed).

## Run log

- Audit 2026-09-20 surfaced D1 + D2. Branch cut from `main`. Coordination doc committed (**2a962ba**). Planner dispatched.
- **Planner returned + spot-checked (PASS).** D1 reproduced independently by the orchestrator. Decisions folded above. Builder dispatched with the plan embedded verbatim.
- **Builder returned; orchestrator reviewed diffs directly.** Diff is surgical — 5 files + new `health.py`, 2 hunks in paper.py / 6 in cli.py, **no whole-file `ruff format` churn** (the failure mode of the two prior Builders). One incidental line-wrap in `paper.py` is the ruff-canonical form (`ruff format --check` passes), so kept. Safety invariant verified independently: `grep health src/bonito/trading/live_runner.py` → no matches; `health` imported only at `cli.py:1563`. Acceptance smoke run by the orchestrator: paper `ALARM exit 3` (`halted=true fills_stale=true sessions_since_fill=23 last_fill=2026-08-18`), live `OK exit 0` (no false alarm), `live resume` preview `exit 1` with the ledger **byte-identical** (sha256 before/after). Full fast suite **907 passed, 1 skipped**; ruff check + format clean; YAML valid. Implementation committed **f8c54e4**. Tester dispatched.
