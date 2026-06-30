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

   **Picking the time — a real tradeoff, not a free choice.** The live cycle
   *must* run during regular hours: Robinhood fractional/dollar orders only
   fill in RTH, so the after-close pattern the paper GitHub Action uses
   (22:30 UTC, when the daily bar is settled) is NOT available here — copying
   it would place orders that never fill. Every minute before the 4pm ET
   close, `bonito live refresh` still pulls a still-*forming* daily bar from
   Yahoo (last trade as the "close"). But `bonito live run` now guards every
   entry/exit with `_is_forming` (the settled-bar guard): on a forming bar it
   skips entries and holds exits rather than acting on an unsettled price.
   Pre-close runs are correct by construction — at worst they no-op a symbol
   whose settled signal would have fired, never trade a wrong price. Net: the
   schedule no longer affects correctness, only opportunity — run too early
   and the guard suppresses that day's trades (picked up next session or a
   later run); run too late and an order risks slipping past 4pm. 3:45pm ET
   keeps ~15 min of headroom while staying in RTH, intentionally biased
   toward "miss a trade > mis-trade." The settled-bar guard is now
   IMPLEMENTED; see `tasks/arm_fill_gap_coordination.md` Decision #3 and
   `docs/RFC_SETTLED_BAR_GUARD.md`.
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
   '<json>' -u config/universe.live.json`. Exit 1 = FATAL drift (>0.5% of a
   position's shares, or a position in one side but not the other): STOP,
   report, do not trade. Exit 0 with a "sub-tolerance drift" warning is fine
   to proceed — the 0.5% gate absorbs fractional-rounding noise. The drift
   gate blocks new entries only; it never blocks an exit.
3. Refresh data: `.venv/bin/bonito live refresh -u config/universe.live.json`.
4. Preflight: `.venv/bin/bonito live preflight -u config/universe.live.json`.
   Non-zero exit = ABORT: STOP and report (kill switch, data outage, or
   flag mismatch). Do not trade.
5. Generate intents: `.venv/bin/bonito live run --no-refresh
   -u config/universe.live.json`. This writes livetrade/intents/*.json and
   places NOTHING itself.
6. Execute ONLY the intents in the newest intents file, sells before buys:
   for each, Robinhood review_equity_order then place_equity_order (fresh
   UUID ref_id). After the order resolves, read its ACTUAL filled quantity
   and price (from place_equity_order's response, or get_equity_orders), then
   record it:
   - Filled (including a PARTIAL fill): `.venv/bin/bonito live record-fill
     SYMBOL SIDE PRICE --shares <ACTUAL filled quantity> --broker-order-id ID
     -u config/universe.live.json`. Use the broker's actual share count via
     `--shares` (NOT `--dollars`): a partial fill or fractional rounding makes
     dollars/price wrong, and `--shares` makes the ledger match the broker
     exactly, so step 7's reconcile stays clean.
   - Rejected / did NOT fill: `.venv/bin/bonito live record-fill SYMBOL SIDE
     PRICE --no-fill -u config/universe.live.json` (PRICE = the intended/last
     price; no order id needed). Logs the divergence as an explicit no-fill
     instead of silently assuming the position exists.
   On any order error: STOP, report what filled and what didn't, do not retry.
7. Reconcile again (get_equity_positions vs ledger). Report any FATAL
   mismatch; do not silently fix it.
8. Fidelity check (the rehearsal gate): `.venv/bin/bonito live tracking
   -u config/universe.live.json`. Status must be OK. WARN = live fills are
   diverging from the replay beyond the fill-bps band — report it; during the
   rehearsal a WARN is a gate failure to investigate before the next cycle.
9. Persist: `.venv/bin/bonito live status -u config/universe.live.json`,
   then `git add livetrade/ && git commit -m "chore(livetrade): live cycle
   $(date -u +%F)" && git push`.

Hard rules: never place an order not in the intents file; never trade the
margin account; never run `bonito live resume`; never edit mode or
live_enabled. If the kill switch is latched, report and stop.
```

## Rehearsal protocol — the go-live gate

Going live is **graduated, not a binary flip**. The gate (pre-live checklist /
`RFC_LIVE_FIDELITY.md` D5) is **≥2 weeks of green live-vs-replay tracking at
1-share size**, every cycle, before any real size.

**Sizing for the rehearsal (you set this — human-only).** In
`config/universe.live.json`, set risk caps so each position is ~1 share: e.g.
`max_position_usd` to a tiny value (~$30–50 covers 1 share of most universe
names) and leave `position_pct_equity` null so it doesn't override. Blast
radius is then a few dollars per name while the real execution path is proven.

**Per-cycle pass criteria** (the Routine asserts these; any failure stops the
cycle, places nothing further, reports):
- Step 2 reconcile → exit 0, no FATAL drift.
- Step 4 preflight → OK (no kill switch / flag mismatch / data outage).
- Step 8 `live tracking` → status **OK** (live fills within the fill-bps band
  of the replay; no decision divergence beyond tolerance).

**The gate:** run every weekday. **≥2 consecutive weeks where every cycle is
green** (reconcile clean + tracking OK) is the quantitative basis to trust the
live account tracks paper/backtest.

**Then, and only then:** your sign-off → keep `live_enabled: true` and **raise
the risk caps gradually** (e.g. double the cap, watch a few cycles, repeat),
re-checking `live tracking` at each step. The decision logic never changes —
only the size — because the strategy pipeline is shared code and the fidelity
work guarantees the live path matches the replay.

**Dogfood first (zero risk):** create the Routine with `live_enabled: false`
for a day or two. It reconciles, preflights, and generates intents but places
NOTHING — proving container-on-schedule + connector auth + the full chain
before any real order. Flip to `live_enabled: true` at 1-share size once the
dogfood chain is clean.

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
