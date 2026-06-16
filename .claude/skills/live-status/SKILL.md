---
name: live-status
description: One-shot account health check — trailing performance (1D/1W/inception vs SPY), open positions, fidelity tracking, and safety flags. Read-only, no trading.
allowed-tools: Read, Bash, Grep
---

# Live Status Skill

A read-only snapshot of the trading account: how it's done, what's open,
whether the simulation can still be trusted, and whether anything is
wrong. This never places or modifies a trade — it only reports.

## Usage

```
/live-status              # paper account (default)
/live-status live         # live account (-u config/universe.live.json)
```

## Steps

0. **Setup**:
   ```bash
   [ -d .venv ] || python3.12 -m venv .venv && .venv/bin/pip install -e "." --quiet
   ```
   No `git pull` needed — this is read-only and doesn't touch `livetrade/`.

1. **Refresh prices** (skip if data was refreshed in the last few minutes
   this session):
   ```bash
   .venv/bin/bonito live refresh [-u config/universe.live.json]
   ```

2. **Performance** — the headline numbers:
   ```bash
   .venv/bin/bonito live performance [-u config/universe.live.json]
   ```
   Reports trailing 1D / 1W / since-inception returns against SPY (with
   alpha in points), realized + unrealized P&L, win rate, profit factor,
   the closed-trade log, and current open positions marked at live quotes.
   1W is omitted automatically until there are 6+ trading days of history
   — that's expected, not a bug.

3. **Safety flags** — anything that would block new trading:
   ```bash
   .venv/bin/bonito live preflight [-u config/universe.live.json]
   ```
   Non-zero exit = kill switch latched, a `live`/`live_enabled` mismatch,
   or a total data outage. Report this verbatim if it fails; do not try
   to fix it as part of a status check.

4. **Fidelity** — is the backtest still trustworthy:
   ```bash
   .venv/bin/bonito live tracking [-u config/universe.live.json]
   ```
   `OK` = trust the replay numbers. `INSUFFICIENT` = not enough matched
   fills yet, not a problem. `WARN` = paper is diverging from replay;
   flag it, don't act on it without the user.

5. **Summarize** in this shape:
   - Equity + 1D/1W/inception returns vs SPY (alpha in points)
   - Open positions with live unrealized P&L
   - Closed-trade win rate / profit factor (call out small-sample-size
     caveats below ~20 trades — a hot streak is not validation)
   - Preflight status (only mention if NOT clean)
   - Tracking status (OK silently noted; WARN/INSUFFICIENT called out)
   - One forward-looking note: what changes the picture next (e.g. "2-week
     tracking review lands on <date>", "ORCL is the first position testing
     the stop on a drawdown")

## Notes

- This is intentionally narrower than `/robinhood-trade status` — it adds
  the period-return/benchmark math (`bonito live performance`,
  `src/bonito/trading/performance.py`) and the safety/fidelity gates in
  one pass, for "how are we doing" questions rather than the trading cycle.
- Never read more into a short win streak than the sample supports — the
  account backtest's true win rate is ~48%; early 100% streaks regress.
- If asked to also execute trades or sweep stops, hand off to
  `/robinhood-trade` — this skill stays read-only.
