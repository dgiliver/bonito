---
name: pipeline
description: Run a strict 4-role (Planner→Builder→Tester→Validator) implementation pipeline for a non-trivial or safety-critical change. The orchestrator coordinates; each role does only its job; nothing ships without independent validation.
allowed-tools: Task, Bash, Read, Write, Edit, Grep, Glob
---

# 4-Role Implementation Pipeline ("4 agent mode")

A disciplined, auditable way to ship a non-trivial change: four specialized
subagents in sequence, with the main session acting as **orchestrator** — the
single writer of a coordination doc and the only party that commits. Use it when
correctness matters more than speed.

## When to use
- Any change that is **3+ files, architectural, or safety-critical** (anything
  touching live trading, money, the backtest engine, the kill switch, or a
  human-only invariant).
- Investigations/experiments where the answer must be **pre-registered** and
  independently reproduced (e.g. "does removing X help?").
- Skip it for trivial/obvious fixes — don't over-engineer.

## The four roles (strict — no role does another's job)
1. **Planner** (`architect`, read-only): re-verify the touchpoints against the
   *current* `src/` (catch drift), produce a **file:line-exact** diff plan + a
   test plan, resolve the genuine design questions, and flag risks. **No code.**
2. **Builder** (`backend-dev` / the fitting specialist): implement the plan
   exactly. Owns `src/` + touched docs. Does **not** write the regression tests
   or self-validate.
3. **Tester** (`tdd-developer`): the test plan, **non-vacuous** — each test must
   fail if the behavior it guards regresses (prove it by mutating `src/`,
   seeing red, reverting). Tests only; no `src/` logic changes.
4. **Validator** (`code-reviewer`, read-only): independently **re-derive** every
   load-bearing claim from scratch (don't trust prior reports), reproduce the
   test non-vacuity, confirm constraints held. **PASS/FAIL** with itemized
   findings. Does **not** fix.

## Orchestrator rules (you)
- **You are the sole writer of `tasks/<name>_coordination.md`** — the live
  tracking doc (task table + run log). Subagents read it; only you write it.
- **You are the only one who commits.** Review each role's actual diffs
  directly (not just its report) before committing.
- **Spot-check the single most load-bearing claim at every handoff** — cheaply,
  not by redoing the agent's full work (e.g. grep the one call site, re-run the
  one mutation, confirm the one invariant). This has caught real errors
  (vacuous diffs from wrong git base; a "confound" that didn't exist).
- **Enumerate the hard constraints up front** and hold every role to them. For
  this repo that means at minimum: `config/universe*.json`
  `mode`/`live_enabled`/risk caps and `strategies/*.json` are **human-only**;
  **exits are never gated**; **paper mode stays byte-identical** (the
  `execute_paper`/`preflight`/`PaperLedger.equity` determinism surfaces are
  off-limits); new live-only logic is `mode=="live"`-gated.
- **Pre-register before running** any experiment (criterion fixed *before*
  seeing results, one shot, no variant-shopping) — log to
  `docs/EXPERIMENT_LOG.md` at the end (`/grill-me` discipline).

## Flow
1. **Scope** (inline): list the files/touchpoints, name the constraints, pick a
   short task name. Create `tasks/<name>_coordination.md` with: task statement,
   hard constraints, the 4 role definitions, a task table (`| ID | Role | Task |
   Status | Result |`), and a run log. Commit it.
2. **Dispatch Planner.** When it returns: spot-check its top claim, fold the
   plan into the doc (mark Planner done), commit, dispatch Builder with the plan
   embedded verbatim (subagents can't see each other's output).
3. **Builder returns:** review the diffs directly, run `.venv/bin/python -m
   pytest tests/ -m "not slow" -q` + `ruff check`, confirm constraints held
   (e.g. `git diff` shows no human-only file, the determinism surfaces are
   untouched). Commit the implementation. Mark done, dispatch Tester.
4. **Tester returns:** verify non-vacuity yourself on the most important test
   (inject the bug via `sed`/`python`, see the right test go red, `git checkout
   --` restore). Commit the tests. Dispatch Validator.
5. **Validator returns:** relay PASS/FAIL. On PASS, write the closeout run-log
   entry (commit hashes, the verdict, residual caveats) and commit. On FAIL,
   loop the failing item back to the relevant role.

## Async-agent mechanics
- Agent/Task dispatches run in the **background**; you're notified on completion.
  **Do not poll** the output file or `sleep` to wait — end your turn and pick up
  on the `<task-notification>`.
- Each dispatch is a fresh context — embed the **full plan/constraints** in the
  prompt. To continue an existing agent, use SendMessage with its id.
- Commit the coordination-doc update at each handoff (conventional commit;
  `docs(tasks):` for tracking, `feat/fix/test(...)` for the real work). End
  commit messages with the repo's `Co-Authored-By` / `Claude-Session` footers.

## Anti-patterns (learned the hard way)
- **A test that passes with the bug injected is worthless** — invariance-only
  tests miss systematic constant-direction errors; add an absolute-contract test.
- **"This is already covered" is a claim to verify, not trust** — a shared
  fixture's convention can make a new flag's path silently untested.
- **Diffing the wrong git base** (`origin/main..HEAD` when the work is
  uncommitted) gives a vacuous "clean" — diff the working tree.
- **The account-level replay is the honest judge** for any trading-behavior
  decision; per-symbol backtests mislead (no kill switch / capital competition).

## Output
A merged, validated change with a complete `tasks/<name>_coordination.md` audit
trail, every role's commit, and a Validator PASS. Follow with `/review-loop` to
gate the PR before merge.
