# Lessons

Patterns extracted from corrections and surprises. Review at session start
when working on the corresponding area.

## Trading optimization (2026-06-12)

- **Never judge a pipeline change by raw P&L attribution.** The exit rule
  showed -$1,684 attributed P&L but removing it made the account worse —
  attribution can't see opportunity cost (capital freed for re-entries).
  The account replay (`bonito live backtest-account`) is the only judge.
- **Pre-register the adoption criterion BEFORE running an experiment**
  (train improves AND holdout doesn't degrade), and no variant shopping
  after seeing results. This discipline rejected momentum ranking, which
  improved train +38pts while collapsing holdout to -20% — the exact trap
  the criterion exists to catch.
- **A train-only improvement is evidence AGAINST a signal-level change,
  not for it.** Structural changes (diversification, sizing) tend to
  improve both windows; signal tweaks that only help train are fitting
  the path.
- **Kill-filter PASS does not mean deployable** — it checks structure, not
  profitability. MSFT's grid winner passed with a -10.1% holdout. Gates
  that exist to kill bad strategies don't automatically certify good ones.
- Log every adopted/rejected experiment in `docs/EXPERIMENT_LOG.md` so
  rejected ideas don't get re-proposed from re-reading attribution tables.

## Paper-vs-replay tracking fidelity (2026-06-22)

- **An early-window `bonito live tracking` WARN is usually an expected
  artifact, not a bug — don't re-investigate from scratch.** Two structural
  causes, both confirmed by a 4-role investigation (see
  `tasks/arm_fill_gap_coordination.md`):
  - *Intraday-entry vs close-based replay.* The live/paper pipeline can fill
    entries from intraday quotes, but the replay only enters on a CONFIRMED
    CLOSE signal — often a bar later. During a fast move that produces large,
    SAME-signed fill-bps gaps on both legs (ARM was −944/−909 bps because the
    replay entered one bar into a rally and rode it up). Same-signed,
    stable-across-reports fill gaps are structural, NOT random slippage.
  - *Config drift.* The replay runs the CURRENT universe config over a window
    whose early fills were generated under an OLDER config. Tell: the equity
    gap grows across successive weekly reports while the per-fill bps stay
    frozen.
- **Diagnostic tells (check these before opening the code):** fill bps
  identical across successive weekly reports ⇒ structural, not execution
  noise; equity gap widening while fill bps frozen ⇒ config drift; an
  *unmatched* fill ⇒ the close-based replay declined an entry the pipeline
  took, not a matcher error.
- **The one real signal worth a decision:** the pipeline can OPEN a position
  from an intraday quote on a bar whose CLOSE fails the entry rule — ORCL was
  bought intraday at 204.16 on 06-10, but that bar closed 201.26, below
  ema_slow 203.02, so the close-based replay (and the weekly research gate
  that trusts it) never takes that trade. Whether to restrict entries to
  confirmed closes, exclude such fills from tracking, or accept it is a USER
  policy call — never silently "fix" it.
- **Matcher invariants now under test**
  (`tests/test_tracking.py::TestMatchFills`): `match_fills` pairs
  same-(symbol,side) fills only within ±1 day (`MATCH_TOLERANCE_DAYS`);
  `delta_bps = (paper−replay)/replay×1e4` (paper below replay ⇒ negative); a
  fill with no in-tolerance counterpart is a decision divergence. Locked so a
  refactor can't silently move the boundary.

## Settled-vs-forming bar guard (2026-06-25)

- **A shared test fixture's timestamp convention can silently make a new
  flag's default path untested.** `tests/test_portfolio_backtest.py`'s
  existing fixtures build `as_of` from a naive-midnight `day(i)` helper;
  naive midnight always converts to several hours into the *previous* ET
  evening, so a settled-bar check is `False` (settled) for every `d` it
  produces, regardless of the new `require_settled` flag's value. All 12
  pre-existing replay tests passed identically whether the guard's
  `require_settled=False` opt-out was wired correctly or missing entirely —
  caught only because the Tester independently checked whether the existing
  "this already covers it" claim actually held, instead of trusting it.
  Lesson: when a new parameter is supposed to be load-bearing for an
  existing test, prove it (mutate the call site, confirm the test fails)
  rather than inferring coverage from "the test still passes."
- **Accepted residual: half-day sessions (~9/yr, e.g. day before
  Thanksgiving) close at 13:00 ET, not 16:00.** The guard's D1 heuristic
  (`_is_forming`) treats every session as closing at 16:00 ET, so on a
  half-day it reads an already-settled bar as forming until 16:15 ET
  regardless. Accepted as-is per RFC §5.1 / §8 decision #1 — the failure
  mode is always "skip a trade," never "act on a stale or wrong price," and
  correctly detecting half-days would require a market-calendar dependency
  the user explicitly ruled out (detection = D1, stdlib `zoneinfo` only, no
  new dependency). Revisit only if half-day skips show up as a recurring
  `bonito live tracking` WARN pattern.
