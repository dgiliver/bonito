# Strategy search 2026-10b: trend-timed QQQ leverage (pre-registration)

Committed **before any result was computed**. This is the user's choice of next family, made in the Q&A on 2026-10-14 after `docs/STRATEGY_SEARCH_2026-10.md` was rejected at its design window.

## Prior information (disclosed)

- **What I have already seen:**
  - Unlevered QQQ held only while SPY > SMA200 made 16.6% CAGR, Sharpe 1.02, max drawdown 23.9%. Plain QQQ made 21.2% / 0.98 / 35.1% over 2016-06 → 2026-10 (profitability review, §B).
  - The rejected momentum family's 2016–2021 numbers.
- **What I have not seen:** any result for a leveraged-ETF strategy.
- **The holdout is untouched.** No strategy in either search has been evaluated on 2022-01-03 → 2026-10-13.

## Criterion (unchanged, user decision)

Beat QQQ on CAGR **and** Sharpe, with max drawdown ≤ **1.25×** QQQ's, measured on the same dates.

## Instruments and rules

| Element | Rule |
|---|---|
| Instruments | QQQ, QLD (2× daily NASDAQ-100) and TQQQ (3×). Yahoo split-adjusted daily OHLC, so ETF fees and daily-reset decay are already in the prices. All three are unlevered purchases in a cash account; no margin. |
| Signal | Last session of each ISO week, using that day's close: QQQ close vs its own 200-session SMA, computed on QQQ's real sessions |
| Execution | Next session's open; weights rebalanced exactly to target |
| Costs | 10 bps per unit of traded notional |
| Engine | Reuses the reviewed rotation conventions: next-open fills, session calendar from QQQ, fee attribution |

## Variants: exactly four, fixed now

| Variant | Above SMA200 | At or below SMA200 |
|---|---|---|
| L2-QQQ | 100% QLD | 100% QQQ |
| L2-CASH | 100% QLD | cash |
| L15-CASH | 50% QLD + 50% QQQ (≈1.5×) | cash |
| L3-CASH | 100% TQQQ | cash |

## Windows and selection

1. **Design window: 2016-01-04 → 2021-12-31.**
   - A variant **passes** only if it meets the criterion against QQQ, **and** still meets it with the SMA period at 150 **and** at 250. That robustness check means a pass can't depend on a lucky lookback.
   - Among passing variants, the highest design-window Sharpe at SMA200 is selected.
   - If none pass, the family is **REJECTED**, the holdout is not run, and it stays untouched.
2. **Holdout: 2022-01-03 → 2026-10-13.** One run of the selected variant at SMA200.
   - **ADOPTED for paper** iff it beats QQQ on CAGR and Sharpe with drawdown ≤ 1.25× QQQ's.
   - Otherwise **REJECTED**.
   - The stock-level "ex-top-2" check doesn't apply to a three-ETF strategy. The SMA-robustness rule in step 1 replaces it.
3. One-shot enforcement, as before: a `--prepare` (data-only) phase, then `--run`, which refuses to overwrite and records the git SHA, the dirty-tree flag and a data fingerprint.

## Known risks (stated up front)

- Leveraged ETFs reset daily. In choppy markets, decay can make them underperform 2× or 3× the index.
- A gap down larger than ~33% in one day could wipe out TQQQ, and ~50% could wipe out QLD. The weekly signal can't react intraday.
- The 2022 bear market is in the holdout. That is exactly why the holdout is the decisive test.

## After the test

- **ADOPTED:** the paper shadow runs for at least 8 weeks, compared against QQQ. The user signs off, and live goes through a reviewed integration (weekly Routine). The intraday stop Routine could then be retired.
- **REJECTED:** it is logged, and the remaining options go back to the user.
