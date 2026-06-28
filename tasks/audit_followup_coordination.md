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
| A-1 | Planner | Experiment design for Q1 (regime A/B, account-level, pre-registered criterion) + Q2 (leakage scramble/shift design, null + threshold); file:line-exact | architect | done | Build-ready design delivered. Key calls: **Q1 must use the live/replay regime path** (`backtest_account`→`generate_intents`→`_regime_allows`→`signals.regime_allows_long`), NOT the engine's `_compute_regime_mask` the audit used — so the audit's 1.73-vs-1.53 number does NOT transfer; the account comparison stands alone. Account window is fixed 2022-01-03→2026-06-22 (universe data start) so the only account-level bear is 2022 (central confound, biases criterion toward "retain" on ties). Pre-registered Q1 criterion written verbatim (retain if Sharpe_ON≥OFF on both train+holdout, OR DD≥5pp lower on Full/Bear-2022 with ≤20pp return give-up; kill-switch safety override; one-shot, no variant-shopping). Q2: timing contract pinned (signals read bar i-1, fills opens[i], stops/TP same-bar closes[i]); tests A (future-truncation), B (future-scramble incl. gated-regime variant), C (stop/TP same-bar honesty) + per-indicator forward-window check; shuffle (D) scoped out as invalid; thresholds 0 divergences @ rtol=1e-12. Orchestrator independently confirmed the two linchpins (live regime path; backtest-account CLI flags). |
| A-2 | Builder | Run Q1 comparison; build+run Q2 leakage harness; fix root cause if Q2 leaks | backend-dev | done | **Q1 → RETAIN (overturns the audit's tentative "regime may be costing you").** Account replay 2022-01-03→2026-06-22: regime-**OFF** trips the 25% kill switch on 2022-12-22 (−19.5%, Sharpe −0.38) and never trades again; regime-**ON** never halts (+485%, Sharpe 1.63, DD 21.6%). Pre-registered criterion fires RETAIN three ways: safety override (OFF halts, ON doesn't) + (R) Sharpe_ON≥OFF on train+holdout + (D) ≥5pp lower Bear-2022 DD. Orchestrator verified halt status + setup integrity (OFF differs only in regime_filter/name) directly from result JSONs. The per-symbol audit missed this because it has no account-level kill switch / portfolio concentration and uses the engine regime path. Draft EXPERIMENT_LOG entry produced (not appended — human-only). **Q2 → PASS, 0 leaks.** 11 sub-checks (truncation/scramble/gated-regime/stop-TP/indicator) on synthetic + real SPY, 0 divergences, worst fill delta 0.0, no `src/` fix needed. Builder found+fixed a bug in the *probe* (Test B over-asserted: an exit decided after the scramble split legitimately depends on post-split bars; entry-at-227 was unchanged = the leak-relevant check passed) — diagnosis sound; Tester's leak-injection will confirm non-vacuity. No human-only file touched (git clean). |
| A-3 | Tester | Q2 leakage probe → permanent non-vacuous regression test; test any fix | tdd-developer | done | `tests/test_lookahead.py` — 42 deterministic tests (no DuckDB/network, runs under test-fast), green; full suite 837 passed. Went beyond the brief: found that **invariance-only tests miss a systematic constant-direction leak** (the probe's 36 tests all passed *with* an `opens[i]→opens[i+1]` leak injected) and closed it with absolute-contract tests (`test_a0` fill==own-bar-open, `test_a1` signal-from-i-1, regime at-or-before alignment). Also correctly reasoned `searchsorted(side="left")` is a staleness regression not a forward leak, and tested the actually-exploitable variant (dropping the `-1`). Non-vacuity proven for all 3 injections (RED-with-leak / GREEN-after-revert), engine left clean. **Orchestrator independently reproduced the headline blind-spot**: injected the entry-fill leak → `test_a0` RED while invariance tests stayed GREEN (20 passed); reverted clean. Committed `15944e1`. |
| A-4 | Validator | Independently re-run both; verify criterion honored, tests non-vacuous, no live-config touch; PASS/FAIL | code-reviewer | done | **PASS.** Q1: re-ran both account-replay arms from scratch — bit-for-bit match with the Builder (determinism confirmed); OFF `halted=True` 2022-12-22 / dies, ON `halted=False` / +485%; setup is single-variable (diffed); criterion honored, no goalpost-moving; audit's per-symbol number correctly not cited. Q2: independently re-injected both leaks — `test_a0` RED on the entry-fill leak (invariance tests stayed GREEN, reproducing the blind spot), `test_a1` RED on the signal-read leak; reverted clean; 837 passed; engine unchanged from HEAD; ruff clean; tree clean. **One precision correction (does not change the verdict):** "triply-supported" overstates it — (R) Sharpe and (D) give-up are downstream of the *same* halt the safety override already captures (OFF's holdout Sharpe is 0.0 only because it stopped trading), not orthogonal evidence. The genuinely independent corroboration is the no-intraday-stops confirmatory pair (different stop mechanics → OFF still halts 2022-10-14, ON survives). RETAIN rests on: safety override + that confirmatory pair. |

## Run log

