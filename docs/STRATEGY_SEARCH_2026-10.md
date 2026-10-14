# Strategy search 2026-10: a bot that beats the market (pre-registration)

This was written and committed **before any result was computed**. Its purpose is to stop the
search from being tuned to the answer. The design decisions were made by the user in a
one-question-at-a-time Q&A on 2026-10-14, following `docs/PROFITABILITY_REVIEW_2026-10.md`.

## Decisions (user)

| Question | Decision |
|---|---|
| What "beat the market" means | **Higher return, similar risk.** Beat QQQ's CAGR **and** Sharpe, with max drawdown ≤ **1.25×** QQQ's. |
| Stock pool | **The current 45-name universe plus the NASDAQ-100.** In backtests the pool is point-in-time: NASDAQ-100 members as of each date, plus each of the 45 names only from the date it was added to `config/universe.json`. |
| Trade cadence | **Weekly rebalance.** |
| Protection between rebalances | **Portfolio-level only.** No per-stock stops. Go to cash when the market trend breaks, with the account kill switch as backstop. |
| Plan | Approved. Nothing touches the live account until the paper-shadow results are in and the user signs off. |

## Data

- **NASDAQ-100 membership:** quarterly snapshots of the English Wikipedia *Nasdaq-100* components table, taken from page revisions dated at or before each quarter start, 2015-Q1 → 2026-Q4.
  - Approximation: a membership change shows up at the next quarterly snapshot, not on its exact effective date.
  - Tickers are mapped to their current trading symbol where renamed (e.g. FB→META).
  - Members whose prices can't be fetched (acquired or delisted) are listed in the data file. That is residual survivorship bias, and it favours the strategy, so a fail here is conservative.
- **The 45 names' add dates** come from the first commit adding each symbol to `config/universe.json`.
- **Prices:** Yahoo daily OHLC, split-adjusted, 2015-01 → 2026-10-13.

## Strategy family: weekly cross-sectional momentum rotation

| Element | Rule |
|---|---|
| Signal | Friday close, or the last session of the week |
| Execution | Next session's open |
| Pool | Point-in-time pool on the signal date. Names need ≥ 1 year of price history. |
| Momentum score | Total return from `L` months ago to 1 month ago (the most recent month is skipped) |
| Holdings | The top `N` by score, equal weight, rebalanced weekly. Names staying in the top `N` are not traded except to rebalance. |
| Trend exit | If QQQ's close is ≤ its 200-day SMA on the signal date, hold cash until a signal date where it is above again |
| Costs | 10 bps per unit of turnover |
| Leverage | None; shorts none; fractional shares allowed |

## Variants: exactly four, fixed now

| Variant | Lookback `L` | Holdings `N` |
|---|---|---|
| M6-T5 | 6 months | 5 |
| M6-T10 | 6 months | 10 |
| M12-T5 | 12 months | 5 |
| M12-T10 | 12 months | 10 |

No other variant gets run and reported as a result. Exploratory runs can only be done *after* this test, and they must be labeled as exploratory.

## Windows and selection rule

1. **Design window: 2016-01-04 → 2021-12-31.** Pick the variant with the highest Sharpe *among those that pass the criterion against QQQ in the design window*. If none pass, the family is **REJECTED** and the holdout is never run.
2. **Holdout window: 2022-01-03 → 2026-10-13.** Run once, for the selected variant only. It is **ADOPTED for paper** iff, in the holdout:
   - CAGR > QQQ's CAGR, **and**
   - Sharpe > QQQ's Sharpe, **and**
   - max drawdown ≤ 1.25 × QQQ's max drawdown, **and**
   - re-run without its top-2 P&L contributors, CAGR is still > QQQ's.

   Otherwise it is **REJECTED**.
3. All four variants' design-window numbers and the holdout result are reported. The full 2016→2026 numbers are reported for context only.

## After the test

- **ADOPTED:** it runs in the paper shadow for ≥ 8 weeks, compared against QQQ and against its own replay. The user then signs off before any live change.
- **REJECTED:** the result is logged in `docs/EXPERIMENT_LOG.md`, and the next family is pre-registered the same way. Candidates are low-volatility, quality and ETF trend.
