# Autonomous intraday live stops via a second Claude Code Routine

This is the second, hourly Routine from `docs/RFC_INTRADAY_LIVE_STOPS.md`.
Read that RFC for the full reasoning; this doc is the buildable prompt,
mirroring `docs/AUTONOMOUS_LIVE_ROUTINE.md`'s conventions exactly. It
exists because broker-side `trigger: stop` orders are confirmed rejected
for fractional quantities on this account — both GTC (2026-07-18) and GFD
(2026-07-20), with different errors proving the restriction is the trigger
mechanism itself, not time-in-force (`docs/EXPERIMENT_LOG.md`, both dates).
There is no broker-native resting order to lean on, so this Routine
watches open positions itself, hourly, and places a real market sell the
instant Bonito's own `check_stops()` logic decides to exit.

**This is a second, independent Routine — it does not replace the daily
one.** The daily cycle (`docs/AUTONOMOUS_LIVE_ROUTINE.md`) still owns
entries and its own once-daily settled-close exits. This Routine only
watches for stop-loss/take-profit triggers *between* those daily
decisions and only ever places sells.

## Safety preconditions (same as the daily Routine)

1. Robinhood connected as a **claude.ai connector** (already true if the
   daily Routine works — this Routine reuses the same connector).
2. `config/universe.live.json` has `mode: "live"` and `live_enabled: true`
   (unchanged by this Routine; human-only).
3. The daily Routine's own schedule must run comfortably before the 4pm ET
   close — **if it does not, fix that first.** A late-running daily cycle
   (this account's actual root cause for 2 of its 3 ledger-drift incidents
   so far — see `docs/EXPERIMENT_LOG.md`) queues its own orders past the
   close regardless of anything this second Routine does; this Routine
   only adds *intraday* coverage between cycles, it does not fix a
   mistimed daily cycle.

## Setup (from a LOCAL terminal, same as the daily Routine)

`/schedule` is unavailable inside a cloud session.

1. From a local Claude Code terminal:
   ```
   /schedule weekdays every hour from 9:30am to 2:30pm ET, run the Bonito
   intraday live stop-check
   ```
   Include only the Robinhood connector — same reasoning as the daily
   Routine. Paste the prompt below.
2. **Pick a small model** (Sonnet or Haiku) — same reasoning as the daily
   Routine: the decision logic lives entirely in the deterministic CLI,
   this Routine is mechanical orchestration on top of it.
