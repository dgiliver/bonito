# Backtest-audit follow-up — 4-role coordination

**Task**: Investigate the two headline open questions from the 2026-06-28
backtest-suite audit, via the strict 4-role pipeline. No role does another's
job; the orchestrator is the single writer of this doc.

## Context

A 190-backtest diverse suite (10 strategies × 5 symbols × train/test + 3
regimes, each vs buy-and-hold over the same window) produced two open questions
worth a rigorous pass (full audit: `scratchpad/BACKTEST_AUDIT.md`, reproducers
`scratchpad/backtest_suite.py` + `audit.py`, raw `scratchpad/results.json`):

- **Q1 — does the live regime filter earn its keep?** The `noregime` A/B (the
  deployed strategy with the SPY-200 regime gate removed) beat the live
  `deployed` strategy out-of-sample on both Sharpe (1.73 vs 1.53) and excess vs
  B&H (+142% vs +23%). But that was per-symbol, on a survivorship-biased symbol
  set, and the gate *did* halve the 2022 drawdown on QQQ (not on SPY). Open
  question: on a rigorous, **account-level**, **pre-registered** test, does the
  SPY-200 regime gate add or destroy value for the deployed strategy?
- **Q2 — is the no-look-ahead guarantee real?** The audit could only argue
  look-ahead is *structurally* prevented (signals on bar N−1, execute open N;
  `ReplayStore` point-in-time; engine fail-closes on missing regime data). It
  was never independently **proven** via a scramble/shift stress-test. Open
  question: does the backtest engine actually leak future information?

## Hard constraints (non-negotiable)

- **Live config is human-only.** This pipeline produces a *recommendation* +
  pre-registered evidence + an `EXPERIMENT_LOG.md` entry for Q1. It must NOT
  edit `config/universe.live.json` (`mode`/`live_enabled`/risk caps or the
  deployed strategy's regime_filter), nor `strategies/deployed_strategy.json`.
- **Pre-register before running** (per `docs/EXPERIMENT_LOG.md` discipline): the
  Q1 adoption criterion is fixed *before* the comparison is run; no
  variant-shopping after seeing results.
- **Q2 is a correctness probe.** If it surfaces real leakage, that is a bug to
  fix (Builder) + lock under a permanent regression test (Tester). If it
  confirms no leakage, the stress-test still ships as a permanent regression
  test so the guarantee can't silently regress.
- Out of scope (separate asks, not this pipeline): committing the audit doc to
  the repo; running the live research loop to mint fresh candidates.

## Roles & sequencing (strict — no role does another's job)

1. **Planner** (`architect`, read-only): read the audit artifacts +
   `EXPERIMENT_LOG.md` + the relevant engine/replay/regime code. Produce the
   exact experiment design for BOTH questions — for Q1: which replay
   (`backtest-account` / `portfolio_backtest`), regime-on vs regime-off harness,
   and a **pre-registered pass/fail criterion** written down before any run;
   for Q2: the specific null/scramble/shift tests, the null expectation, and the
   numeric threshold that distinguishes "leak" from "clean". Name exact
   files/functions/commands. Flag risks (e.g. shuffle breaking indicator
   semantics). NO code, NO experiment runs.
2. **Builder** (`backend-dev`): execute the Planner's design — run the Q1
   regime-on/off comparison and record results against the pre-registered
   criterion; implement the Q2 leakage stress-test harness and run it; if Q2
   finds real leakage, fix the root cause in `src/`. Owns experiment execution
   + any `src/` fix. Does NOT write the permanent regression tests or the
   independent re-verification.
3. **Tester** (`tdd-developer`): turn the Q2 leakage probe into a permanent,
   non-vacuous `tests/` regression (must fail if look-ahead were reintroduced),
   plus a regression test for any Builder fix. Does NOT change `src/` logic
   beyond the tests.
4. **Validator** (`code-reviewer`, read-only): independently re-run BOTH
   experiments from scratch (not by trusting the Builder's numbers), check the
   Q1 criterion was honored as pre-registered (no goalpost-moving), confirm the
   Q2 tests are non-vacuous via revert/restore, confirm no live config / human-
   only file was touched, ruff/full-suite clean. PASS/FAIL with itemized
   findings. Does NOT fix.

## Task table

| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| A-1 | Planner | Experiment design for Q1 (regime A/B, account-level, pre-registered criterion) + Q2 (leakage scramble/shift design, null + threshold); file:line-exact | architect | dispatched | |
| A-2 | Builder | Run Q1 comparison; build+run Q2 leakage harness; fix root cause if Q2 leaks | backend-dev | pending | |
| A-3 | Tester | Q2 leakage probe → permanent non-vacuous regression test; test any fix | tdd-developer | pending | |
| A-4 | Validator | Independently re-run both; verify criterion honored, tests non-vacuous, no live-config touch; PASS/FAIL | code-reviewer | pending | |

## Run log

- Orchestrator: audit complete (190 backtests, benchmark verified). User asked
  to dive into the open questions via the 4-role pipeline. Created this doc;
  scoped to Q1 (regime-filter value) + Q2 (look-ahead leakage proof), with
  live-config changes explicitly out of scope (recommendation only). Dispatching
  Planner (A-1).
