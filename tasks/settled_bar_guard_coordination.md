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
| C-1 | Planner | Re-verify RFC touchpoints vs. current `src/`; produce file:line diff plan; pin Routine schedule time | architect | done | RFC touchpoints confirmed (line numbers drifted, corrected). Caught an unflagged regression: `generate_intents` is also called by the account replay (`portfolio_backtest.py:279`) — a naive guard would zero every replay day. Fix: `require_settled: bool = True` param, `False` only at that call site. Resolved the RFC's tz ambiguity: stored daily timestamps are ET-midnight-of-D as naive UTC (04:00 UTC summer / 05:00 UTC winter). `signals.py`/`cli.py` sweep confirmed unchanged. Schedule: keep 3:45pm ET. Full plan in run log. |
| C-2 | Builder | Implement C-1's plan: `_is_forming` helper + entry/exit/regime/preflight wiring + schedule doc update | backend-dev | done | Implemented §1-§6, §9, §10 exactly — zero drift from the plan (every "Current:" snippet matched the live tree byte-for-byte). `signals.py`/`cli.py` spot-checked, confirmed no changes needed. ruff clean; mypy's one error on `portfolio_backtest.py` confirmed pre-existing via `git stash` diff. `pytest tests/ -m "not slow"`: 763 passed, 1 skipped, 8 deselected — full green. Reproduced all 7 rows of the Planner's empirical proof table directly against the shipped helper — all matched. Orchestrator reviewed the diff directly (not just the report) before committing. |
| C-3 | Tester | RFC §7 test plan (5 parts), non-vacuous | tdd-developer | done | `tests/test_settled_bar_guard.py` (new, 30 active + 2 slow tests) covers parts 1-4; part 5 (mutation) executed live against `src/`, restored, documented. **Corrected the Planner/Builder's claim that existing replay coverage was sufficient**: pre-existing `test_portfolio_backtest.py` fixtures use naive-midnight timestamps that are always "settled" regardless of `require_settled`, so they never exercised the `portfolio_backtest.py:283` opt-out. Added `TestSettledBarGuardReplayWiring` (winter+summer) using the real ET-midnight-as-UTC convention, proven load-bearing via mutation. `pytest tests/ -m "not slow"`: 795 passed, 1 skipped, 10 deselected. ruff/ruff-format clean. Orchestrator independently re-ran the replay-regression mutation (flip `require_settled=False`→`True` at :283) and confirmed the same 2-fail/12-pass split before restoring. |
| C-4 | Validator | Independent re-verification; PASS/FAIL | code-reviewer | pending | |

## Run log

- Orchestrator: user resolved all 3 RFC §8 decisions, said "go for it".
  Created this coordination doc, dispatched Planner (C-1).
- Planner (C-1) done. Verified all RFC §10 touchpoints against current
  `src/`; line numbers had drifted (corrected in the diff plan below) but no
  structural surprise there. Two findings beyond the RFC itself:
  - **RFC API-sketch gap, now resolved.** Stored daily bar timestamps are
    **ET-midnight-of-D as naive UTC** (`04:00 UTC` in EDT, `05:00 UTC` in
    EST) — not midnight-UTC, not naive-ET — verified directly against
    `data/market_data.duckdb`. `_is_forming` must convert both `last_bar`
    and `as_of` through `America/New_York` via `zoneinfo`; a naive `.date()`
    would be wrong in principle (lucky only in summer).
  - **Unflagged regression, now mandatory in the plan.** `generate_intents`
    is also called by the account replay (`portfolio_backtest.backtest_account`,
    `portfolio_backtest.py:279`, independently re-confirmed by orchestrator
    grep) with `as_of=day` — itself a settled bar timestamp. A naive guard
    would read every replayed bar as forming and **zero the entire
    replay**, silently breaking the weekly-research adoption gate
    (`tracking.py`, `auto_research.py`, `bonito live backtest-account/-universe`).
    Fix: add `require_settled: bool = True` to `generate_intents` (threaded
    into `_regime_allows` too); the replay call site is the only caller that
    sets `require_settled=False`.
  - Diff plan (Builder-ready, file:line-exact):
    - `live_runner.py`: import `zoneinfo.ZoneInfo` (after :14); module
      constants `_ET`/`SETTLE_HOUR_ET=16`/`SETTLE_MINUTE_ET=15` (after :37);
      new `_is_forming(last_bar, as_of) -> bool` sibling to `_is_stale`,
      appended at EOF (fail-closed: any tz resolution error → `True`).
      `generate_intents` signature gets `require_settled: bool = True`
      (:179-184). Exit-loop hold mirrors the stale-hold at :214-216;
      entry-loop skip mirrors the stale-skip at :325-327 (inserted before
      the `:329` price read, so a forming price never lands in `prices`).
      `_regime_allows` (:364-389) gets `require_settled` threaded through
      its one call site (:317) and an `elif` forming-branch after its
      existing stale branch (:387) — same risk-off-via-`regime_data=None`
      pattern.
    - `portfolio_backtest.py:279`: `generate_intents(..., require_settled=False)`
      + a one-line comment explaining why. The only required `src/` change
      outside `live_runner.py`.
    - `signals.py`: **no changes** (confirmed) — guard is decision-layer
      only; signal evaluators stay pure/deterministic over their inputs.
    - `cli.py`: **no changes** (confirmed) — call-graph grep shows
      `live_sweep`/`live_check_stops` → `_sweep_stops` → `check_stops` et
      al., never `generate_intents`. The only 4 callers in the tree:
      `live_runner.py:179` (def), `portfolio_backtest.py:279`, and
      `cli.py:1006,1056` (`live signals`/`live run` — both correctly
      default to `require_settled=True`).
    - Preflight (`PreflightReport`/`preflight()` in `live_runner.py`,
      :556-659): new `forming_symbols: list[str]` field (soft WARN per RFC
      §8 decision #3) — symbol stays in `fresh` (existing no-fresh-data
      ABORT stays unaffected) and is *also* added to `forming`; one
      `warnings.append(...)` summarizing the list. `ok`/`reasons` untouched
      — never hard-fails. Regime preflight (:638-645) intentionally left
      alone — already produces an equivalent warning, and `_regime_allows`
      independently forces risk-off at runtime; a second WARN would be
      redundant noise.
    - `docs/AUTONOMOUS_LIVE_ROUTINE.md`: rewrite the "Picking the time"
      paragraph (currently ~:92-109) to state the guard now makes
      correctness time-independent; flip its "not yet done" sentence about
      the guard to past tense. **Schedule recommendation: keep 3:45pm ET**
      — no observed real-world chain runtimes exist to responsibly justify
      a later number (inventing one would be false precision), and the
      guard means the time no longer affects correctness, only how often a
      pre-close run suppresses a trade.
  - Risks flagged for Tester/Validator: replay-regression needs a positive
    test (≥1 intent fires over a multi-day replay window); tz-semantics
    test must cover both a winter (05:00 UTC) and summer (04:00 UTC) stored
    bar, not just one season; existing suite's `AS_OF = LAST_BAR + 3 days`
    idiom stays settled (green) but new tests must not perturb that shared
    fixture; half-day blind spot accepted as-is (skip, never mis-trade) —
    no code change, just a `tasks/lessons.md` note at closeout.
  - Full plan (verbatim) handed to Builder in C-2's dispatch prompt.