3. **Schedule buffer, not a free choice**: the last run (2:30pm ET) sits
   75 minutes before the daily cycle's 3:45pm ET run, wider than the
   45-minute gap paper's `intraday-stops.yml` keeps from its own daily
   cycle — because live's daily cycle runs *during* this Routine's own
   market-hours range (paper's runs safely after close), so a
   same-window collision is a real, not just theoretical, possibility
   here (see `docs/RFC_INTRADAY_LIVE_STOPS.md` §6.5). A stop breach in
   the last ~75 minutes before close is still caught by the daily
   cycle's own settled-close exit — a granularity difference in the last
   hour, not a coverage gap.
4. **Dogfood before trusting the schedule**: use "Run now" once while you
   watch, ideally with no open positions or with a symbol you're
   comfortable testing an exit on, to confirm the full chain end to end
   before relying on the schedule.

## The Routine prompt (self-contained)

```
You are running the Bonito intraday live stop-check on the Robinhood
Agentic cash account, unattended. Follow these steps exactly. If any step
aborts, STOP, commit nothing new, and end the run reporting what happened —
never improvise an order.

Token discipline (this runs hourly during market hours, unattended — be
lean):
- Everything you need is in this prompt. Do NOT read source files, docs, or
  CLAUDE.md, and do NOT explore the repo. Do NOT plan or narrate reasoning.
- The stop/take-profit decision logic is all inside `bonito live sweep`
  (deterministic, no LLM) — your only job is to run the commands and
  place/record a real order for whatever it flags. Don't second-guess or
  re-derive its decision.
- Run each command, check its exit code, move on. Do NOT echo full command
  output or paste raw MCP/JSON blobs — pull only the field you need.
- Final report <= 6 lines: triggered or not, what filled, reconcile/push
  status, any abort reason. Nothing else.

Setup:
- `[ -d .venv ] || python3.12 -m venv .venv && .venv/bin/pip install -e "." --quiet`
- `git pull origin main` — explicit `main`, same reasoning as the daily
  Routine's step 10.
- Run every step in the foreground; do not background anything, including
  step 4's sweep. Do not rely on a plain `export` to carry a variable
  between steps — each may run as a separate shell.

1. Resolve the account: Robinhood get_accounts -> the one with
   agentic_allowed: true (nickname "Agentic", ...8597). Assert ALL THREE of:
   masked number ends in 8597 AND agentic_allowed == true AND nickname ==
   "Agentic". Any check fails -> STOP immediately, do nothing, report the
   mismatch.
2. Reconcile: get_equity_positions for that account -> build {"SYMBOL": qty}
   JSON ({} if flat) -> `.venv/bin/bonito live reconcile '<json>' -u
   config/universe.live.json`. Exit 1 = FATAL drift: STOP, report, do not
   act — this catches a prior crash between placing and recording an
   order, same reasoning as the daily cycle's step 2/7.
3. Preflight (defense-in-depth, not load-bearing for exit coverage): `.venv
   /bin/bonito live preflight -u config/universe.live.json`. Non-zero exit
   -> STOP and report (kill switch, data outage, or flag mismatch). A
   latched kill switch already flattened every position at the moment it
   tripped, so this is very unlikely to ever find something left to
   protect — call it anyway, it is cheap and still catches a
   live/live_enabled misconfiguration or a stale data feed.
4. Detect: `.venv/bin/bonito live sweep --no-refresh -u
   config/universe.live.json`. NEVER pass `--execute` here — that flag only
   auto-fills the *paper* ledger, which is not applicable to live. This
   command does not place any real order itself; it either prints "No stops
   triggered" (nothing further to do — skip to step 7) or writes an intents
   file listing which open position(s) triggered a stop-loss or take-profit.
5. If (and only if) step 4 wrote an intents file: for each intent in it,
   place a real market sell — Robinhood review_equity_order then
   place_equity_order (plain market order, fresh UUID ref_id — NEVER
   trigger:stop; that is confirmed rejected for fractional quantities on
   this account regardless of time-in-force, see docs/EXPERIMENT_LOG.md
   2026-07-18 and 2026-07-20). After the order resolves, read its ACTUAL
   filled quantity and price, then record it:
   `.venv/bin/bonito live record-fill SYMBOL sell PRICE --shares <ACTUAL
   filled quantity> --broker-order-id ID -u config/universe.live.json`.
   Use `--shares`, never `--dollars` — a partial fill or fractional
   rounding makes dollars/price wrong. On any order error: STOP, report
   what filled and what didn't, do not retry.
6. If step 5 acted: reconcile again (get_equity_positions vs ledger).
   Report any FATAL mismatch; do not silently fix it.
7. Persist (only if anything changed — a no-trigger run may still have
   ratcheted a trailing high-water mark): `.venv/bin/bonito live status -u
   config/universe.live.json`, then `git add livetrade/ && git commit -m
   "chore(livetrade): intraday live stop-check $(date -u +%FT%H:%MZ)"`.
   Skip the commit only if `git diff --cached --quiet` shows nothing
   staged changed.

   Push (this is the ONE place this Routine's rules deliberately differ
   from the daily cycle's — read this carefully, it is not a mistake):
   `git push origin HEAD:main`. If rejected (non-fast-forward, e.g. the
   daily cycle pushed first): run `git pull --rebase origin main`, then
   retry the push. Up to 3 attempts total. This is NOT a force-push and
   does not conflict with the no-force rule below — it replays your own
   local, not-yet-shared commit on top of the new remote tip, then pushes
   normally; it never rewrites a commit anyone else has already seen. If a
   rebase attempt hits an actual content conflict (not just a clean
   divergence): run `git rebase --abort` immediately (safe — this only
   undoes your own local, unpushed rebase attempt), then STOP and report
   explicitly that a real order executed but could not be persisted this
   run, so the next reconcile (yours or the daily cycle's) catches and
   fixes it. Do not attempt to resolve a real conflict yourself.

   Why this differs from the daily cycle's "stop immediately on a
   rejected push" rule: giving up immediately here, like the daily cycle
   does, would leave an already-executed real broker order unrecorded in
   the ledger until someone notices — worse than the daily cycle's
   version of this same scenario. The bounded retry is safe specifically
   because it never touches history anyone else has already seen.

Hard rules: never place any order that is not a plain market sell for a
symbol step 4's sweep actually flagged; never place a `trigger: stop`
order (confirmed rejected for fractional quantities on this account);
never trade the margin account; never edit mode or live_enabled; never
use `git push --force`/`-f` or `git commit --amend` for any reason — the
ONE exception in this entire prompt is step 7's bounded `git pull
--rebase` retry, which is not a force-push and does not rewrite shared
history. If the kill switch is latched, report and stop.
```

## Why no rehearsal-sizing protocol here

The daily Routine's rehearsal protocol graduates *entry* sizing from
1-share to full size. This Routine never enters a position — it only
sells an already-open one when Bonito's own stop/take-profit logic
decides to exit — so there is no equivalent sizing dial to graduate.
Dogfooding (above) is the right-sized substitute: prove the chain end to
end with "Run now" before trusting the schedule, same spirit, smaller
mechanism.

## Your footprint once this is live

Same as the daily Routine: nothing daily. Read a report only when this
Routine actually places a sell, or when it aborts (drift, kill switch,
data outage, or an unresolvable push conflict).
