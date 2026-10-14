# Why we're not beating the market — review and action plan (2026-10-13)

## Bottom line

The live account is down **12.4%** ($150 → $131.42, 07-15 → 10-13). Over the same window SPY is up **3.2%** and QQQ **3.1%**.

The cause is **the strategy, not the plumbing**. Execution matches the replay trade for trade, but:

- **The live window:** the strategy loses money in this market, the same way in the replay and in the paper shadow.
- **Over 10 years:** on a stock list chosen without hindsight, the strategy makes about two thirds of SPY's return.

The strong backtests (+559% since 2022) came almost entirely from a **stock list picked in hindsight**, not from the entry and exit timing.

No setting of the current strategy (stop width, take-profit) fixes this. Becoming profitable *relative to the market* needs:

1. An honest scoreboard.
2. A different source of edge, tested without hindsight.
3. A cheap default, the index itself, for whenever no candidate clears that bar.

## Evidence

### 1. Out of sample, the strategy loses: live, paper and replay agree

| Source, live window | Return | SPY |
|---|---|---|
| Live account (07-15 → 10-13) | **−12.4%** | +3.2% |
| Account replay of the same strategy and window ($150 config) | −7.1% | +3.4% |
| Paper shadow since its 09-23 resume | −7.6% | +0.7% |
| Holding the names we actually traded | +5.8% | |
| Holding all 45 universe names, equal weight | +1.6% | |

Live trading:

- **Trades:** 55 round trips, 31% win rate, profit factor 0.52, −$19.52 realized.
- **Mean per trade:** −1.97% (t = −1.84).
- **Breakeven:** the average win is +8.0% and the average loss −6.4%, so breakeven needs a 45% win rate.

### 2. The mechanism: trailing stops whipsaw high-beta names

| Exit type, live | Trades | Wins | P&L | Avg return |
|---|---|---|---|---|
| Intraday stop loss (2×ATR trailing) | 36 (65%) | 2 | **−$38.65** | −6.5% |
| Take profit (+10%) | 12 | 12 | +$20.56 | +10.6% |
| Signal exit / other | 7 | 3 | −$1.43 | |

After a stop-out, the stock was higher than our exit price **5 sessions later in 20 of 27 cases**. It averaged +4.3% against SPY's +1.3%.

We re-bought the same name after a stop 9 times, paying for the round trip twice. The replay shows the same pattern in the same window: 49 stops at a 6% win rate.

### 3. Execution is not the gap

- **Stop exits:** −6.05% live vs −6.04% in the replay.
- **Take-profit exits:** +10.56% vs +10.15%.

The remaining ~5-point live-vs-replay difference is **path divergence**. Only 32 of 55 live entries match a replay entry within ±2 days. That comes from tiny positions, settled-cash timing and occupied slots, and amounts mostly to luck of the path. Live also held fewer positions on average: 6.2 vs 7.3 of 8 slots.

### 4. The backtest edge is hindsight in the stock list

Replay from 2016-06 to 2026-10, with the kill switch off so the strategy itself is measured:

| | CAGR | Sharpe | Max DD |
|---|---|---|---|
| Strategy on the current 45 names | 27.7% | 1.49 | 27% |
| **Just hold those same 45 names** | **45.6%** | 1.38 | 43% |
| QQQ | 21.2% | 0.98 | 35% |
| SPY | 15.3% | 0.89 | 34% |

The 45 names were chosen in 2025–26 from what had already gone up: AI and semiconductor names, 13F copies, user requests. Holding them beat the strategy's timing in 8 of 11 years. Timing only helped in down years (2018, 2022).

The **hindsight-free test** uses the ~29 largest NASDAQ-100 names as of mid-2016, a list fixed before any result was seen. Residual survivorship favours the strategy, so this is conservative.

| 2016-06 → 2026-10 | CAGR | Sharpe | Max DD |
|---|---|---|---|
| **Deployed strategy** | **10.4%** | 0.79 | 18% |
| Hold the same names | 19.7% | 1.01 | 30% |
| QQQ | 21.2% | 0.98 | 35% |
| SPY | 15.3% | 0.89 | 34% |

Every stop and take-profit variant tried (no stop, no take-profit, neither, 3×ATR without take-profit) also trails SPY on this universe, at 10.5–14.1% CAGR. **The timing layer costs return.** Its only benefit is a smaller drawdown.

Related: the 25% kill switch sits *inside* this strategy's normal drawdown (24–37% depending on settings). It tripped in the 10-year replay and in the paper shadow in August. That is a risk-configuration mismatch, not a safety success.