- Orchestrator: audit complete (190 backtests, benchmark verified). User asked
  to dive into the open questions via the 4-role pipeline. Created this doc;
  scoped to Q1 (regime-filter value) + Q2 (look-ahead leakage proof), with
  live-config changes explicitly out of scope (recommendation only). Dispatching
  Planner (A-1).
- Planner (A-1) done. Two findings beyond the brief: (1) **Q1's regime path ≠
  the audit's.** The account replay uses `signals.regime_allows_long` (latest-
  bar trailing mean), while the audit's `noregime` win came from the engine's
  `_compute_regime_mask` (searchsorted over a convolved SMA) on single symbols —
  different code, doesn't transfer. Q1 therefore stands on its own account-level
  comparison, and the Builder must NOT cite the audit's 1.73-vs-1.53 as the
  expected result. (2) **Only one account-level bear (2022)** exists (universe
  data starts 2022-01-03), so the gate's whole thesis is tested on a single
  drawdown — the pre-registered criterion deliberately biases toward "retain" on
  ties because removing a safety gate needs strong evidence. Also surfaced: the
  deployed strategy's description validates the EXIT rule (2026-06-12), NOT the
  regime gate — so Q1 is genuinely un-pre-registered and open.
- Orchestrator independently verified the two load-bearing claims before
  dispatching the Builder: (a) `_regime_allows` → `signals.regime_allows_long`
  and `_compute_regime_mask` is confined to `engine.py` (so the account replay
  genuinely exercises the production regime path); (b) `bonito live
  backtest-account` exposes `-u/--start/--end/--holdout/--intraday-stops`
  exactly as the harness needs. Both confirmed. Dispatching Builder (A-2) with
  the full plan embedded.
- Builder (A-2) done. **Headline: the audit's surface finding was wrong at the
  level that matters.** The per-symbol audit suggested the regime gate might be
  costing return; the account-level replay (the actual live pipeline) shows the
  opposite — without the gate the account over-commits into the 2022 bear,
  trips the 25% kill switch (2022-12-22), and is dead for the rest of the
  window (0 holdout trades), while the gated account survives and compounds to
  +485%. Both finding and reason are clear: per-symbol backtests have no
  portfolio kill switch and use a different regime code path. Verdict RETAIN,
  triply-supported (safety override + (R) + (D)). Q2: engine proven leak-free
  (0 divergences across 11 stress checks on synthetic + real data); the only
  bugs were in the probe itself (an `AttributeError`, and a Test-B over-
  assertion that an exit decided *after* the scramble split should be
  invariant — it shouldn't, and the Builder correctly split entry/exit into
  independent decision points). Orchestrator independently re-confirmed the
  kill-switch result, the single-variable setup integrity, and that no human-
  only file was touched, before accepting. Dispatching Tester (A-3) to lift the
  probe into a permanent, deterministic, NON-VACUOUS `tests/test_lookahead.py`.
- Tester (A-3) done. Produced 42 deterministic tests and, crucially, improved
  on the probe's strategy: invariance-only testing (truncation/scramble) is
  blind to a *systematic constant-direction* leak because every run is wrong
  the same way — the Tester proved this (the probe's tests passed with an
  `opens[i]→opens[i+1]` leak live) and added absolute-contract tests that catch
  it. Non-vacuity demonstrated for all 3 mandated injections. Orchestrator
  independently re-ran the headline injection (entry-fill leak → `test_a0` RED,
  invariance tests GREEN, revert clean) — confirmed the blind-spot insight and
  the test's non-vacuity. Committed `15944e1`. Dispatching Validator (A-4) for
  the final independent PASS/FAIL.
- Validator (A-4) done: **PASS.** Re-derived both verdicts from scratch (account
  replay reproduced bit-for-bit; both leak injections reproduced RED→revert→
  GREEN). Flagged one precision correction folded into A-4's result above: the
  RETAIN verdict rests on the kill-switch safety override + the independent
  no-intraday-stops confirmatory pair, NOT on three orthogonal signals — (R)/(D)
  are downstream of the same halt. Verdict unchanged.
- **Pipeline complete. All 4 roles done, Validator PASS.**
  - **Q1 → RETAIN the SPY-200 regime gate.** At the account level (the actual
    live pipeline) the gate is the difference between surviving the 2022 bear
    and tripping the 25% kill switch into a dead account. This overturns the
    audit's tentative per-symbol "the gate may be costing you" — per-symbol
    backtests have no portfolio kill switch and use a different regime code
    path. Live config untouched (human-only); the verdict is "keep the status
    quo," with a draft EXPERIMENT_LOG entry ready for a human to append.
  - **Q2 → engine proven leak-free**, now permanently guarded by
    `tests/test_lookahead.py` (42 non-vacuous tests, test-fast-safe).
  - Caveats on Q1 stand (single 2022 bear; survivorship-biased universe;
    effect is a lower bound — 3 override symbols are un-gated). Remaining
    follow-ups, all OUT of this pipeline's scope: append the EXPERIMENT_LOG
    entry (human); optionally commit the scratch reproducers; the audit's other
    open items (cluster-winner overfit, survivorship) untouched.
