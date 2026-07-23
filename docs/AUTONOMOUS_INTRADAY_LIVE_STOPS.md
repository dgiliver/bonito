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
3. The daily Routine's own schedule must run **after 16:15 ET**
   (realistically ~4:45pm ET) — running before that threshold means the
   settled-bar guard reads every bar as forming and the daily cycle never
   trades at all, on any regular day (see "Picking the time" in
   `docs/AUTONOMOUS_LIVE_ROUTINE.md`; this doc originally said the
   opposite here, which was the pre-correction premise). A post-close
   daily cycle is expected and correct, not a mistimed bug — its real
   consequence is that every order it places queues overnight and fills
   at the next open (the queued-order ledger-drift class in
   `docs/EXPERIMENT_LOG.md`), which is a distinct, still-open recording
   problem this second Routine neither causes nor fixes; this Routine
   only adds *intraday* exit coverage between the daily cycles.

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
3. **Schedule buffer**: the last run (2:30pm ET) sits ~135 minutes before
   the daily cycle's actual ~4:45pm ET run (see
   `docs/AUTONOMOUS_LIVE_ROUTINE.md`'s "Picking the time" — the daily
   cycle must run after 16:15 ET or it never trades at all, so it's well
   outside this Routine's own 9:30am-2:30pm ET market-hours range, not
   inside it). That's a more comfortable gap than this doc originally
   assumed (it was drafted against a since-corrected 3:45pm ET premise),
   but a same-window collision still isn't impossible — either Routine's
   actual run time can drift from its nominal schedule, exactly as this
   account's own daily cycle already did — which is why the retry-then-stop
   push handling below exists regardless of how comfortable the nominal
   gap looks (see `docs/RFC_INTRADAY_LIVE_STOPS.md` §6.5). A stop breach
   between this Routine's last check and the 4pm ET close (~90 minutes)
   is still caught by the daily cycle's own settled-close exit once it
   runs — a granularity difference, not a coverage gap.
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
  Routine's step 11.
- Run every step in the foreground; do not background anything, including
  step 5's sweep. Do not rely on a plain `export` to carry a variable
  between steps — each may run as a separate shell.

1. Resolve the account: Robinhood get_accounts -> the one with
   agentic_allowed: true (nickname "Agentic", ...8597). Assert ALL THREE of:
   masked number ends in 8597 AND agentic_allowed == true AND nickname ==
   "Agentic". Any check fails -> STOP immediately, do nothing, report the
   mismatch.
2. Acquire the cycle lock (shared with the daily Routine — prevents two
   runs acting on the same ledger concurrently):
   - `.venv/bin/bonito live lock-acquire intraday
     -u config/universe.live.json`. Exit 1 = another run holds it: STOP,
     report the holder/run id it printed, do nothing else — for an hourly
     check, backing off entirely and letting the next hourly run cover it
     is always acceptable. Exit 0 prints `run_id=<id>` — save it; step 8
     needs it.
   - Immediately: `git add livetrade/live_cycle_lock.json && git commit
     -m "chore(livetrade): cycle lock acquire (intraday)" && git push
     origin HEAD:main`. The PUSH is the real lock — the local file alone
     synchronizes nothing. If the push is REJECTED: another run pushed
     first. Run `git fetch origin main && git reset --hard origin/main`
     (safe HERE and ONLY here: the sole local commit at this moment is
     this run's own never-pushed lock commit — do not use reset --hard
     at any other step), then re-run lock-acquire once. Exit 1 now ->
     STOP and report. Acquired again -> commit and push once more; a
     second rejection = STOP and report.
   - If ANY later step aborts the run, still do step 8's lock-release +
     commit + push (skipping the trading parts) before ending — a held
     lock self-heals via staleness in 20 minutes, but releasing promptly
     is the polite default.
3. Reconcile: get_equity_positions for that account -> build {"SYMBOL": qty}
   JSON ({} if flat) -> `.venv/bin/bonito live reconcile '<json>' -u
   config/universe.live.json`. Exit 1 = FATAL drift: STOP, report, do not
   act — this catches a prior crash between placing and recording an
   order, same reasoning as the daily cycle's steps 4/9. NOTE: a pending
   sentinel from the daily cycle's own overnight-queued order (its step
   8 queued branch) resolving at today's open can legitimately surface
   here as drift before the daily cycle's step 3 has run today — if the
   FATAL involves a symbol the ledger shows as a zero-qty pending
   sentinel, report it as "pending order likely filled, daily cycle will
   resolve it" rather than as unexplained drift, and still STOP (do not
   resolve it yourself; only the daily cycle runs resolve-pending).