### 5. Parameter sweep on the 45-name universe (exploratory, not adoption decisions)

| Variant | 10y CAGR | 2022+ CAGR | Live window | Live stops |
|---|---|---|---|---|
| Baseline 2×ATR, TP 10% | 27.7% | 46.5% | −7.0% | 49 |
| 3×ATR | 26.6% | 38.5% | −5.1% | 22 |
| 4×ATR | 27.6% | 42.1% | **−0.7%** | 5 |
| No stop | 27.2% | 43.5% | −2.0% | 0 |
| No TP | 27.9% | 49.3% | −9.4% | 48 |
| No stop, no TP | 42.1% | 76.2% | −9.2% | 0 |

Wider stops lose less in the live window, which is consistent with the whipsaw diagnosis. No variant changes the hindsight-free conclusion. "No stop, no TP" scores best on this universe only because it approaches buy-and-hold of hindsight winners.

### 6. One promising but unproven direction: monthly momentum rotation

This was a one-shot test with textbook parameters fixed in advance: 12-1 month momentum, top 5, equal weight, monthly rebalance, 10 bps per unit of turnover. It ran on the same hindsight-free 2016 list.

| 2016-06 → 2026-10 | CAGR | Sharpe | Max DD |
|---|---|---|---|
| Momentum, all 29 names | **33.2%** | 1.14 | 37% |
| Momentum, excluding NVDA and TSLA | 22.0% | 0.93 | 31% |
| Momentum, excluding NVDA, TSLA, AVGO, NFLX | 13.0% | 0.65 | 33% |
| QQQ | 21.1% | 0.97 | 35% |

The edge is concentration in a few mega-winners. Whether NVDA and TSLA belong in a "mid-2016" list is exactly the hindsight question. It is **a candidate for a proper point-in-time test** (real historical constituents, including delisted names), not a result. Adding the SPY > SMA200 gate made it worse: 19.1% CAGR.

### 7. Why live trading can't find the edge for us

Per-trade returns have a standard deviation of about 8%. Telling a realistic +1% per-trade edge apart from zero needs about 250 trades, which is **~14 months** at the current pace. A +0.5% edge needs about 1,000 trades, roughly 4.5 years.

Live trading can confirm there's no gross failure; it cannot *discover* edge. Discovery has to happen in hindsight-free tests.

### What this is *not*

- **Not execution or slippage:** see section 3.
- **Not the reconcile or pending-order incidents:** they cost coverage, not returns.
- **Not settlement friction:** it capped 2 of 16 entries after the settled-cash fix.
- **Not commissions:** there are none, and fractional spreads are negligible at $16 positions.
- **Not regime (SPY above or below its 200-day):** SPY was above it all window. The SMA50 gate experiment also showed regime filtering doesn't explain the live losses.

## Progress

