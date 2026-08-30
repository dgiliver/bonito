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
   domain allowlisting. Domain access alone is NOT sufficient if the
   environment's outbound HTTPS goes through a TLS-intercepting proxy (as
   Claude Code cloud environments do) — see the `YF_DISABLE_CURL_CFFI=1`
   prefix on step 5 below; without it, refresh can silently ingest nothing
   while still exiting 0.
5. The ••••8597 cash-only account scoping is **NOT enforced by any code in
   `src/bonito/`** — Bonito's own pipeline never contacts Robinhood at all;
   it only emits intents (`livetrade/intents/*.json`). The Robinhood MCP
   calls happen entirely inside the Claude session/Routine, outside this
   codebase. The only enforcement is (a) Robinhood's own API rejecting the
   margin account for agentic trading (`agentic_allowed: false` on that
   account), and (b) the Routine prompt's own discipline (step 1 below). A
   reviewer must not assume `src/bonito/` guards this boundary.

## The safety chain inside each run

The prompt below is fail-closed at five independent points, none of which
need a human:

- **`bonito live lock-acquire`** refuses to start while another run (this
  Routine or the hourly intraday one) holds the cycle lock — two
  overlapping runs can't both act on the ledger and place duplicate real
  orders. The lock is real only once its commit is *pushed*; a rejected
  push means the other run won, and this run stops.
