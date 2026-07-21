# RFC: Settled-vs-forming bar guard for the live trading cycle

- **Status:** Draft — awaiting user decision (entry/live-behavior change = human-domain)
- **Author:** orchestrator pass, 2026-06-22
- **Branch:** `claude/determined-shannon-0dhndr`
- **Supersedes/extends:** ARM fill-gap investigation, Decision #3
  (`tasks/arm_fill_gap_coordination.md:199-228`)
- **Implements option:** (b) "harden the code to act only on settled bars"
  — the code-change lever from Decision #3. Option (a) (schedule-only) needs
  no RFC.
- **Addendum (2026-07-21):** the guard proposed here is correct and was
  built as designed — but its interaction with the 3:45pm ET schedule this
  RFC assumed as background context (§1) was more severe than anticipated:
  a fixed schedule time before 16:15 ET means the guard reads the just-
  ingested bar as forming on *every* regular trading day, unconditionally,
  not just on the half-days this RFC's §5.1 discussed. That was confirmed
  empirically (`tasks/todo.md`, 2026-07-13: 6 consecutive days of zero live
  entries) and led to moving the schedule to ~4:45pm ET, which surfaces a
  different, previously-unconnected problem (orders queuing overnight).
  See `docs/AUTONOMOUS_LIVE_ROUTINE.md`'s "Picking the time" section and
  `docs/RFC_INTRADAY_LIVE_STOPS.md` for the current understanding — not
  a correction to this RFC's guard design, only to the schedule assumption
  used as its motivating example.

---

## 1. Summary (TL;DR)

The daily live cycle evaluates strategy signals on `data.closes[-1]` — the
**last bar in the store**. When the cycle runs intraday (the documented live
Routine fires 3:45pm ET, 15 min before the 4pm close), that last bar is a
**forming** bar: yfinance returns a same-day row whose "close" is just the
last trade so far, not the settled session close. The strategies are
close-based, so the cycle can open or close a position off a price the
settled-close strategy — and the weekly research gate that trusts the
settled-close replay — would never act on.

This is the root mechanism behind the ARM/ORCL tracking WARN (confirmed by
4 independent passes to be a *legitimate* divergence today, because it has
only ever fired in a **manual rehearsal**, never an automated run). It is
**prospective**: the moment the live Routine is created as written, every
live trading day inherits it.

**Proposal:** add a settled-vs-forming guard at the **decision layer**
(`generate_intents`) that *skips entries and holds exits* when the latest
bar's trading session has not closed — symmetric with the existing
stale-data guard, and fail-closed. The intraday stop sweep stays exempt by
construction (different call path). `live_enabled` stays `false` until the
full pipeline + sign-off clears it.

---

## 2. Problem — the forming-bar mechanism (exact touchpoints)

| Stage | Code | What happens |
|-------|------|--------------|
| Ingest | `refresh_data`, `live_runner.py:145` | `end = now + 1 day`; `ticker.history(end=…)` fills a **same-day forming bar** (O/H/L-so-far / last-trade-as-Close) when called intraday. Stored under today's date. |
| Staleness guard | `_is_stale`, `live_runner.py:706-707`; `MAX_DATA_AGE_DAYS = 5` (`:32`) | Rejects only bars **older than 5 days**. This is the *inverse* of what we need — it guards against too-**old** data, never too-**fresh** (forming) data. A forming bar dated today passes trivially. |
| Entry eval | `generate_intents` entry loop `live_runner.py:321-349` → `latest_entry_signal`, `signals.py:307-329` (`latest_idx = len(data) - 1`, `:320`) | Entry rules evaluated unconditionally on the last bar. Forming bar ⇒ entry fires on a forming close. |
| Exit eval | `generate_intents` exit loop `live_runner.py:210-238` → `latest_exit_signal`, `signals.py:332-359` (`current_price = data.closes[latest_idx]`, `:345-346`) | Exit rules + stop + TP evaluated on the forming close. |
| Regime filter | `_regime_allows`, `live_runner.py:380-388` | Same `_is_stale`-only check on the regime reference's last bar. |
| Preflight | `_is_stale` uses at `live_runner.py:625, :642` | Fail-closed gate; today checks staleness/outage, not settledness. |

**Net:** there is no point in the daily path that distinguishes a settled
close from a forming one. Decision #3 already traced this end-to-end
(`tasks/arm_fill_gap_coordination.md:179-197`); this RFC verifies it against
current `src/` and proposes the fix.

---

## 3. Scope & non-goals

**In scope:** the daily decision cycle — `generate_intents` (entry + exit
loops) and the regime filter it calls; surfacing the condition in
`preflight`.

**Explicit non-goals:**

1. **The intraday stop sweep is exempt — by construction, not by flag.**
   `live_sweep` → `_sweep_stops` → `check_stops` (cli.py:1105-1171) sources
   prices from `fetch_latest_quotes` (live intraday quotes) and **never
   calls `generate_intents`**. It *wants* intraday prices — that is its job.
   A guard inside `generate_intents` does not touch it. Intraday stop
   protection (sweep + broker-side GTC stops) is unchanged.
