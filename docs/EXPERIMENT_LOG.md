# Experiment Log — live pipeline optimization

Canonical record of account-level experiments. **Check this before proposing
an optimization** — rejected ideas come back looking clever every time the
attribution tables are re-read.

## Protocol

Every candidate change is judged by `bonito live backtest-account` (the
replay of the real pipeline code), never by raw P&L attribution:

1. **Pre-register the criterion before running**: adopt only if the TRAIN
   window improves AND the holdout does not degrade.
2. One shot per idea — no variant shopping after seeing results. A sign
   flip ("momentum failed, try inverse momentum!") is a new idea that needs
   its own independent justification, not a free retry.
3. Structural changes (capital allocation, diversification) are held to the
   same bar but are more trustworthy when the improvement is monotone
   across a parameter family (e.g. 5→6→7→8 slots).
4. Compare against the last saved result in `livetrade/research/`.

## Adopted

| Date | Change | Evidence |
|------|--------|----------|
| 2026-06-12 | `position_pct_equity` sizing (slots scale with equity instead of fixed $1k) | Fixed slots left 61% of equity idle by 2026; +156%→+196% with nothing else changed |
| 2026-06-12 | 8 slots × 12.5% equity, $2.5k/position cap (was 5 × 20%, $1k cap) | $14,823→$26,024 (+420.5%), Sharpe 1.36→1.55, max DD 21.6%. Monotone gain 5→6→7→8; train +83.4% AND holdout +181.5% both improve. 8 slots chosen over 7 for DD headroom (21.6% vs 23.7% against the 25% kill switch) at equal Sharpe |
| 2026-06-12 | Drop NVDA from the universe | Per-symbol research: all 144 grid candidates lose money in 2025–26 holdout (-19% to -40%); live attribution -$333 over 37 trades, 27 stop-outs |
| 2026-06-12 | IREN per-symbol strategy `iren_ema8-21_rsi68_atr1.5_tpnone` | Holdout Sharpe 2.98, +1269%, DD 24% OOS. **Caveat**: bypassed the train DD gate (57% in 2022-24) — justified only because a capped slot limits account exposure to ~12.5% |
| 2026-06-12 | AAPL/GOOGL per-symbol assignments via `research clusters --per-symbol` | Both passed holdout kill filter + profitable-holdout gate; account replay confirmed (AAPL -$254→-$36, GOOGL -$32→+$109) |

## Rejected

| Date | Idea | Why it looked good | Why it failed |
|------|------|--------------------|----------------|
| 2026-06-12 | Remove the EMA cross-below exit rule | Exit arm shows -$1,684 raw P&L over 34 trades | Account replay DEGRADES without it (+191.9% vs +196.5%). Attribution misses opportunity cost: those exits free capital for better re-entries |
| 2026-06-12 | Momentum-ranked entry competition (21-day momentum decides who gets slots instead of universe list order) | Train improved +83.4%→+121.8% | Holdout collapsed to **-20.1%** and the 25% kill switch fired (DD 26.3%). Ranking by momentum buys the most extended signals and concentrates into correlated high-beta names. Classic overfit: better in-sample, fatal out-of-sample |
| 2026-06-12 | Per-symbol grid winner for MSFT | Passed the kill filter on holdout | Holdout return was **-10.1%** — the kill filter checks structure (trades/DD/Sharpe ceiling), not profitability. Led to the profitable-holdout gate now in `cluster_research.py` |

## Standing conclusions

- **Universe list order for entry competition is a tested decision** — do
  not "fix" it without new evidence (see momentum rejection above).
- **The exit rule stays** even though its raw P&L is negative.
- **Kill-filter PASS ≠ deployable**: assignments additionally require
  positive holdout return (enforced in code since 2026-06-12).
- Full replay artifacts: `livetrade/research/account_backtest_*.json`;
  research reports: `livetrade/research/cluster_report_*.json`.