| Item | Status |
|---|---|
| 3. Market-relative scoreboard | **Done (2026-10-14).** `live status`, `live tracking` and `live performance` now report the account against SPY, QQQ and hold-universe (equal-weight hold of the universe's own symbols). This is report-only: it never changes the tracking status, never gates trading, and benchmark download failures can't fail `live refresh`. |
| 4. Hindsight-free evaluation | **Partly done.** `bonito research benchmark` grades a universe+strategy against the criterion below, with the kill switch off by default. `config/research/hindsight_free_2016.json` is the fixed mid-2016 list. It reproduces section 4 exactly: DOES_NOT_BEAT, failing 5 of 6 checks (only drawdown passes). **Still to do:** true point-in-time index constituents, including delisted names. |
| 5. Research adoption gate | **Not yet, deliberately.** Gating weekly research on beating QQQ only means something once point-in-time data exists. On the hand-picked universe, "hold the universe" beats every timing variant by construction. |

Run the harness with `bonito research benchmark -u config/research/hindsight_free_2016.json --ingest --start 2016-06-01`. It saves a JSON report to `livetrade/research/benchmark_eval_*.json`.

## Action plan

Human-only controls (`mode`, `live_enabled`, risk caps, `strategies/*.json`, universe composition) are marked **[you]**.

### Phase 0: stop the bleeding (this week)

1. **[you] Pause new live entries; keep exits running.**
   - **How:** set `"entry_allowlist": []` in `config/universe.live.json`. An empty allowlist blocks every new entry, while exits, stops and reconcile keep working, so open positions close normally. Use the allowlist, **not** `entry_blocklist`: weekly research overwrites the blocklist every Saturday (`sync_live_config`), but treats the allowlist as human-only and leaves it alone.
   - **Cost of not pausing:** about −$6/month at the current pace, with no evidence it will turn.
   - **Alternative:** keep running it deliberately as a paid live test of the plumbing, and accept the cost.
2. **[you] Decide what the idle cash should do.**
   - **Index core:** holding a broad index ETF is the honest "make money with the market" default, and it is the bar any strategy must beat. It is outside the bot's universe, so it is a manual buy, or a small config/code change if you want the bot to own it.
   - **Cash:** sit in cash until a candidate passes Phase 2.
3. **Re-baseline the scoreboard.** Report live and paper results against SPY, QQQ and "hold the universe" in `live status` and `live tracking`. Today the system grades itself only against its own replay, which is how "tracking OK" coexisted with losing to the market.

### Phase 1: an honest evaluation harness (1–2 weeks)

4. **Point-in-time universe backtests.**
   - Ingest historical NASDAQ-100 / S&P 500 constituents by date, including delisted names where available.
   - Evaluate every candidate on the universe *as it was on each date*.
   - Until then, use fixed-as-of-date lists like `scripts/experiments/2026-10-13_hindsight_free_strategy.py` and say so explicitly.
5. **Change the weekly research adoption gate.**
   - Today it adopts when Sharpe "doesn't degrade" on the hindsight universe, with a holdout drawn from the same period the universe was picked in.
   - Require beating **QQQ and equal-weight hold** on the point-in-time universe, in a time-split holdout.
   - Report kill-switch-off results alongside, so a halt doesn't mask the strategy's real behaviour.
6. **[you] Freeze discretionary universe additions.** Adding names because they recently ran up is the bias. Any future universe should be rule-based, for example the top N by market cap or liquidity as of a date.

### Phase 2: candidates, pre-registered, one shot each (2–4 weeks)

Each candidate gets a criterion fixed before it runs, judged on the Phase 1 harness and logged in `docs/EXPERIMENT_LOG.md` whether adopted or rejected:

> ADOPT iff CAGR **and** Sharpe beat QQQ over the 10-year point-in-time window **and** the 2022+ sub-window, the max drawdown is no worse than 1.25× QQQ's (amended 2026-10-14 by the user's "higher return, similar risk" decision — see `docs/STRATEGY_SEARCH_2026-10.md`), and the result survives excluding the top 2 contributors.

- **A. Monthly cross-sectional momentum rotation.** The most promising lead (section 6). It needs the point-in-time test to rule out the NVDA/TSLA hindsight question.
- **B. Index core plus trend overlay** (QQQ only while SPY > SMA200). Hindsight-free: 16.6% CAGR, 24% max drawdown, against QQQ's 21.2% and 35%. Choose it only if a smaller drawdown is worth about 4.6 points a year to you. It won't beat QQQ on return.
- **C. The current swing strategy with wider stops (4×ATR or none).** Keep it only if A and B fail and you want to keep a swing system running. Expect it to *lose less*, not to beat the market: every variant trails SPY hindsight-free.

### Phase 3: promotion and sizing

7. A winning candidate runs in the **paper shadow first** for at least 8 weeks, compared against SPY/QQQ and its own replay. Then **[you]** sign off before it goes live.
8. **[you] Set the kill switch from the chosen strategy's measured drawdown** (for example 1.25× its 10-year max drawdown). A 25% halt on a strategy whose normal drawdown is 30%+ will latch in ordinary conditions.
9. **[you] Expectations at $131.** Beating the market by 5 points a year is about **$7/year**. The account's value right now is validating the pipeline. Add capital only after a hindsight-free edge has passed Phases 2 and 3.

## Reproduce

| What | How |
|---|---|
| Hindsight-free strategy test | `scripts/experiments/2026-10-13_hindsight_free_strategy.py ingest`, then `… base keep keep` (other variants: `nostop none keep`, `x 3.0 none`) |
| Momentum rotation | `scripts/experiments/2026-10-13_momentum_rotation.py data/hindsight_free/mega.duckdb [EXCLUDE …]` |
| Live trade dissection | live ledger fills, paired into round trips, with exit reasons joined from `livetrade/intents/*.json` |
| Account replays | `portfolio_backtest.backtest_account` on `config/universe.json`, with `max_drawdown_halt` set to 1.0 for diagnostics |

Market data: Yahoo daily bars ingested 2015-01 → 2026-10-13. Broker figures: Robinhood `get_portfolio` and `get_realized_pnl` on 2026-10-13.