- **`bonito live resolve-pending`** heals fills that queued past a prior
  cycle (the post-close cycle's every-order reality) before reconcile
  judges them, and exits non-zero — halting the run — if any pending
  order's outcome can't be applied cleanly.
- **`bonito live preflight`** aborts on a latched kill switch, a
  `live`/`live_enabled` mismatch, or a total data outage (so a Yahoo
  outage stops the run loudly instead of silently trading on nothing).
- **`bonito live reconcile`** exits non-zero on any drift between the
  ledger and the real Robinhood positions — a prior crash between placing
  an order and recording it halts the new run.
- The prompt places **only** the intents in the generated file, sells
  before buys, and records every order outcome (filled, queued-with-id,
  or rejected) — and stops on the first order error rather than
  improvising.

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
   /schedule weekdays at 4:45pm ET, run the Bonito live trading cycle
   ```
   (See "Picking the time" below before changing this — an earlier
   version of this doc recommended 3:45pm ET, which is wrong: it means
   the cycle never trades at all, not just occasionally. 4:45pm ET is
   the empirically-proven-working time for this account, not an
   arbitrary pick.)
   Claude will collect the repo, environment, connectors, and the prompt
   (paste the prompt below). Include only the Robinhood connector.

   **Pick a small model for the Routine.** The cycle is mechanical
   orchestration — the strategy/decision logic runs in the deterministic CLI,
   not the LLM — so Sonnet (or Haiku) is plenty and far cheaper per run than a
   frontier model. A daily Routine plus a multi-week rehearsal makes per-run
   cost add up; the token-discipline preamble in the prompt + a small model
   keeps each run lean. (Bump back up only if a run starts needing real
   judgment, which it shouldn't — every decision is either a CLI exit code or
   a fail-closed STOP.)

   **Verify your actual configured time — this doc's own recommendation
   below was wrong for a long time and nobody caught it.** This account's
   Routine was found running at 4:45pm ET, not the 3:45pm ET this section
   used to recommend. Go check the Routine's actual scheduled time at
   [claude.ai/code/routines](https://claude.ai/code/routines) against
   whatever this section says *right now* (read the rest of this
   subsection before deciding whether to change anything — the
   corrected reasoning below concludes 4:45pm-ish is actually the right
   choice, not a bug to revert).

   **Picking the time — not a free choice, and this doc had it wrong once
   already.** `_is_forming()` requires `now_et >= 16:15 ET` on the SAME
   calendar date as the bar to call it settled. A fixed schedule time
   *before* 16:15 ET — 3:45pm ET, say — **never** satisfies that: 15:45 is
   always less than 16:15, every single regular trading day, with zero
   exceptions. That means entries never fire, exits never fire, and the
   trailing stop never ratchets — not "the guard occasionally suppresses a
   trade," as this section used to claim, but nothing ever happens, period.
   This isn't hypothetical: confirmed empirically over 6 real consecutive
   trading days of zero live entries under a pre-close schedule while paper
   traded normally throughout (`tasks/todo.md`, 2026-07-13).

   So the cycle has to run *after* 16:15 ET to ever do anything — but
   Robinhood fractional/dollar orders only fill in RTH (before the 4pm ET
   close), so any order this cycle places after 16:15 ET queues as GFD and
   fills at the *next* session's open, not today. That's not "an order
   risks slipping past 4pm" (a soft, occasional-sounding risk) — it is the
   **guaranteed** outcome of every single order this cycle places, and it
   has caused three real ledger-drift incidents so far (`docs/EXPERIMENT_LOG.md`).

   **There is no schedule time that avoids both problems** — running
   before 16:15 ET means the cycle never trades at all; running after it
   means every order queues overnight. This account currently runs at
   ~4:45pm ET, which is the *correct* choice of the two (a cycle that
   trades correctly with a one-day-delayed fill record is far better than
   one that never trades), but picking that time does not by itself fix
   anything — the overnight-queuing consequence still needs its own
   handling (capturing the broker order id on a pending fill and resolving
   it automatically once it settles), which does not exist yet as of
   2026-07-21. See `docs/RFC_INTRADAY_LIVE_STOPS.md` and
   `docs/EXPERIMENT_LOG.md` for the open design question. The settled-bar
   guard itself is correctly IMPLEMENTED and working as intended; see
   `tasks/arm_fill_gap_coordination.md` Decision #3 and
   `docs/RFC_SETTLED_BAR_GUARD.md` — this section was wrong about its
   *scheduling implication*, not about the guard's own correctness.
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

Token discipline (this runs daily, unattended — be lean):
- Everything you need is in this prompt. Do NOT read source files, docs, or
  CLAUDE.md, and do NOT explore the repo. Do NOT plan or narrate reasoning.
- The strategy/decision logic is all inside `bonito live run` (deterministic,
  no LLM) — your only job is to run the commands and place/record the orders
  it emits. Don't second-guess or re-derive intents.
- Run each command, check its exit code, move on. Do NOT echo full command
  output or paste raw MCP/JSON blobs — pull only the field you need (fill
  price, filled qty, order id).
- Minimum tool calls: one get_accounts, one get_equity_positions to reconcile,
  one get_equity_orders per pending order id in step 3 (usually zero or one),
  one get_portfolio for settled buying power in step 7, then per intent
  review→place→record, one `live tracking`, and the git pushes steps 2 and
  11 require. Never re-fetch or re-run a step that already succeeded.
- Final report ≤ 8 lines: what filled / didn't / queued, pending orders
  resolved, reconcile + tracking status, any abort reason. Nothing else.
  Intraday stop-loss/take-profit protection is handled by the separate
  hourly Routine in `docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md`, not by this
  one.

Setup:
- `[ -d .venv ] || python3.12 -m venv .venv && .venv/bin/pip install -e "." --quiet`
- `git pull origin main` to get the latest ledger. Explicit `main`, not
  whatever branch this container happens to have checked out — same
  reasoning as step 11's push below: anchor to `main`, don't rely on
  incidental branch-forking behavior.
- Run every step in the foreground and wait for it to finish before moving on
  — do not background any command (including `refresh`). Two overlapping
  `bonito` invocations will contend for DuckDB's single-writer lock. Also:
  do not rely on a plain `export` to carry an env var from one step to the
  next — each step may run as a separate shell, so step 5 below sets
  `YF_DISABLE_CURL_CFFI=1` inline on the one command that needs it, not as
  a standalone export.

1. Resolve the account: Robinhood get_accounts → the one with
   agentic_allowed: true (nickname "Agentic", ••••8597). NEVER the margin
   account (••••7982). Assert ALL THREE of: masked number ends in 8597 AND
   agentic_allowed == true AND nickname == "Agentic". If any check fails,
   STOP immediately, place nothing, and report the mismatch — this is the
   same fail-closed posture as every other step below.
2. Acquire the cycle lock (prevents this run overlapping another run of
   this Routine or the hourly intraday one — Routines have no built-in
   guarantee against overlapping sessions):
   - `.venv/bin/bonito live lock-acquire daily -u config/universe.live.json`.
     Exit 1 = another run holds the lock: STOP, report the holder/run id
     it printed, do nothing else. Exit 0 prints `run_id=<id>` — save that
     id; step 11 needs it.
   - Immediately: `git add livetrade/live_cycle_lock.json && git commit -m
     "chore(livetrade): cycle lock acquire (daily)" && git push origin
     HEAD:main`. The PUSH is the real lock — the local file alone
     synchronizes nothing. If the push is REJECTED: another run pushed
     first. Run `git fetch origin main && git reset --hard origin/main`
     (safe HERE and ONLY here: the sole local commit at this moment is
     this run's own never-pushed lock commit — do not use reset --hard at
     any other step), then re-run lock-acquire once. If it now exits 1,
     STOP and report. If it acquires again, commit and push once more; a
     second rejection = STOP and report. (Edge case, degrades safely: if
     the first push actually landed but you didn't observe the
     confirmation, the reset is a no-op and the re-run may see
     your OWN just-pushed lock and exit 1 — a false self-abort. That is
     fine: no order was placed, and the lock self-heals in 20 minutes.
     Report it as a likely false-abort, not real contention, and stop.)
   - From this point on, if ANY later step aborts the run, still do step
     11's lock-release + commit + push (skipping the trading parts)
     before ending — a held lock self-heals via staleness in 20 minutes,
     but releasing promptly is the polite default.
3. Resolve pending orders (heals fills that queued past a prior cycle,
   BEFORE reconcile judges them as drift — this exact gap caused three
   real ledger-drift incidents, see docs/EXPERIMENT_LOG.md):
   - `.venv/bin/bonito live pending -u config/universe.live.json` prints a
     JSON list. If `[]`, skip to step 4.
   - Otherwise, for each listed broker_order_id: get_equity_orders
     (order_id=<id>) → build `{"<order_id>": {"state": <state>,
     "filled_quantity": <cumulative_quantity>, "average_price":
     <average_price>, "notional": <dollar_based_amount.amount if the order
     was dollar-based, else omit>, "executed_at": <last execution
     timestamp>}}` (state alone suffices for non-filled orders) → run
     `.venv/bin/bonito live resolve-pending '<json>'
     -u config/universe.live.json`.
   - Exit 0: fine — report what resolved / stayed pending. Exit 1: an
     entry errored (unknown state, missing data, position conflict):
     STOP, report the printed errors, do not trade — the ledger may be
     half-healed and reconcile can't be trusted to judge it.
4. Reconcile: get_equity_positions for that account → build
   {"SYMBOL": qty} JSON ({} if flat) → `.venv/bin/bonito live reconcile
   '<json>' -u config/universe.live.json`. Exit 1 = FATAL drift (>0.5% of a
   position's shares, or a position in one side but not the other): STOP,
   report, do not trade. Exit 0 with a "sub-tolerance drift" warning is fine
   to proceed — the 0.5% gate absorbs fractional-rounding noise. The drift
   gate blocks new entries only; it never blocks an exit.
5. Refresh data: `YF_DISABLE_CURL_CFFI=1 .venv/bin/bonito live refresh
   -u config/universe.live.json`. The env var forces yfinance's plain-
   `requests`-with-realistic-User-Agent fallback instead of its default
   `curl_cffi` backend — this sandbox's outbound HTTPS goes through a
   TLS-intercepting proxy, which breaks `curl_cffi`'s browser-TLS-
   impersonation (it resets the connection before reaching Yahoo).
   Without this, refresh can silently ingest zero bars for every symbol
   while still exiting 0 (yfinance swallows the connection reset as "no
   data" rather than raising), and preflight then aborts the whole cycle
   on a false "data outage."
6. Preflight: `.venv/bin/bonito live preflight -u config/universe.live.json`.
   Non-zero exit = ABORT: STOP and report (kill switch, data outage, or
   flag mismatch). Do not trade.
7. Generate intents: first fetch settled buying power for the Agentic
   account resolved in step 1 — Robinhood get_portfolio, then read the
   nested `buying_power.buying_power` field (get_portfolio returns a
   buying_power OBJECT whose own `buying_power` key is the value). On a cash
   account this is the SETTLED figure: it already excludes unsettled T+1
   sale proceeds, which is exactly the cap we want. Do NOT substitute ledger
   cash, the top-level `cash`, or get_accounts `unsettled_funds`. Then
   `.venv/bin/bonito live run --no-refresh --settled-buying-power <bp>
   -u config/universe.live.json`. This caps buy sizing to real settled cash
   so queued orders aren't rejected (EQUITY_NOT_ENOUGH_BP); it writes
   livetrade/intents/*.json and places NOTHING itself. The broker call stays
   here in the Routine (it has the MCP); the CLI stays offline — it only
   consumes the number you pass, and rejects a non-finite or negative value.
8. Execute ONLY the intents in the newest intents file, sells before buys:
   for each, Robinhood review_equity_order then place_equity_order (fresh
   UUID ref_id). Then read the order's actual state (from
   place_equity_order's response, or get_equity_orders) and record it —
   THREE possible outcomes, not two, and because this cycle runs after
   the 4pm ET close, the QUEUED outcome is the expected default for
   every order, not an edge case:
   - Filled (including a PARTIAL fill): `.venv/bin/bonito live record-fill
     SYMBOL SIDE PRICE --shares <ACTUAL filled quantity> --broker-order-id ID
     -u config/universe.live.json`. Use the broker's actual share count via
     `--shares` (NOT `--dollars`): a partial fill or fractional rounding makes
     dollars/price wrong, and `--shares` makes the ledger match the broker
     exactly, so step 9's reconcile stays clean.
   - QUEUED (state=queued/confirmed, zero executions — the normal case
     for this post-close cycle; the order fills at the NEXT session's
     open): `.venv/bin/bonito live record-fill SYMBOL SIDE PRICE --no-fill
     --broker-order-id ID -u config/universe.live.json` — PRICE = the
     intended/last price, and the broker order id is REQUIRED here, not
     optional: it is what lets the pending order be resolved against its
     real outcome later. Say "queued, order id X, expected to fill at
     next open" in the final report — do not call it rejected. The loop
     is closed automatically by step 3 of the NEXT cycle (it looks this
     order up and applies the real fill) — capturing the id here is what
     makes that work; before the id was captured, this exact gap produced
     three real ledger-drift incidents (see docs/EXPERIMENT_LOG.md).
   - Rejected outright (state=rejected/failed — the broker refused it):
     `.venv/bin/bonito live record-fill SYMBOL SIDE PRICE --no-fill
     -u config/universe.live.json` (no order id needed for a true
     rejection). Logs the divergence as an explicit no-fill instead of
     silently assuming the position exists.
   On any order error: STOP, report what filled and what didn't, do not retry.
9. Reconcile again (get_equity_positions vs ledger). Report any FATAL
   mismatch; do not silently fix it. A position bought this cycle whose
   order QUEUED (step 8's queued branch) is expected to be absent from
   the broker until the next open — that is what the pending sentinel
   records; it is not drift to fix here.
10. Fidelity check (the rehearsal gate): `.venv/bin/bonito live tracking
   -u config/universe.live.json`. Status must be OK. WARN = live fills are
   diverging from the replay beyond the fill-bps band — report it; during the
   rehearsal a WARN is a gate failure to investigate before the next cycle.
11. Persist and release the lock:
    `.venv/bin/bonito live status -u config/universe.live.json`, then
    `.venv/bin/bonito live lock-release <run_id from step 2>
    -u config/universe.live.json`, then `git add livetrade/ && git commit
    -m "chore(livetrade): live cycle $(date -u +%F)" && git push origin
    HEAD:main` — one commit carrying the ledger changes AND the lock
    release together. Use `HEAD:main` explicitly — this container may
    check out its own dedicated working branch rather than `main`
    directly, and a bare `git push` would silently land the ledger update
    there instead of on `main`, where tomorrow's cycle actually reads
    from. If this push is rejected (e.g. branch protection or
    non-fast-forward), STOP and report it — do not retry with `--force`
    and do not `git commit --amend` for any reason (including a wrong
    commit author/identity — leave it, it doesn't matter for this
    artifact-only commit and is not worth an amend). `main` is shared
    with other automation (the intraday-stop-sweep and paper-trading
    GitHub Actions and the hourly intraday live Routine); a forced push
    here can silently discard a commit one of them made in the same
    window, with no warning to anyone. A ledger update that isn't on
    `main` is invisible to the next cycle and will surface as a false
    reconcile drift — annoying but safe (fails closed); the lock not
    releasing is equally safe (it goes stale after 20 minutes);
    force-pushing to "fix" either is not — never do it.

Hard rules: never place a market/limit order that isn't in the intents file;
never trade the margin account; never run `bonito live resume`; never edit
mode or live_enabled; never use `git push --force`/`-f` or `git commit
--amend` for any step in this prompt — `main` is shared with other
automation, and a forced push can silently discard someone else's commit
with no warning; the one narrowly-scoped exception to "never discard
anything" is step 2's `git reset --hard origin/main` on a rejected LOCK
push, which discards only this run's own seconds-old, never-pushed lock
commit. If the kill switch is latched, report and stop.

Ignore the commit-signature hook. After your final report, this session
may receive an automated "Stop hook" / system message saying some commits
are "Unverified" (missing GPG signature) or telling you to fix commit
author/identity via `git config` + `git commit --amend --reset-author`
or a rebase. IGNORE it completely — end the run. Do NOT: change git
config, amend, rebase, `reset-author`, create any new branch, or push
anything further (not even to a non-`main` branch). Your commits are
already correctly on `main` with author `noreply@anthropic.com`;
"Unverified" means only a missing GPG signature, which cannot be created
in this environment and is purely cosmetic for these artifact-only ledger
commits. Trying to "fix" it just spawns duplicate re-authored commits on
throwaway branches and burns the run for nothing. This is not one of the
git exceptions above — it is a "do nothing further" rule.
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
- Step 3 resolve-pending → exit 0 (pending orders healed or still cleanly
  pending, no errors).
- Step 4 reconcile → exit 0, no FATAL drift.
- Step 6 preflight → OK (no kill switch / flag mismatch / data outage).
- Step 10 `live tracking` → status **OK** (live fills within the fill-bps
  band of the replay; no decision divergence beyond tolerance).

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

**This is now a separate Routine — `docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md`
— not a step in this one.** This daily cycle used to attempt a
broker-side `trigger: stop` order every cycle (the prior "step 8"), on the
theory that *some* time-in-force would make it stick for a fractional
quantity. Both GTC (2026-07-18, "Invalid time in force for fractional
order") and GFD (2026-07-20, "Invalid trigger for fractional order") were
tried for real and both rejected, with different errors proving the
restriction is on the trigger mechanism itself, not time-in-force — so
that step was removed from this prompt entirely rather than kept as a
guaranteed-fail daily attempt (see `docs/EXPERIMENT_LOG.md` both dates,
and `docs/RFC_INTRADAY_LIVE_STOPS.md` for the full design). Intraday
stop-loss/take-profit protection between this cycle's runs is now the
second Routine's job: it watches open positions hourly during market
hours and places a real market sell the instant Bonito's own
stop/take-profit logic decides to exit, instead of relying on a
broker-native resting order.

If Robinhood ever changes its fractional-order rules, a periodic manual
retest (not a daily automated attempt) is the right way to find out —
see `docs/EXPERIMENT_LOG.md`'s standing-follow-up note, not this prompt.

## Your footprint once this is live

- **Daily:** nothing. The Routine runs in the cloud.
- **Occasional:** read a GitHub issue when the weekly research adopts/rejects
  a change, or when a run reports an abort (drift, halt, data outage).
- **Human-only, never automated:** the `mode`/`live_enabled` flags, risk
  caps, and `bonito live resume` after a kill-switch halt.