2. **The paper GitHub Action is unaffected.** It runs 22:30 UTC (~6:30pm
   ET), 3+ hours post-close, so its last bar is already the settled one. The
   guard is a no-op there (settled ⇒ proceeds normally).
3. **No change to backtest/replay semantics.** Replay already keys off
   settled closes; this RFC makes the *live* path match it, not vice-versa.

---

## 4. Relationship to option (a), the schedule lever

(a) and (b) are **complementary, not either/or**:

- **(a) schedule near the close** shrinks the forming↔settled price gap to
  tick noise but never eliminates it, and silently does nothing if the
  Routine is ever mis-scheduled. Zero code.
- **(b) this guard** makes the cycle *correct regardless of run time*: on a
  forming bar it declines to act rather than acting on a wrong price. It
  also means a future re-schedule can't reintroduce the hazard.

Recommended end state: ship (b) **and** keep the schedule sane. (b) is the
load-bearing safety property; (a) reduces how often (b) has to suppress a
trade.

---

## 5. Design

### 5.1 Detection: is the latest bar settled?

**Definition.** A daily bar dated `D` is **settled** at wall-clock `now`
iff `now_ET ≥ close(D) + finalize_buffer`, where `close(D)` is `D`'s
session close in US/Eastern (16:00 normal, 13:00 on early-close half-days)
and `finalize_buffer ≈ 15 min` (lets the data vendor finalize the bar).
Everything else — including a same-day bar before today's close — is
**forming**.