- Orchestrator: independently re-confirmed the replay-regression claim via
  a direct grep of `portfolio_backtest.py` (matches Planner's citation
  exactly) before baking it into the Builder's mandatory instructions.
  Dispatching Builder (C-2) now with the Planner's full plan embedded.
- Builder (C-2) done. Implemented the Planner's plan exactly, zero drift.
  Orchestrator reviewed all three diffs directly (`live_runner.py`,
  `portfolio_backtest.py`, `docs/AUTONOMOUS_LIVE_ROUTINE.md`) before
  committing — `8f92fc4` (implementation) + `c357bc5` (tracking). Dispatched
  Tester (C-3).
- Tester (C-3) was killed mid-run by the user after its first pass. Before
  stopping, it had already found a real gap: the existing
  `test_portfolio_backtest.py` fixtures build `as_of`/bar timestamps from a
  naive-midnight `day(i)` helper, which `_is_forming` always reads as
  settled regardless of the `require_settled` argument — so
  `test_no_lookahead_entry_fires_on_signal_day` (the test the Planner/Builder
  cited as adequate replay-regression coverage) never actually exercises the
  `require_settled=False` opt-out at `portfolio_backtest.py:283`. Orchestrator
  asked the user how to proceed (resume / restart / pause); user chose
  resume. Resumed the same agent via `SendMessage` with instructions to close
  the gap (not just document it) and finish the rest of the RFC §7 plan.
- Tester (C-3) done on resume. Added `tests/test_settled_bar_guard.py`
  (RFC §7 parts 1-4: unit table with hand-derived winter+summer UTC↔ET
  arithmetic for every boundary case, `generate_intents` entry/exit/regime
  integration, sweep-exemption regression via `inspect.getsource` call-graph
  checks + a behavioral contrast test, naive-`.date()` tz-bug guard) and
  `TestSettledBarGuardReplayWiring` in `tests/test_portfolio_backtest.py`
  (closes the replay-regression gap found above, winter+summer, using the
  real ET-midnight-as-naive-UTC stored-bar convention rather than the
  shared fixture's naive-midnight idiom). Part 5 (non-vacuous proof) executed
  two live mutations against `src/` and restored both, with literal pytest
  output captured for each: (1) `_is_forming` hardcoded to `return False` →
  3/6 integration tests fail as predicted, 3 unaffected as predicted;
  (2) `portfolio_backtest.py:283`'s `require_settled=False` flipped to
  `True` → both new replay tests fail while all 12 pre-existing tests stay
  green (proving the old suite really was blind to this). Full suite:
  795 passed, 1 skipped, 10 deselected. ruff + ruff-format clean.
  Orchestrator independently re-ran mutation (2) from scratch — same
  2-fail/12-pass split, confirmed `git diff --stat` empty after restore —
  before accepting the report and committing (`aa62a86`). Dispatching
  Validator (C-4) next.
