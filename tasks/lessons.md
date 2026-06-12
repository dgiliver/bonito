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
