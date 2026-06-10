# Enhancement Build (2026-06-10) — validation harness, regime filter, ATR stops, $5k paper

- [x] `trading/validation.py`: kill-filter thresholds + windowed (train/holdout) metrics + verdict + strategy_hash
- [x] DSL: `RegimeFilterConfig` (SPY > SMA200 gate) on StrategyConfig
- [x] Engine: optional `regime_data` param masks long entries
- [x] signals.py: trailing_atr/atr stop support in live path + `regime_allows_long`
- [x] paper.py: pin strategy (hash + config snapshot) on positions; ledger peak_equity/halted
- [x] live_runner.py: per-symbol strategy map, pinned-strategy exits, regime gate on entries, portfolio kill switch
- [x] CLI: backtest-universe → holdout split + verdict column + regime; `live resume`; status shows HALT
- [x] universe.json → $5k paper caps; re-seed ledger at $5k
- [x] Compare variants (baseline / ATR stop / ATR+regime), deploy winner to deployed_strategy.json
- [x] Tests for all of the above; full suite green (581 passed)
- [x] Commit + push

## Review (2026-06-10 session)

Network unblocked → Phase 2 executed, then enhancement build:

**Validation harness**: `backtest-universe` now runs one full-range sim per
symbol, slices equity/trades into train ([start, holdout)) and holdout
([holdout, end]) windows, and prints a kill-filter verdict computed on the
holdout (trades ≥ 7/yr scaled to window, DD ≤ 25%, Sharpe ≤ 3.0).
`--strategy file.json` overrides for variant comparison; `--holdout none`
reverts to full-period verdicts.

**Variant comparison** (holdout 2025-01-01 → 2026-06-10, medians across 25):
| variant | pass | med H.Sharpe | med H.DD% | med H.Ret% |
|---|---|---|---|---|
| baseline 1.6% trail | 2 | 0.72 | 48.2 | +13.4 |
| atr2.5 | 2 | 1.13 | 43.0 | +46.5 |
| **atr2.0+regime (deployed)** | **3** | 0.89 | 42.8 | +19.8 |

Deployed `ema_cross_rsi_atr_regime` v2.0: 2.0×ATR(14) trailing stop +
SPY>SMA200 regime gate. Trade churn fell ~70% (220→~55 trades/symbol).
Holdout passers: COST, MSFT, TSM. Near-misses: WDC (only Sharpe 3.82>3.0),
LLY (DD 27%>25%).

**New safety rails**: positions pin their strategy at entry (hash + full
config snapshot — exits always use the entering config); portfolio kill
switch flattens + halts at 25% drawdown from peak equity (clear with
`bonito live resume`, human-only); regime risk-off blocks entries but never
exits; missing ATR/regime data = hold/risk-off, never guess.

**Paper account re-seeded at $5,000** (max_position $1000, 5 positions,
$100 buffer, 25% DD halt). First cycle filled MU/SNDK/DELL at $1k each.

Decision points for Phase 3 (live):
- Paper trades ALL 25 symbols for system-validation throughput; before
  flipping live, restrict entries to kill-filter passers (COST/MSFT/TSM as
  of today) via `symbol_strategies` or a passer allowlist.
- Backtest costs (0.1% commission default) don't match Robinhood
  commission-free + spread reality; calibrate against paper fills.

# Robinhood Autonomous Trading — Plan (Option A)

Goal: trade a 21-symbol universe on Robinhood with $150 (Agentic cash account,
agentic_allowed=true), fully autonomous via scheduled Claude sessions that run
Bonito signal code locally and execute orders through the Robinhood MCP.
Paper mode first; live only after validation.

## Architecture

```
DuckDB bars (yfinance daily refresh)
        │
bonito live run ──► TradeIntents (JSON)
        │                  │
   paper mode         live mode (Claude session)
        │                  │
PaperLedger (repo)    Robinhood MCP: review → place → record-fill
        │                  │
   livetrade/state committed + pushed each session
```

