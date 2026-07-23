# RFC: Intraday live stop protection (a second Routine)

- **Status:** Proceeding on all 4 recommendations in §9 (2026-07-21) — the
  user asked to move to building the second Routine without objecting to
  any of §9's specifics, so each is marked "proceeding per recommendation"
  below rather than a line-by-line confirmed sign-off; flag any of them to
  override. Built as `docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md`; the user
  still needs to create the Routine itself (§10 rollout, manual claude.ai
  step). Also surfaced and corrected a stale claim in
  `docs/AUTONOMOUS_LIVE_ROUTINE.md`: the daily cycle's actual ~4:45pm ET
  schedule is CORRECT, not a misconfiguration — running before 16:15 ET
  (the settled-bar guard's threshold) means the cycle never trades at
  all, confirmed empirically over 6 days (`tasks/todo.md`, 2026-07-13);
  running after it means every order queues overnight, which is what
  actually needs fixing (§9 D1 is unaffected by this; the still-open
  pending-fill-resolution work below now absorbs what a "fix the
  schedule" plan would otherwise have tried to avoid).
- **Author:** orchestrator pass, 2026-07-21
- **Branch:** `claude/determined-shannon-0dhndr`
- **Supersedes/extends:** `docs/AUTONOMOUS_LIVE_ROUTINE.md` step 8 (the daily
  broker-side stop-order attempt) and its "Intraday stops under a Routine"
  section; `docs/EXPERIMENT_LOG.md` 2026-07-18 and 2026-07-20 bug rows
- **Implements option:** the "second Routine" alternative named and
  deliberately deferred in chat on 2026-07-18, designed here after the only
  competing option — a direct, non-Claude-session Robinhood integration — was
  researched and ruled out (§2.3)

---

## 1. Summary (TL;DR)

All 6 open live positions (PLTR, HOOD, ASML, LLY, META, AMZN, on the
Agentic ••••8597 cash account) are currently **unprotected by any
broker-side stop mechanism**. Not because step 8 hasn't been hardened
enough — it has, twice — but because it's now empirically proven that
Robinhood **rejects `trigger: stop` orders for fractional share quantities
on this account, unconditionally**. Two independent, differently-worded
rejections rule out time-in-force as the fixable variable:

| Date | Time in force | Error | What it proves |
|------|---------------|-------|-----------------|
| 2026-07-18 | GTC | `"Invalid time in force for fractional order"` | Looked like a TIF problem |
| 2026-07-20 | GFD | `"Invalid trigger for fractional order"` | It isn't — the **trigger type itself** is rejected, independent of TIF |

Every position in this account is fractional by construction (small-account
dollar-based slots), so there is no third time-in-force value left to try.

A from-scratch direct Robinhood API integration — bypassing the
Claude-session requirement entirely, mirroring paper's cheap
GitHub-Actions-based `intraday-stops.yml` — was researched as the
alternative and **ruled out** (§2.3): the only sanctioned path (Robinhood's
Agentic Trading MCP) has no companion API-key mode, and the fallback
(the older, unofficial, reverse-engineered API) is not a viable
replacement for it.

**Proposal:** a **second Claude Code Routine**, running hourly during market
hours, that reuses the exact `check_stops()` logic paper's
`intraday-stops.yml` has run every 15 minutes for weeks — except, since a
broker-native stop is off the table, it **places a real market sell**
through the Robinhood MCP the instant Bonito's own logic decides a stop or
take-profit has triggered, rather than leaving a resting order for the
broker to fill. This is not new architecture: it is the **same shape the
daily Routine already uses for every exit** (Bonito decides → the Routine
places → the Routine records), on an hourly cadence instead of a daily one.
It replaces the currently-guaranteed-to-fail step 8 with a mechanism that
actually watches and acts.

This RFC also writes down every operational lesson this session forged
while hardening the daily Routine (§3) — because the new Routine inherits
every one of those hazards on day one, and re-deriving them from a second
set of real-money mistakes is not an acceptable way to learn them twice.

---

## 2. Problem

### 2.1 The broker-side stop mechanism is dead — proven, not assumed

`docs/AUTONOMOUS_LIVE_ROUTINE.md` step 8 was built, then hardened, on the
assumption that *some* time-in-force would let a `trigger: stop` order
stick for a fractional quantity. That assumption held right up until real
market-hours testing:

- **2026-07-18 — GTC rejected.** The first real attempt, on all 3
  then-open positions (PLTR/HOOD/ASML), came back
  `"Invalid time in force for fractional order."` Read literally, this
  blames time-in-force — so switching to GFD was a reasonable next
  experiment, not a guess (`c5e7e3e`).
- **2026-07-20 (Monday) — GFD also rejected.** The predicted next test,
  under real market hours as planned. Rejected too, but with a **different**
  error: `"Invalid trigger for fractional order."` This is the load-bearing
  fact: a *different* rejection reason on the *only other* TIF worth trying
  means the restriction is on `trigger: stop` itself, not on which TIF
  accompanies it. There is no remaining TIF value whose rejection would look
  any different — this line of investigation is exhausted, not paused.

Both tests ran through Robinhood's official **Agentic Trading MCP**, live
only since ~May 2026. It has no public track record yet; the historical
community knowledge that exists for Robinhood (`robin_stocks` and similar)
describes the older, unofficial, reverse-engineered API and does not
reliably transfer — which is exactly why this needed two real, on-account
tests rather than more research (5 parallel research passes before the
first test found genuinely mixed secondary evidence, not an answer).

### 2.2 What step 8 was actually trying to buy, and its ceiling even if it had worked

Step 8's purpose was never full-time coverage — it was explicitly documented
as **not** giving 24/7 protection even in the best case: a GFD stop expires
at that session's close and needs re-placing every cycle, leaving a gap
between market open and whenever the daily cycle runs, every single day.
GTC would have closed that specific gap; GFD, even if accepted, would not
have. So the realistic ceiling of a working step 8 was "one broker-enforced
price level, refreshed once a day, with a same-day coverage gap before the
cycle runs" — not continuous protection. That ceiling matters for §6: the
mechanism proposed below clears it without much effort, because active
hourly checking is a strictly better shape than a passive resting order
refreshed once a day, independent of the fractional-order restriction.

### 2.3 The direct-API alternative — researched and ruled out

Before designing a second Routine, the cheaper-sounding alternative was
investigated: could live intraday stops run the way paper's
`intraday-stops.yml` does — a plain GitHub Actions cron with no LLM
session at all — via some direct Robinhood integration that doesn't need a
live Claude session? Researched across three independent dimensions, all
converging on **no**:

- **Technical.** Robinhood's only current, sanctioned automated-trading
  surface for this account is the Agentic Trading MCP, which exists
  *inside* a Claude session by design — it has no companion API-key mode,
  no webhooks, and no conditional/scheduled order primitive that would let
  a stateless cron job place or manage orders on its own. The older
  unofficial API (`robin_stocks` and similar) that a cron job could in
  principle call directly is unmaintained/fragile and is not what this
  account's orders route through — building against it would be building
  against a different, unsanctioned integration, not a lighter version of
  the current one.
- **Legal/ToS.** The sanctioned path (a Claude session driving the official
  MCP) carries low ToS risk precisely because it *is* the sanctioned path.
  A workaround built on the unofficial API would trade that low-risk
  standing for a materially different risk profile, for a cost-savings
  reason alone — not a trade this account's stakes justify.
- **Competitive.** No broker was found that combines fractional-share
  support with a genuinely indefinite, unattended, API-key-based
  auth story — the thing that would make a GitHub-Actions-style direct
  integration actually work long-term the way it does for paper.

None of these are soft "hasn't been tried yet" conclusions — this was
multi-agent research specifically tasked with finding a counterexample to
each, and none turned one up. **A second Claude Code Routine is not the
fallback option — given the constraint that live orders require a live
Claude session, it is the only architecture left.**

---

## 3. Operational lessons this session forged (the new Routine inherits all of them)

The daily Routine did not arrive at its current form by design — every rule
below was written *after* a real run hit the failure it now guards against.
The new Routine starts from the same real-money account, the same
Robinhood MCP, the same shared `main` branch, and the same unattended,
no-approval-prompt execution model, so it inherits every one of these
hazards on its very first run, not hypothetically.

- **The TLS-intercepting proxy breaks `curl_cffi`.** This sandbox's
  outbound HTTPS goes through a proxy that resets the connection before
  Yahoo's TLS handshake completes when `yfinance` uses its default
  `curl_cffi` browser-impersonation backend — and `yfinance` swallows that
  reset as "no data" rather than raising, so a refresh can silently ingest
  zero bars while still exiting 0. `YF_DISABLE_CURL_CFFI=1` forces the
  plain-`requests` fallback instead. It has to be set **inline on the
  specific command that needs it**, not via a standalone `export` —
  Routine steps may each run as a separate shell, so exported state does
  not reliably carry from one step to the next. The new Routine only needs
  this if it ever calls `bonito live refresh` itself (§6.2 recommends it
  doesn't), but must not assume env state persists across its own steps
  either.
- **`git push origin HEAD:main`, never a bare `git push`.** A Routine
  container may check out its own dedicated working branch rather than
  `main` directly. A bare push would silently land a ledger commit on that
  stray branch — invisible to every other automation that reads from
  `main` — while still looking like success locally.
- **Never `git push --force`/`-f`, never `git commit --amend`, on this
  branch, for any reason.** `main` is shared with the paper-trading and
  intraday-stop-sweep GitHub Actions and now the daily live Routine; a
  forced push can silently discard a commit one of them made in the same
  window, with no warning to anyone. This is now enforced by GitHub branch
  protection (user-configured: "Do not allow force pushes" + "Do not allow
  bypassing the above settings"), which **correctly rejected** a
  carefully-verified, good-faith `--force-with-lease` recovery attempt made
  this session — treated as the safeguard working as intended, not an
  obstacle. §6.5 designs the new Routine's push-conflict handling with this
  rule as a hard constraint, not a suggestion.
- **Shell-quoting a multi-paragraph commit message is a real hazard, not a
  style nit.** A commit message with a `$` followed by a digit, or a
  backtick-quoted command name, inside a double-quoted `git commit -m
  "..."` argument gets mangled by bash: `$9`/`$1`/`$3` expand as
  positional parameters (silently stripping leading digits off dollar
  figures) and backticks trigger command substitution (silently deleting
  whatever they wrapped and erroring on the result). Caught once this
  session by re-reading the committed message and grepping for the
  expected numbers; the fix (write to a file, commit with `-F`) applies to
  this Routine too the moment its commit messages get descriptive.
- **`get_equity_orders` succeeding is not proof; only re-querying is.** A
  `place_equity_order` call returning without an error is not sufficient
  evidence that an order exists — this exact gap let 3 real positions sit
  with an unconfirmed stop for over a day (2026-07-16) before anyone
  noticed. The fix pattern — verify via a fresh read after every mutating
  call, treat zero-found as "check again once, passively, before any
  retry" (broker-side state can lag), and treat "more than one found" as
  its own named failure rather than folding it into success — is a general
  broker-interaction pattern, not specific to stop orders. The new
  Routine's order placement (§6.3) uses the same shape.
- **The queued-order-resolves-later-than-cycle-time bug class — hit
  twice.** A dollar-based/fractional market order placed outside a live
  session (after 4pm ET, or on a weekend) queues as a GFD
  regular-hours order rather than filling immediately:
  - **PLTR/HOOD/ASML** were opened 2026-07-16 via orders placed after 4pm
    ET; they queued and didn't actually fill until 2026-07-17 09:30 ET —
    a different day, a different price, and therefore a different
    quantity than what the cycle recorded at decision time. Nothing
    reconciled the stale record against the real fill once it happened.
  - **LLY/META/AMZN** were opened via orders placed on Saturday 2026-07-18;
    they queued and filled at Monday's open, 2026-07-20 09:30 ET. This
    time the cycle correctly recorded an explicit no-fill sentinel rather
    than a wrong number (the verification hardening from the first
    incident working as intended) — but again, nothing later reconciled
    that sentinel against the real fill once it happened, so the position
    was simply missing from the ledger for two days.
  Both were root-caused precisely, verified against ≥2 independent broker
  sources (`get_equity_positions` for qty/cost-basis,
  `get_equity_orders` for execution timestamps, `get_portfolio` for a cash
  cross-check), and corrected through the real `PaperLedger` code path —
  never hand-edited JSON — then round-tripped through save/load before
  being trusted. **This is a real, still-open gap**: an automated
  reconcile-and-correct step, not a third manual patch, is the right fix,
  and it is not built yet. The new intraday Routine's own market-hours-only
  schedule (§6.1) sidesteps this specific trigger (its own orders should
  always fill same-cycle, in RTH) but does not fix the underlying gap for
  the daily cycle, and both Routines share one ledger.
- **A tool-access approval gate is a deliberate checkpoint, not a bug.**
  A subagent asked to test order-placement access — twice, the second time
  with the user's own explicit authorization quoted verbatim — both times
  soundly declined, reasoning that an order-tool-category approval wall is
  a deliberate human-in-the-loop checkpoint. That was accepted as correct,
  not routed around a third way. The new Routine does not change who is
  authorized to place live orders; it is a second *scheduled* actor with
  the same Robinhood connector and the same account scoping as the first.

---

## 4. What already exists — reuse, don't rebuild

The paper account has been running an equivalent intraday mechanism for
weeks; almost nothing here is new:

- **`check_stops()`** (`src/bonito/trading/live_runner.py:577`) — the
  intraday stop-loss/take-profit sweep. Sources prices from live quotes
  (not stored daily bars), inspects only open positions, **never generates
  entries**, and ratchets `high_water_mark` on every call. Mode-agnostic —
  nothing in it branches on `universe.mode`.
- **`compute_position_atrs`** — ATR inputs for ATR/trailing stops, read
  from the DuckDB store (a read, not a write — doesn't contend for the
  single-writer lock `bonito live refresh`/`bonito live run` need).
- **`bonito live sweep`** (`cli.py:1114`, body in `_sweep_stops`,
  `cli.py:1153`) — the CLI entry point: fetch quotes → `check_stops` →
  write an intents file if anything triggered → `ledger.save()`
  unconditionally (persists HWM ratcheting even when nothing triggers).
  Accepts `-u`/`--universe` like every other `live` command — nothing
  in this path is paper-specific **except** the `--execute` flag, which
  only auto-fills the ledger `if execute and universe.mode == "paper"`
  (`cli.py:1174`) — correctly scoped, since live can never assume a fill;
  it must always go through a real broker order. This means `bonito live
  sweep -u config/universe.live.json` (without `--execute`) already works
  today, unmodified, against the live ledger: it detects a triggered stop
  and writes the intents file, exactly the input the new Routine needs.
  **No new `src/bonito` code is required for detection** — worth
  confirming with a dry run and a mode-parameterized test before relying
  on it (§8), but it is not a new build.
- **`.github/workflows/intraday-stops.yml`** — paper's production
  precedent: cron `*/15 13-21 * * 1-5` UTC (trimmed to 9:30–16:00 ET by an
  in-job `zoneinfo` guard), a `concurrency: group: livetrade-state` shared
  with the daily paper cycle so the two jobs never commit at the same
  time, a bounded `git pull --rebase` retry loop (3 attempts) before
  giving up on a push conflict, and exactly one open GitHub issue on
  failure rather than one every 15 minutes. §6.5 examines which parts of
  this precedent transfer cleanly to live and which don't.
- **`compute_stop_levels()`** (`live_runner.py:525`) — the function step 8
  already uses to compute a stop *price* for a broker order. Distinct from
  `check_stops()`: it reports a level for a resting order, it does not fire
  an exit itself. Still useful for a human-readable status line, not for
  the new Routine's core loop.

---

## 5. Scope & non-goals

**In scope:** a second, independently-scheduled Claude Code Routine that
watches open live positions between daily cycles and places a real market
exit the moment Bonito's own stop-loss/take-profit logic fires; the
push/reconcile/fill-recording discipline it needs to do that safely
alongside the existing daily Routine.

**Explicit non-goals:**

1. **No entry logic in the new Routine.** `check_stops()` never generates
   entries, by construction — the new Routine inherits that boundary for
   free. Evaluating entries hourly would reintroduce exactly the
   forming-bar hazard `RFC_SETTLED_BAR_GUARD.md` fixed for the daily cycle;
   nothing here revisits that.
2. **No change to the daily cycle's own exit logic.** The settled-close
   exit rules in `generate_intents` are unchanged; they remain the
   authoritative, once-daily decision, with the new Routine filling the gap
   *between* those decisions, not replacing them (§7).
3. **No change to `mode`/`live_enabled`/risk caps.** Human-only, as
   everywhere else in this pipeline.
4. **Not (yet) the systemic queued-order-reconciliation fix** flagged in
   §3 — that gap is real and still open, but is a fix to the *daily*
   cycle's fill-recording, orthogonal to standing up intraday monitoring.
   Named here so it isn't lost, not solved here.

---

## 6. Design

### 6.1 Cadence & schedule

Routines have a one-hour minimum polling interval, so "intraday" here means
hourly, not 15-minute like paper's sweep. Recommended: on the half-hour
from the open through the last slot whose sells still fill before the 4pm
close (9:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30 ET). The daily cycle
must run after 16:15 ET (the settled-bar guard's threshold; running before
it means the daily cycle never trades at all — see the corrected "Picking
the time" section in `docs/AUTONOMOUS_LIVE_ROUTINE.md`), so realistically
~4:45pm ET. That leaves the last intraday check (15:30) ~75 minutes clear
of the daily cycle — a 15:30 run would have to execute for 75+ minutes to
overlap it, and the cycle lock handles even that. 15:30 is the last slot
that still leaves 30 minutes for a placed market sell to fill before the
close; a later slot risks a sell that doesn't fill in time.
A stop breach in the final run-up to close, after the last intraday check,
is still caught by the daily cycle's own settled-close exit — a coverage
*granularity* difference in the last ~hour, not a gap (§7).

**DST-proofing the schedule (added 2026-07-23).** claude.ai custom crons
are interpreted in UTC, not the user's local zone (verified: `30 13 * * 1-5`
displays as "9:30 AM EDT"). A fixed-UTC cron therefore fires an hour off
across the EDT/EST boundary — tuned for summer, it would run 8:30am–2:30pm
ET all winter, first run pre-market. Rather than a twice-a-year manual cron
edit (exactly the kind of silent-drift maintenance that already produced
this account's 3:45→4:45pm schedule divergence), the cron is a **UTC
superset** of both seasons (`30 13-20 * * 1-5`) and an in-prompt guard
(`bonito live market-hours` → `in_intraday_sweep_window`, `live_runner.py`)
trims stray firings to the real weekday 9:30am–15:45 ET window (15:45, not
15:30, absorbs the run stagger claude.ai's Routines UI states it applies —
"Runs are staggered by a few minutes to spread server load" — while still
leaving fill time before the close). This is the same superset-cron + ET-guard pattern paper's
`intraday-stops.yml` uses, ported from a GitHub Actions in-job Python check
to a tested CLI exit-code gate. DST-correct via `zoneinfo`, no cron edit
ever needed.

### 6.2 Detection: reuse `bonito live sweep` (with refresh)

`YF_DISABLE_CURL_CFFI=1 bonito live sweep -u config/universe.live.json`.

- **Refresh, NOT `--no-refresh` (corrected 2026-07-23).** The original
  design used `--no-refresh` on the theory it would avoid contending with
  the daily cycle for DuckDB's single-writer lock. That theory was wrong,
  and the first real runs proved it: `data/market_data.duckdb` is
  gitignored, and Routine containers are ephemeral, so each intraday run
  starts with a completely EMPTY store — there is no shared DuckDB to
  contend for (the two Routines are isolated containers with separate
  files), and `--no-refresh` simply left the store empty, so preflight
  false-aborted every run on "data outage" and ATR could never compute. A
  plain `sweep` (no `--no-refresh`) refreshes ONLY the open positions
  (`refresh_data(store, symbols=sorted(ledger.positions))`, `cli.py`) —
  a handful of symbols for ATR, lean — then fetches their live quotes. The
  `YF_DISABLE_CURL_CFFI=1` prefix is required for the same TLS-proxy reason
  the daily cycle's refresh needs it (both `refresh_data` and
  `fetch_latest_quotes` go through yfinance).
- **No `--execute`**: that flag's job is auto-filling the *paper* ledger,
  which is exactly the fiction live can't assume (`RFC_LIVE_FIDELITY.md`'s
  entire thesis). Live already has the right shape without it: `sweep`
  writes an intents file when something triggers, and the Routine —
  exactly like the daily cycle's step 6 — is what actually places the real
  order.
- **Preflight runs `--exits-only`** (§6.4): the stored-daily-bar data
  checks are wrong for a live-quote-based exits path and would false-abort
  on the empty container; only the kill-switch and live/live_enabled
  checks are kept.

### 6.3 Placement: real market sell, same shape as daily step 6

For each intent in the freshly-written file: `review_equity_order` →
`place_equity_order` (plain market sell, fresh UUID `ref_id` — never
`trigger: stop`, which §2.1 proved doesn't work for this account anyway).
Read the order's actual filled quantity/price, then record it with
`bonito live record-fill SYMBOL sell PRICE --shares <actual filled qty>
--broker-order-id ID -u config/universe.live.json` — never `--dollars`,
same reasoning as the daily cycle's step 6. **Verify, don't assume**: the
same `get_equity_orders`-confirms-it pattern step 8 was hardened with
(§3) — a non-error `place_equity_order` response is not proof by itself.

### 6.4 Fill recording & reconcile discipline — inherited verbatim

Before acting, a lightweight reconcile (`get_equity_positions` →
`bonito live reconcile`) — cheap, and it inherits the same protection the
daily cycle's step 2 has: a prior crash between placing and recording an
order halts the *next* run instead of compounding silently. `apply_sell`
(`paper.py:202`) supports partial fills and fully removes a closed position
from `ledger.positions`, so a correctly-recorded sell makes `check_stops()`
naturally idempotent on the next hourly pass — no separate de-dup bookkeeping
needed, as long as every placed order is recorded before the run ends.

### 6.5 Concurrency with the daily Routine — thinner margin than paper's, so retry-then-stop

Paper's `concurrency: group: livetrade-state` is a GitHub Actions queueing
primitive with no equivalent in Claude Code Routines — two Routines are
just two independently-scheduled cloud sessions with no shared lock. But
paper's *schedule* also does most of the real work: its daily cycle runs at
22:30 UTC. The cron's raw last tick is 21:45 UTC (45 min before), but the
in-job guard trims actual execution to 9:30-16:00 ET — 20:00 UTC in EDT —
so the real gap between paper's last EFFECTIVE sweep and its daily cycle is
~150 minutes in EDT (~90 in EST, since paper's daily cron is fixed-UTC
while the guard is ET wall-clock; either figure dwarfs the raw 45).
Genuinely disjoint in practice either way, which is why a real collision
has essentially never happened.

**Live's daily cycle actually runs post-close, not in RTH — correcting
this RFC's own earlier premise.** The settled-bar guard requires the bar
to be settled (16:15 ET) before the daily cycle can act on anything, so
it must run *after* the close — ~4:45pm ET in practice, not the 3:45pm ET
this RFC originally assumed (see the corrected "Picking the time" section
in `docs/AUTONOMOUS_LIVE_ROUTINE.md`). That puts the daily cycle *outside*
this Routine's own market-hours sweep range (9:30am-3:30pm ET), not inside
it — a ~75-minute gap from the last intraday check (15:30) to the daily
cycle (~16:45), comparable to paper's own effective gap rather than the
razor-thin one this RFC first argued. The collision
risk is real but lower-probability than originally stated here; it isn't
zero, since either Routine's actual run time can drift from its nominal
schedule — this account's *own* daily cycle already drifted once, from a
documented 3:45pm ET to an actual 4:45pm ET, unnoticed until this session
traced a ledger-drift bug back to it. So the retry-then-stop design in D3
below still stands, on more honest grounds: not because a collision is
likely, but because the cost of getting a rare one wrong (an unrecorded
real order) is asymmetric, and the fix is cheap and safe regardless of
how often it's ever actually needed.

The consequence that matters: if the new Routine's `git push` is rejected
(non-fast-forward, because the daily cycle pushed first), and it just
*stops*, per the daily Routine's own "never retry a rejected push" rule —
a **real broker order that already executed** goes unrecorded in the
ledger. That's a materially worse outcome than the daily Routine's own
version of this scenario, where "stop and report" just means a paper-safe
delay. So the new Routine's push handling **should deliberately diverge**
from the daily Routine's:

1. On a rejected push, run `git pull --rebase` and retry — bounded (e.g. 3
   attempts, mirroring `intraday-stops.yml`'s own retry loop exactly).
   This is **not** a force-push and does not conflict with the no-force
   rule: it replays the Routine's own local, not-yet-shared commit on top
   of the new remote tip, then pushes normally (fast-forward). It never
   rewrites a commit anyone else has already seen.
2. If the rebase hits an actual content conflict (both Routines touched
   the same lines of `live_ledger.json` in the same window) — do not
   attempt to resolve it. `git rebase --abort` (safe: it only undoes the
   Routine's own local, unpushed rebase attempt), then stop and report,
   naming explicitly that a real order executed but could not be
   persisted this run — so a human, or the next reconcile, catches and
   fixes it rather than it silently vanishing.

This is the one place this RFC asks for behavior that differs from an
already-hardened rule elsewhere in the pipeline, so it's called out as its
own decision in §9 rather than assumed.

### 6.6 Step 8's fate

Given §2.1, step 8 as currently written will fail, identically, every
single day — it is not "unattended-friendly," it is a guaranteed failure
that burns tool calls and clutters the report for zero benefit, and the
new Routine gives strictly better coverage than step 8 could have provided
even if GFD had been accepted (§2.2). §9 asks for an explicit decision
rather than removing it unilaterally, since real engineering effort went
into hardening step 8's verification logic and the user may want a
periodic (not daily-automated) manual retest preserved in case Robinhood's
fractional-order policy ever changes.

---

## 7. Interaction with existing protection (no coverage gap, no double-count)

- **Daily cycle's settled-close exits** are unchanged and remain the
  authoritative once-daily decision (§5). The new Routine's hourly checks
  fill the gaps *between* those decisions; they don't replace or race them,
  because a closed position simply disappears from `ledger.positions` and
  stops being evaluated by either path.
- **Take-profit exits** were never blocked by the fractional-stop-order
  restriction in the first place — `check_stops()` firing a take-profit
  exit is a Bonito-side *decision* (like any other exit), not a broker
  stop *order*. The new Routine's real-market-sell mechanism handles both
  stop-loss and take-profit triggers identically; there is no separate
  take-profit problem to solve.
- **The kill switch never blocks exits.** `generate_intents` flattens every
  position in the same cycle a drawdown halt trips (`live_runner.py:293
  -316`), before the halted-check that blocks further *entries*
  (`:318-320`) is even reached — so by the time any later run (daily or
  intraday) sees `ledger.halted`, there is nothing left to protect. The new
  Routine calling `bonito live preflight` (recommended, §9 D4) is
  defense-in-depth for a live/live_enabled misconfiguration or a stale data
  feed, not a load-bearing exit-coverage check.
- **The still-open queued-order-reconciliation gap (§3)** is not fixed by
  this RFC. It's a daily-cycle, entry-side problem (orders placed outside
  a live session queuing past cycle-time); the new Routine's strictly
  market-hours schedule means its own sells should always resolve
  same-cycle, so it doesn't add new exposure to that gap — but it doesn't
  close it either.

---

## 8. Test plan

1. **Mode-parameterized `check_stops`/`sweep` test.** Existing coverage
   (`tests/test_live_runner.py`) exercises this path, but confirm it's
   parameterized on a live-mode `UniverseConfig` fixture specifically, not
   only paper — the "no code change needed" claim in §4 should be backed
   by a test, not just a read of the source.
2. **`--execute` non-interaction for live.** Assert `bonito live sweep
   -u <live-config>` (no `--execute`) writes an intents file on a synthetic
   triggered stop and does **not** touch `ledger.positions` itself
   (confirming detection and execution stay decoupled for live, the same
   way step 5/6 are decoupled in the daily cycle). Plus: a preflight
   `--exits-only` unit test (empty store passes; kill switch / live-flag
   still abort) — DONE this pass (`TestPreflight`).
3. **Rebase-retry unit coverage** for the push-conflict handling in §6.5:
   a clean fast-forward-able divergence retries and succeeds; a genuine
   content conflict aborts cleanly and reports rather than guessing.
4. **Idempotency check**: after a recorded sell removes a position from
   `ledger.positions`, a second `check_stops()` pass over the same (now
   closed) symbol produces no intent — confirms §6.4's "no separate de-dup
   needed" claim rather than assuming it.
5. **Dry run against the live ledger**, no order placement
   — confirms `bonito live sweep -u config/universe.live.json` behaves as
   described in §4 against the real current 6-position book before any
   Routine is wired up.
6. **Dogfood the Routine itself** the same way the daily one was validated:
   create it, run it manually ("Run now") while watching, against a
   scenario with no positions or with `live_enabled: false` first, before
   trusting the schedule.

---

## 9. Decisions

All four proceeding per the stated recommendation (2026-07-21) — see the
Status line above for what "resolved" means here.

**D1 — Step 8's fate: DROPPED.** Removed the daily broker-side
stop-order attempt from the unattended prompt entirely (§6.6) — it now
fails deterministically every cycle, so keeping it would just be a
guaranteed-fail daily attempt. `docs/AUTONOMOUS_LIVE_ROUTINE.md`'s step 8
is gone (steps renumbered), its "Intraday stops under a Routine" section
rewritten to point at this RFC's mechanism, and a standing "retest if
Robinhood's fractional-order support ever changes" follow-up is logged in
`docs/EXPERIMENT_LOG.md` instead.

**D2 — Last intraday run at 3:30pm ET (revised 2026-07-23).** The last
run lands at 15:30 ET — the last half-hour slot whose triggered market
sell still fills before the 4pm close — leaving ~75 minutes clear of the
post-close daily cycle (~16:45 ET). Earlier drafts stopped at 2:30pm,
a leftover from the since-corrected assumption that the daily cycle ran
at 3:45pm and needed a wide buffer before it; with the daily cycle
actually post-close, that extra hour of coverage (2:30–3:30) is free.
See `docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md`'s Setup section. The only
intraday-blind window is the last 30 minutes (3:30–4:00pm), caught by the
daily cycle's own settled-close exit — granularity, not a gap.

**D3 — Push-conflict handling divergence: ADOPTED.** The new Routine
retries via bounded `git pull --rebase` (3 attempts) before stopping on a
rejected push, deliberately different from the daily Routine's
stop-immediately rule, because giving up here can orphan an
already-executed real order. Does not touch the daily Routine's own rule
or the no-force-push branch protection.

**D4 — Preflight as defense-in-depth: ADOPTED.** The new Routine calls
`bonito live preflight` every run (step 3) even though §7 shows the
kill-switch check is usually moot for an exits-only path by the time it
would fire — cheap, and still catches a live/live_enabled
misconfiguration or a stale data feed independent of the kill switch.

**D5 — DST-proofing via superset cron + ET guard: ADOPTED (2026-07-23).**
claude.ai custom crons are UTC (empirically confirmed — see §6.1), so a
fixed cron drifts an hour across the EDT/EST boundary. Rather than a
twice-a-year manual cron edit, the cron is a UTC superset
(`30 13-20 * * 1-5`) and an in-prompt guard (`bonito live market-hours` →
`in_intraday_sweep_window`) trims stray firings to the real weekday
9:30am–15:45 ET window. Full rationale, the 15:45-vs-15:30 stagger slack,
and the both-seasons arithmetic are in §6.1. Same superset-cron + ET-guard
pattern as paper's `intraday-stops.yml`.

---

## 10. Rollout & gating

1. ~~Resolve §9 (user).~~ Done 2026-07-21 — proceeding per recommendation
   on all 4 (see Status line).
2. ~~Write the new Routine prompt~~ Done —
   `docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md`, and
   `docs/AUTONOMOUS_LIVE_ROUTINE.md` step 8 removed (steps renumbered)
   with its "Intraday stops under a Routine" section rewritten per D1.
3. **Still open — §8 tests 1–4** (mode-parameterization, decoupling,
   rebase-retry, idempotency): not yet written. This RFC's "no new
   `src/bonito` code needed for detection" claim (§4) is backed by
   reading the source, not yet by a test asserting it against a
   live-mode fixture — do this before fully trusting the mechanism.
4. **Still open — §8 test 5**: a dry run of `bonito live sweep
   --no-refresh -u config/universe.live.json` against the real live
   ledger, no order placement, to confirm current behavior matches §4's
   description before the Routine is created.
5. **User, manual**: create the Routine per
   `docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md`'s Setup section; §8 test 6
   (dogfood) happens here via "Run now."
6. Once clean: get all 8 currently-open positions (grew from 6 to 8
   since this RFC was first drafted — see `docs/EXPERIMENT_LOG.md`
   2026-07-21) their first real coverage under the new mechanism.
7. Log the adoption in `docs/EXPERIMENT_LOG.md` once the Routine is
   created and dogfooded — not yet done (a doc existing isn't an
   adoption; a working Routine is).

---

## 11. Touchpoint quick-reference

```
src/bonito/trading/live_runner.py
  :577        check_stops — intraday sweep, mode-agnostic, never generates entries
  :525        compute_stop_levels — resting-order price, not used by the new Routine's core loop
  :293-316    generate_intents kill-switch flatten (fires before the halted-check that blocks entries)
  :318-320    generate_intents halted-check — entries only, exits already computed above it
src/bonito/trading/paper.py
  :202        apply_sell — supports partial fills; fully removes a closed position (idempotency basis)
src/bonito/cli.py
  live_sweep    intraday MUST refresh (open positions only) — the container's DuckDB
                is empty (gitignored, ephemeral); --no-refresh was a design bug, fixed 2026-07-23
  live_preflight  --exits-only skips the stored-bar data checks for the intraday path
  _sweep_stops  --execute is paper-gated by design; live never needed it
  live_stop_levels  compute_stop_levels' CLI surface, informational only here
docs/AUTONOMOUS_LIVE_ROUTINE.md
  step 8      REMOVED per D1 (steps renumbered 9->8, 10->9); "Intraday
              stops under a Routine" section rewritten to point at
              docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md instead of this RFC
docs/AUTONOMOUS_INTRADAY_LIVE_STOPS.md
  the new Routine's prompt, built per this RFC's §6 design and §9 decisions
.github/workflows/intraday-stops.yml
  precedent for cadence/guard/retry shape; concurrency: group has no Routine equivalent (§6.5)
docs/EXPERIMENT_LOG.md
  2026-07-18 (x2), 2026-07-20, 2026-07-21 bug rows + matching
  2026-07-20 Rejected row — the empirical + root-cause basis for this
  RFC and for the daily Routine's corrected schedule guidance
```