Note the subtlety Decision #3 flagged (`arm_fill_gap_coordination.md:219-221`):
"reject same-day bars" is **wrong**. After the close the same-day bar *is*
the settled one we want (that's why the paper cron is fine). The guard must
key on **settled vs forming**, never on the calendar day.

Two implementation options — **this is the main thing I need a call on:**

#### Option D1 — ET-clock heuristic, no new dependency (recommended)

Convert `as_of` (UTC, tz-naive) → US/Eastern via stdlib `zoneinfo`
(`tzdata` is the only possible add, and only on bare distros). Treat
`close(D)` as **16:00 ET always** — ignore half-days. Settled iff
`now_ET ≥ 16:15 ET on D`.

- **Pro:** no third-party dep; ~15 lines; trivially testable with a frozen
  clock.
- **Con (and why it's safe):** on the ~9 half-days/year, a bar that settled
  at 13:00 is treated as forming until 16:15. Effect = the daily cycle
  *skips trading on that half-day if run between 1pm–4:15pm ET*. That is a
  **missed opportunity, never a wrong action** — the error is always toward
  "don't trade," which is the safe direction. Refine later with a half-day
  list if it ever matters.

#### Option D2 — exchange calendar dependency

Add `exchange_calendars` (or `pandas_market_calendars`) and ask it for the
exact `session_close(D)`, half-days and holidays included.

- **Pro:** exact; no half-day blind spot.
- **Con:** a new runtime dependency and its transitive weight, for a
  correctness gain (trade on half-days between 1–4pm) that is marginal for a
  once-daily cycle. More surface for the fail-closed path to handle if the
  calendar data is stale/unavailable.

**Recommendation: D1.** The half-day gap is a benign missed-trade, not a
risk; we can graduate to D2 if half-day trading ever becomes material. Both
options must verify the **actual tz of stored Yahoo daily timestamps**
during the build (tz-naive UTC midnight vs naive ET midnight changes the
`D` boundary by hours) — a load-bearing build-time check, called out in the
test plan.

### 5.2 Placement: decision layer, not ingest

Guard goes in **`generate_intents`**, *not* in `refresh_data`:

- Dropping the forming bar at ingest would starve the **sweep**, which
  legitimately needs the freshest intraday bar/quote for ATR + stop checks.
- The forming row landing in the store is harmless: replay/tracking already
  key off settled closes, and the next post-close ingest overwrites today's
  row with final values.
- "What bar may I act on?" is a decision-layer question. Keep it there.

Concretely: a helper `_is_forming(last_bar, as_of) -> bool` (sibling to
`_is_stale`), checked in both the entry loop (`:325`) and exit loop
(`:214`) right beside the existing stale check, plus the regime filter
(`:384`).

### 5.3 Behavior on trigger (fail-closed)

| Path | On forming latest bar | Rationale |
|------|----------------------|-----------|
| Entry | **Skip** (like stale ⇒ `:326`) | Never open off a forming price. |
| Exit | **Hold** (like stale ⇒ `:215`) | Don't fire a stop/TP on an intraday print that may reverse by the close. Intraday protection is the **sweep's** job, not the daily cycle's — so holding here is consistent, not a protection gap. |
| Regime ref forming | **Treat risk-off** (mirror `:386-387`) | Same conservative default already used for stale regime data. |
| Clock/tz resolution fails | **Treat as forming ⇒ skip/hold** | Fail-closed, matching preflight philosophy. |

**Preflight** (`:625, :642`) additionally surfaces "latest bar not settled
(forming)" in its report so a human/Routine sees *why* the cycle declined —
without necessarily hard-failing (a forming bar pre-close is expected, not
an outage). Whether it should be a hard preflight FAIL or a soft WARN is an
open question (§8).

### 5.4 API shape

```python
def _is_forming(last_bar: datetime, as_of: datetime) -> bool:
    """True if last_bar's trading session has not settled at as_of."""
    # D1: now_et = as_of(UTC) -> US/Eastern; settled iff now_et >= 16:15 ET on last_bar's date
```

`generate_intents` gains no new required argument; the guard is internal.
If a caller ever needs the old behavior, add `require_settled: bool = True`
rather than branching on `universe.mode` — keep paper and live on the same
code path (paper-vs-replay fidelity is the whole point).

---

## 6. Interaction with intraday protection (no exit-coverage gap)

A reader will worry: "if the daily cycle holds exits on forming bars, are
stops unprotected intraday?" No:

- **Intraday stop sweep** (`intraday-stops.yml`, every 15 min RTH) runs
  `check_stops` on **live quotes** — fully intraday, fully exempt from this
  guard.
- **Broker-side GTC stop orders** protect 24/7 independent of any session.

The daily cycle's exits are the *settled-close* exit rules; deferring those
to the settled close is correct, and is exactly what the replay does.

---

## 7. Test plan

1. **`_is_forming` unit table** (frozen clock, synthetic timestamps):
   pre-close same-day ⇒ forming; post-close same-day ⇒ settled; prior
   trading day ⇒ settled; weekend/after-hours ⇒ settled on Friday's bar;
   the 16:00–16:15 buffer window ⇒ forming. CI-deterministic, no live
   DuckDB.
2. **`generate_intents` integration**: synthetic store with a forming last
   bar ⇒ **zero entry intents**, open positions **held** (no exit intent);
   same store with `as_of` advanced past the close ⇒ the entry/exit fires.
   Reuses the synthetic-data style of `tests/test_tracking.py::TestMatchFills`.
3. **Sweep regression**: assert the sweep path still produces stop intents
   on a forming bar (proves the exemption holds — the guard must NOT bleed
   into `check_stops`).
4. **Build-time tz check** (load-bearing): a test asserting the stored Yahoo
   daily timestamp for a known date maps to the expected ET session, so the
   `D` boundary is correct. If this reveals tz-naive-ET vs UTC, the helper
   adjusts before anything else lands.
5. **Non-vacuous proof**: mutate the guard to a no-op and confirm tests 1–2
   fail (per the project's characterization-test discipline).

---

## 8. Decisions (resolved 2026-06-23 — user sign-off)

1. **Detection mechanism: D1** (ET-clock heuristic, stdlib `zoneinfo`, no
   new dependency). The half-day blind spot is accepted as a benign
   missed-trade, never a wrong action.
2. **Build order: both in this pass.** Build the settled-bar guard (full
   Planner→Builder→Tester→Validator pipeline) AND fix the live Routine's
   documented schedule time in the same pass — the RFC's recommended end
   state (§4). `live_enabled` stays `false` until the pipeline clears.
3. **Preflight severity: soft WARN.** The cycle still runs; the per-symbol
   guard in `generate_intents` suppresses the unsafe entries/exits;
   preflight's report notes why, it doesn't hard-fail.

Next: dispatch the 4-role pipeline in a new coordination doc
(`tasks/settled_bar_guard_coordination.md`) to implement §5 against
`live_runner.py`/`signals.py`, per §7's test plan.

---

## 9. Rollout & gating

1. Approve this RFC + answer §8.
2. Strict 4-role pipeline (Planner → Builder → Tester → Validator), one
   coordination doc, orchestrator the sole writer — same discipline as the
   ARM investigation and Phases 1–2.
3. `live_enabled` remains `false` throughout; merged behind the existing
   pre-live checklist (`tasks/todo.md`).
4. Log adopted/rejected in `docs/EXPERIMENT_LOG.md`; record the lesson in
   `tasks/lessons.md`.

## 10. Touchpoint quick-reference

```
src/bonito/trading/live_runner.py
  :145        refresh_data — end=now+1d ⇒ forming same-day bar ingested
  :32,:706    MAX_DATA_AGE_DAYS=5 / _is_stale — old-data guard (inverse of need)
  :210-238    generate_intents exit loop  (add _is_forming hold)
  :321-349    generate_intents entry loop (add _is_forming skip)
  :380-388    _regime_allows — regime ref staleness (mirror for forming)
  :625,:642   preflight _is_stale uses (surface forming bar)
src/bonito/trading/signals.py
  :307-329    latest_entry_signal — latest_idx=len(data)-1
  :332-359    latest_exit_signal  — current_price=closes[latest_idx]
src/bonito/cli.py
  :1105-1171  live_sweep/_sweep_stops — EXEMPT (live quotes, no generate_intents)
```
