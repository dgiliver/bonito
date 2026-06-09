---
name: robinhood-trade
description: Run the daily Robinhood trading cycle or the intraday stop monitor on the configured universe. Paper mode by default; live mode places real orders via the Robinhood MCP on the Agentic account.
allowed-tools: Read, Bash, Grep, ToolSearch, mcp__Robinhood__*
---

# Robinhood Trade Skill

Autonomous daily/intraday trading on the universe in `config/universe.json`.
Architecture: Bonito code generates `TradeIntent`s deterministically; this
session executes them — against the paper ledger, or via the Robinhood MCP
in live mode. **State lives in the repo** (`livetrade/`), so every run MUST
end with a commit + push or the session's trades are lost.

## Usage

```
/robinhood-trade daily          # Full daily cycle (default)
/robinhood-trade monitor        # One intraday stop-loss sweep
/robinhood-trade status         # Just report account state
```

## Setup (every session)

```bash
[ -d .venv ] || python3.12 -m venv .venv && .venv/bin/pip install -e "." --quiet
git pull origin <current-branch>   # pick up latest ledger state
```

## Daily cycle

0. **Reconcile (MANDATORY in live mode, before anything else)**:
   - `get_equity_positions` for the Agentic account → build
     `{"SYMBOL": quantity}` JSON (or `{}` if flat).
   - `.venv/bin/bonito live reconcile '<positions_json>'`
   - Non-zero exit = drift (e.g. a prior session crashed between placing an
     order and recording the fill). **HARD STOP — do not trade.** Pull the
     truth from `get_equity_orders` (placed_agent=agentic), repair the
     ledger with `bonito live record-fill` using actual fill prices, re-run
     reconcile until green, and report what happened to the user.
1. **Refresh data**: `.venv/bin/bonito live refresh`
   - If Yahoo is blocked ("Host not in allowlist"), STOP and tell the user
     to add `query1.finance.yahoo.com` / `query2.finance.yahoo.com` to the
     environment's network allowlist. Never trade on stale data.
2. **Run the cycle**: `.venv/bin/bonito live run --no-refresh`
   - Paper mode (`mode: "paper"` in universe.json): intents fill into
     `livetrade/paper_ledger.json` automatically. Done — go to step 4.
3. **Live mode only** (`mode: "live"` AND `live_enabled: true`):
   - Resolve the account: `get_accounts` → the account with
     `agentic_allowed: true` (nickname "Agentic"). NEVER trade the default
     margin account.
   - Check `get_portfolio` buying power covers the buy intents.
   - For each intent in the newest `livetrade/intents/*.json`:
     - Sells first, then buys.
     - `review_equity_order` (market, dollar-based for buys, share quantity
       for sells, regular_hours) → sanity-check estimated cost and alerts.
     - `place_equity_order` with a fresh UUID `ref_id` (reuse SAME ref_id
       only when retrying a transport failure).
     - Record: `.venv/bin/bonito live record-fill SYMBOL buy PRICE --dollars N`
       (or `... sell PRICE`) using the actual fill price from the order.
   - Reconcile: `get_equity_positions` must match ledger positions; report
     any mismatch to the user instead of "fixing" it silently.
4. **Report + persist**:
   - `.venv/bin/bonito live status`
   - `git add livetrade/ && git commit -m "chore(livetrade): daily cycle YYYY-MM-DD" && git push`

## Intraday monitor

For each sweep (every ~15 min during 9:30–16:00 ET via /loop):

1. Read open positions from the mode's ledger (`livetrade/paper_ledger.json`
   or `livetrade/live_ledger.json`). None → done.
2. Get current prices: `get_equity_quotes` for those symbols.
3. `.venv/bin/bonito live check-stops '{"TSLA": 412.5, ...}'`
   - Paper mode: add `--execute` to fill exits in the ledger.
   - Live mode: for each emitted exit intent, place the sell via the MCP
     (same review → place → record-fill flow as the daily cycle).
4. If any exits fired: commit + push `livetrade/`.

## Hard rules

- NEVER place an order the intents file doesn't contain.
- NEVER trade on the margin account (••••7982); only the Agentic account.
- NEVER exceed `risk` caps in universe.json; the code enforces them — if a
  number looks wrong, stop and ask, don't override.
- Live mode requires BOTH `mode: "live"` and `live_enabled: true`. Flipping
  those flags requires explicit user sign-off — never do it yourself.
- On any error placing an order: stop the run, report what filled and what
  didn't. Do not retry with modified parameters.