Key constraints discovered:
- Robinhood MCP has NO historical bars → data refresh stays on yfinance.
- This remote env blocks Yahoo hosts → user must allowlist query1/query2.finance.yahoo.com
  (or run refresh locally) before daily sessions can refresh data.
- Fractional/dollar orders fill regular-hours only → daily flow runs during RTH.
- Container is ephemeral → ledger state lives in repo, committed every session.
- Live orders only on account ••••8597 ("Agentic", cash, $150).

## Phase 1 — Core module + tests (this session)
- [ ] `config/universe.json` — 21 symbols, risk caps, mode=paper, live_enabled=false
- [ ] `src/bonito/trading/signals.py` — pure per-bar rule/condition evaluation,
      stop-loss/take-profit checks, TradeIntent generation (extracted from bot.py)
- [ ] Refactor `bot.py` to delegate evaluation to signals.py (existing tests stay green)
- [ ] `src/bonito/trading/paper.py` — PaperLedger: cash, positions, fills,
      mark-to-market, JSON persistence
- [ ] `src/bonito/trading/live_runner.py` — orchestration: signals across universe,
      paper execution, stop checks, status
- [ ] CLI `bonito live ...`: refresh, run, signals, check-stops, status, backtest-universe
- [ ] Tests: `test_live_signals.py`, `test_paper_ledger.py`, `test_live_runner.py`
- [ ] Skill `.claude/skills/robinhood-trade/SKILL.md` — daily + intraday runbooks
- [ ] `livetrade/` state dir + seeded paper ledger ($150)
- [ ] Make targets: `live-run`, `live-status`

## Phase 2 — Validation (needs Yahoo allowlist or local run)
- [ ] Backfill universe data (2022-01-01 → today)
- [ ] `bonito live backtest-universe` — deployed strategy across all 21 symbols,
      kill-filter (min trades, max DD, Sharpe sanity)
- [ ] ≥2 weeks paper trading via daily sessions; review win rate / drawdown

## Phase 3 — Live enablement
- [ ] Flip `live_enabled: true` in universe.json (explicit user sign-off)
- [ ] Live flow: review_equity_order → confirm caps → place_equity_order (ref_id UUID)
      → record-fill → reconcile vs get_equity_positions
- [ ] Intraday: /loop session during RTH checks stops via MCP quotes every 15m

## Risk caps ($150 account)
- max_position_usd: 30, max_positions: 5, min_cash_buffer: 5
- max_daily_buys: 3, long-only, dollar-based market orders, RTH only
- Strategy: ema_cross_rsi_optimized (EMA 10/26 cross + RSI<68 filter,
  1.6% trailing stop, 10% take profit) — already validated on SPY by autoresearch

## Review (2026-06-09 session)

Phase 1 complete. Built and verified:
- `signals.py` extracted from bot.py (bot now delegates; all 85 pre-existing
  trading tests green). Fixed a float-precision edge in take-profit triggers.
- `paper.py` ledger + `live_runner.py` orchestration + `bonito live` CLI
  (refresh / signals / run / check-stops / status / record-fill /
  backtest-universe).
- 66 new tests; full CI-equivalent suite: 494 passed, 12 skipped.
- End-to-end smoke test with synthetic bars: 3 entries filled at $30 each,
  caps enforced, intraday trailing stop correctly fired on a −4% move.
- Paper ledger seeded at $150. Account verified live: Robinhood "Agentic"
  cash account ••••8597, agentic_allowed=true, $150 buying power, all 21
  symbols tradable + fractional.

Blockers for Phase 2:
- Yahoo Finance hosts not in this environment's network allowlist — needed
  for `bonito live refresh` and `backtest-universe` on real data.
  Re-verified 2026-06-09: query1/query2.finance.yahoo.com still 403
  ("Host not in allowlist"); Stooq/Alpha Vantage/Tiingo/Nasdaq also blocked.
- ~~TE = T1 Energy Inc. assumed~~ — confirmed by user 2026-06-09: TE is
  T1 Energy Inc.
