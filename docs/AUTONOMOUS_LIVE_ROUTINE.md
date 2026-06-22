# Autonomous live trading via Claude Code Routines

This is how the daily cycle runs with **no laptop and no phone** — a
scheduled cloud session that spins itself up, trades, and shuts down.

## What a Routine is

A [Routine](https://code.claude.com/docs/en/routines) is a saved Claude
Code config (a prompt + repositories + connectors + a schedule) that runs
on Anthropic-managed cloud infrastructure. The scheduled trigger creates a
fresh cloud container at the cadence you set, runs the prompt to
completion as a full Claude Code session, and tears the container down.
Nothing of yours needs to be awake.

This answers the two questions directly:

- **"Can it run without my phone/laptop?"** Yes. Routines run in the cloud
  on a schedule; you can be offline.
- **"Can the container be created automatically on a schedule?"** Yes —
  that is exactly what a scheduled trigger does. Minimum interval is one
  hour; times are wall-clock in your zone.

## Why this is the LIVE executor specifically

The paper cycle already runs unattended via GitHub Actions
(`.github/workflows/paper-trading.yml`) because paper needs no broker
credentials. **Actions cannot place real orders** — the Robinhood MCP only
exists inside a Claude session. A Routine *is* a Claude session, so it is
the one mechanism that can run the live cycle autonomously.

That also means: standing up a live Routine removes the last human
checkpoint (you opening a session and saying "go"). It belongs at the
**end of the pre-live checklist** in `tasks/todo.md`, gated on the same
explicit sign-off as flipping `live_enabled`. Do not create the live
Routine until that sign-off.

## Safety preconditions (all required before the live Routine runs)

1. `config/universe.live.json` has `mode: "live"` AND `live_enabled: true`
   (a human sets these; never automated).
2. The pre-live checklist in `tasks/todo.md` is complete — including ≥2
   weeks of `bonito live tracking` reporting OK.
3. Robinhood is connected as a **claude.ai connector** (see Setup), so the
   cloud session can authenticate. A locally-added CLI MCP will NOT carry
   into a Routine.
4. The environment's network access allows Yahoo Finance
   (`query1.finance.yahoo.com`, `query2.finance.yahoo.com`) for the data
   refresh. Robinhood MCP traffic routes through Anthropic and needs no
   domain allowlisting.
5. The ••••8597 cash-only account scoping is **NOT enforced by any code in
   `src/bonito/`** — Bonito's own pipeline never contacts Robinhood at all;
   it only emits intents (`livetrade/intents/*.json`). The Robinhood MCP
   calls happen entirely inside the Claude session/Routine, outside this
   codebase. The only enforcement is (a) Robinhood's own API rejecting the
   margin account for agentic trading (`agentic_allowed: false` on that
   account), and (b) the Routine prompt's own discipline (step 1 below). A
   reviewer must not assume `src/bonito/` guards this boundary.

## The safety chain inside each run

The prompt below is fail-closed at three independent points, none of which
need a human:

- **`bonito live preflight`** aborts on a latched kill switch, a
  `live`/`live_enabled` mismatch, or a total data outage (so a Yahoo
  outage stops the run loudly instead of silently trading on nothing).
- **`bonito live reconcile`** exits non-zero on any drift between the
  ledger and the real Robinhood positions — a prior crash between placing
  an order and recording it halts the new run.
- The prompt places **only** the intents in the generated file, sells
  before buys, and records every fill — and stops on the first order error
  rather than improvising.

Because a Routine runs with no approval prompts, every safeguard lives in
the code and this prompt. That is deliberate, and it is why the preflight
gate and the reconcile gate both fail closed.

## Setup (you do this once, from a LOCAL terminal)

`/schedule` is unavailable inside a cloud session — create the Routine from
your own machine or from [claude.ai/code/routines](https://claude.ai/code/routines).

1. Connect Robinhood as a connector at
   [claude.ai/customize/connectors](https://claude.ai/customize/connectors).
2. From a local Claude Code terminal:
   ```
   /schedule weekdays at 3:45pm ET, run the Bonito live trading cycle
   ```
   Claude will collect the repo, environment, connectors, and the prompt
   (paste the prompt below). Include only the Robinhood connector.
3. Confirm the environment allows the Yahoo domains and has
   `mode: live` + `live_enabled: true` in `config/universe.live.json`.
4. Use **Run now** once while you watch, to confirm the full chain end to
   end, before relying on the schedule.

To validate the *mechanism* with zero financial risk first, point the
Routine at the paper config (`-u config/universe.json`) or keep
`live_enabled: false`: the run will reconcile, preflight, and generate
intents but place nothing. That proves container-on-schedule + connector
auth + the full pipeline before any real order.

## The Routine prompt (self-contained)

```
You are running the Bonito daily live trading cycle on the Robinhood
Agentic cash account, unattended. Follow these steps exactly. If any step
aborts, STOP, commit nothing new, and end the run reporting what happened —
never improvise an order.

Setup:
- `[ -d .venv ] || python3.12 -m venv .venv && .venv/bin/pip install -e "." --quiet`
- `git pull origin <branch>` to get the latest ledger.

1. Resolve the account: Robinhood get_accounts → the one with
   agentic_allowed: true (nickname "Agentic", ••••8597). NEVER the margin
   account (••••7982). Assert ALL THREE of: masked number ends in 8597 AND
   agentic_allowed == true AND nickname == "Agentic". If any check fails,
   STOP immediately, place nothing, and report the mismatch — this is the
   same fail-closed posture as every other step below.
2. Reconcile: get_equity_positions for that account → build
   {"SYMBOL": qty} JSON ({} if flat) → `.venv/bin/bonito live reconcile
   '<json>' -u config/universe.live.json`. Non-zero exit = drift: STOP,
   report, do not trade.
3. Refresh data: `.venv/bin/bonito live refresh -u config/universe.live.json`.
4. Preflight: `.venv/bin/bonito live preflight -u config/universe.live.json`.
   Non-zero exit = ABORT: STOP and report (kill switch, data outage, or
   flag mismatch). Do not trade.
5. Generate intents: `.venv/bin/bonito live run --no-refresh
   -u config/universe.live.json`. This writes livetrade/intents/*.json and
   places NOTHING itself.
6. Execute ONLY the intents in the newest intents file, sells before buys:
   for each, Robinhood review_equity_order then place_equity_order (fresh
   UUID ref_id), then `.venv/bin/bonito live record-fill SYMBOL SIDE PRICE
   --dollars N --broker-order-id ID` (or `... SIDE PRICE --broker-order-id ID`
   for sells) with the ACTUAL fill price and the order id from
   place_equity_order's response (or get_equity_orders if not returned
   directly). On any order error: STOP, report what filled and what didn't,
   do not retry.
7. Reconcile again (get_equity_positions vs ledger). Report any mismatch;
   do not silently fix it.
8. Persist: `.venv/bin/bonito live status -u config/universe.live.json`,
   then `git add livetrade/ && git commit -m "chore(livetrade): live cycle
   $(date -u +%F)" && git push`.

Hard rules: never place an order not in the intents file; never trade the
margin account; never run `bonito live resume`; never edit mode or
live_enabled. If the kill switch is latched, report and stop.
```

## Intraday stops under a Routine

A Routine can't poll every 15 minutes (one-hour minimum interval), so
intraday protection should NOT depend on a sweep Routine. Use **broker-side
GTC stop orders** instead (pre-live checklist item): the daily Routine
places a stop order at Robinhood after each entry and cancel/replaces to
ratchet trailing stops. Robinhood enforces those 24/7 with no session
running at all — strictly better than a polling sweep, and it keeps the
daily Routine within the run cap.

## Your footprint once this is live

- **Daily:** nothing. The Routine runs in the cloud.
- **Occasional:** read a GitHub issue when the weekly research adopts/rejects
  a change, or when a run reports an abort (drift, halt, data outage).
- **Human-only, never automated:** the `mode`/`live_enabled` flags, risk
  caps, and `bonito live resume` after a kill-switch halt.
