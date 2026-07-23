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

1. Create the Routine on claude.ai (or via `/schedule`), then set a
   **custom cron** on it. claude.ai custom crons are interpreted in **UTC**
   (verified: entering `30 13 * * 1-5` displays as "9:30 AM EDT"), and a
   fixed-UTC cron does NOT track daylight saving. So do NOT hand-tune a
   cron for the current season — set the **DST-superset** and let the
   in-prompt market-hours guard trim the strays:
   ```
   30 13-20 * * 1-5
   ```
   That is 13:30-20:30 UTC, weekdays. In EDT (UTC-4) it fires 9:30am-4:30pm
   ET; in EST (UTC-5) it fires 8:30am-3:30pm ET. Either way the guard (Setup
   below) keeps only the real 9:30am-3:30pm ET runs and skips the one stray
   (the 4:30pm EDT run, or the 8:30am EST run) — so the effective schedule
   is exactly 9:30, 10:30, 11:30, 12:30, 1:30, 2:30, 3:30 ET every weekday,
   in both seasons, with no cron edit ever needed. Include only the
   Robinhood connector — same reasoning as the daily Routine. Paste the
   prompt below.
2. **Pick a small model** (Sonnet or Haiku) — same reasoning as the daily
   Routine: the decision logic lives entirely in the deterministic CLI,
   this Routine is mechanical orchestration on top of it.
3. **Last run at 3:30pm ET — the last slot whose sells still fill before
   the 4pm close.** The daily cycle runs post-close at ~4:45pm ET (it must
   run after 16:15 ET or it never trades — see
   `docs/AUTONOMOUS_LIVE_ROUTINE.md`'s "Picking the time"), so it's a full
   ~75 minutes clear of a 3:30pm intraday run, with no realistic collision
   (a 3:30 run would have to execute for 75+ minutes to overlap it — and
   the cycle lock handles even that). A 3:30pm sweep that trips a stop
   places a plain market sell with 30 minutes to fill before the close;
   every universe name is liquid, so it fills in seconds. Going later than
   3:30 (e.g. a :45 cadence) buys a little more coverage but risks a sell
   placed too near the close not filling in time — 3:30 is the sweet spot
   on the hourly cadence. The only intraday-blind window is the last 30
   minutes (3:30–4:00pm), backstopped by the daily cycle's own
   settled-close exit — a granularity difference, not a coverage gap.
   (Earlier drafts of this doc stopped at 2:30pm; that was a leftover from
   a since-corrected assumption that the daily cycle ran at 3:45pm and
   needed a wide buffer before it. It doesn't — see
   `docs/RFC_INTRADAY_LIVE_STOPS.md` §6.5, D2. The retry-then-stop push
   handling below is the real collision protection regardless of the exact
   cutoff.)
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
- Market-hours guard, FIRST after the venv exists:
  `.venv/bin/bonito live market-hours`. Exit 1 = this is a stray
  off-hours firing (the schedule's cron is a UTC superset of both DST
  seasons, so it fires an hour early or late across the EDT/EST boundary
  — see the Setup notes above) — STOP immediately, do nothing else: no
  pull, no lock, no order, no ledger commit. End with a single line
  ("outside window, skipped"); a stray firing needs no fuller report.
  Exit 0 = within the weekday 9:30-15:45 ET window, proceed. This is
  what makes the UTC cron DST-proof without a twice-a-year manual edit.
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
     second rejection = STOP and report. (Edge case, degrades safely: if
     the first push actually landed but you didn't observe confirmation,
     the reset is a no-op and the re-run may see your OWN just-pushed lock
     and exit 1 — a false self-abort. Fine: no order placed, lock
     self-heals in 20 min. Report it as a likely false-abort, not real
     contention, and stop — the next hourly run covers it anyway.)
   - If ANY later step aborts the run, still do step 8's lock-release +
     commit + push (skipping the trading parts) before ending — a held
     lock self-heals via staleness in 20 minutes, but releasing promptly
     is the polite default.
3. Reconcile: get_equity_positions for that account -> build {"SYMBOL": qty}
   JSON ({} if flat) -> `.venv/bin/bonito live reconcile '<json>' -u
   config/universe.live.json`. Exit 1 = FATAL drift: STOP, report, do not
   act — this catches a prior crash between placing and recording an
   order, same reasoning as the daily cycle's steps 4/9.
   - On a FATAL, first run `.venv/bin/bonito live pending -u
     config/universe.live.json` and check whether the drifting symbol(s)
     appear in that list. If they do, this is EXPECTED, not a crash: the
     daily cycle's own overnight-queued order (its step 8 queued branch)
     filled at today's open and the daily cycle's step 3 hasn't reconciled
     it yet. Do NOT inspect the ledger by hand for a "zero-qty sentinel" —
     that only shows the pending-BUY shape; a pending SELL leaves the
     position at full quantity with a separate zero-qty sentinel, so
     `bonito live pending` (which reads the fills, not the positions) is
     the only reliable check. Report it as "pending order likely filled,
     daily cycle will resolve it" and STOP.
   - If the drifting symbol is NOT in the pending list, it's genuine,
     unexplained drift — report that and STOP.
   - Either way, STOP: never run `bonito live resolve-pending` yourself
     (that is exclusively the daily cycle's job — one writer owns sentinel
     healing so two runs never race to heal the same record).
4. Preflight, EXITS-ONLY mode: `.venv/bin/bonito live preflight
   --exits-only -u config/universe.live.json`. The `--exits-only` flag is
   REQUIRED here and is not optional: this Routine's container starts with
   an EMPTY market-data store (the DuckDB is gitignored, so a fresh
   container has no bars until step 5's sweep refreshes the open
   positions), and a plain preflight would false-abort every single run on
   "data outage — 0 fresh bars." `--exits-only` skips the stored-daily-bar
   checks (irrelevant here — this Routine acts on live quotes, not stored
   bars) and gates only on the kill switch and the live/live_enabled flag,
   which still matter. Non-zero exit -> STOP and report (kill switch
   latched, or live/live_enabled misconfigured). Do not run plain
   preflight without the flag.
5. Detect: `YF_DISABLE_CURL_CFFI=1 .venv/bin/bonito live sweep -u
   config/universe.live.json`. Two required details:
   - The `YF_DISABLE_CURL_CFFI=1` prefix is mandatory, same as the daily
     cycle's refresh (this sandbox's TLS-intercepting proxy breaks
     yfinance's default curl_cffi backend — without it, both the refresh
     and the live-quote fetch silently return nothing).
   - Do NOT pass `--no-refresh`: this container's store is empty, so the
     sweep MUST refresh to have any data. The sweep refreshes ONLY the
     open positions (a handful of symbols, for ATR), not the full
     universe, then fetches their live quotes — lean, and correct. (An
     earlier version of this prompt used `--no-refresh` on the mistaken
     belief it would avoid DuckDB lock contention with the daily cycle;
     the two Routines run in SEPARATE isolated containers with separate,
     non-shared DuckDB files, so there is no lock to contend for, and
     `--no-refresh` just left the store empty — see docs/EXPERIMENT_LOG.md.)
   - NEVER pass `--execute` — that flag only auto-fills the *paper* ledger,
     not applicable to live. The sweep places no real order itself; it
     either prints "No stops triggered" (nothing further — skip to step 8)
     or writes an intents file listing which open position(s) triggered a
     stop-loss or take-profit. If ALL quote lookups fail, the sweep exits
     non-zero — treat that as a real data problem: STOP and report.
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