4. Preflight (defense-in-depth, not load-bearing for exit coverage): `.venv
   /bin/bonito live preflight -u config/universe.live.json`. Non-zero exit
   -> STOP and report (kill switch, data outage, or flag mismatch). A
   latched kill switch already flattened every position at the moment it
   tripped, so this is very unlikely to ever find something left to
   protect — call it anyway, it is cheap and still catches a
   live/live_enabled misconfiguration or a stale data feed.
5. Detect: `.venv/bin/bonito live sweep --no-refresh -u
   config/universe.live.json`. NEVER pass `--execute` here — that flag only
   auto-fills the *paper* ledger, which is not applicable to live. This
   command does not place any real order itself; it either prints "No stops
   triggered" (nothing further to do — skip to step 8) or writes an intents
   file listing which open position(s) triggered a stop-loss or take-profit.
6. If (and only if) step 5 wrote an intents file: for each intent in it,
   place a real market sell — Robinhood review_equity_order then
   place_equity_order (plain market order, fresh UUID ref_id — NEVER
   trigger:stop; that is confirmed rejected for fractional quantities on
   this account regardless of time-in-force, see docs/EXPERIMENT_LOG.md
   2026-07-18 and 2026-07-20). This Routine only runs during regular
   hours, so the order should fill promptly — read its ACTUAL filled
   quantity and price, then record it:
   `.venv/bin/bonito live record-fill SYMBOL sell PRICE --shares <ACTUAL
   filled quantity> --broker-order-id ID -u config/universe.live.json`.
   Use `--shares`, never `--dollars` — a partial fill or fractional
   rounding makes dollars/price wrong. If the order somehow does NOT
   resolve promptly (state stays queued/confirmed with zero executions):
   record it as a pending sentinel instead — `.venv/bin/bonito live
   record-fill SYMBOL sell PRICE --no-fill --broker-order-id ID
   -u config/universe.live.json` (id REQUIRED — it is what lets the
   daily cycle's resolve-pending step heal it) — and name it in the
   report. On any order error: STOP, report what filled and what didn't,
   do not retry.
7. If step 6 acted: reconcile again (get_equity_positions vs ledger).
   Report any FATAL mismatch; do not silently fix it.
8. Persist and release the lock: `.venv/bin/bonito live status -u
   config/universe.live.json`, then `.venv/bin/bonito live lock-release
   <run_id from step 2> -u config/universe.live.json`, then `git add
   livetrade/ && git commit -m "chore(livetrade): intraday live
   stop-check $(date -u +%FT%H:%MZ)"` — one commit carrying any ledger
   changes AND the lock release together (there is always at least the
   lock release to commit, since step 2 committed the acquisition).

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
   fixes it. Do not attempt to resolve a real conflict yourself. (The
   unreleased lock is harmless — it goes stale after 20 minutes.)

   Why this differs from the daily cycle's "stop immediately on a
   rejected push" rule: giving up immediately here, like the daily cycle
   does, would leave an already-executed real broker order unrecorded in
   the ledger until someone notices — worse than the daily cycle's
   version of this same scenario. The bounded retry is safe specifically
   because it never touches history anyone else has already seen.

Hard rules: never place any order that is not a plain market sell for a
symbol step 5's sweep actually flagged; never place a `trigger: stop`
order (confirmed rejected for fractional quantities on this account);
never trade the margin account; never edit mode or live_enabled; never
run `bonito live resolve-pending` (that is exclusively the daily
cycle's job); never use `git push --force`/`-f` or `git commit --amend`
for any reason — the TWO narrowly-scoped exceptions in this entire
prompt are step 8's bounded `git pull --rebase` retry (not a force-push;
never rewrites shared history) and step 2's `git reset --hard
origin/main` on a rejected LOCK push (discards only this run's own
seconds-old, never-pushed lock commit). If the kill switch is latched,
report and stop.
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
