# Settled-Cash Sizing — 4-Role Pipeline Coordination

**Branch:** `claude/settled-cash-sizing` (from `main` @ 44fb078)
**Orchestrator:** main session (sole writer of this doc, sole committer)

## Task statement

In live mode, `generate_intents()` sizes buys from `ledger.cash`
(`src/bonito/trading/live_runner.py:~334`). The paper ledger books sale proceeds
as cash immediately, but a Robinhood **cash** account holds them **unsettled
(T+1)** — so the routine generates buys the broker rejects
(`EQUITY_NOT_ENOUGH_BP`): 15 blocked buys across ~40% of trading days, which also
corrupts paper-vs-replay tracking fidelity. **Fix:** cap live buy sizing by the
broker's real settled buying power, passed in from the routine.

## Touchpoints (to be re-verified by Planner against current `src/`)

| File | Change |
|------|--------|
| `src/bonito/trading/live_runner.py` | `generate_intents()` gains `settled_buying_power: float \| None = None`; caps `available` when provided |
| `src/bonito/cli.py` | `live run` (`live_run`) gains `--settled-buying-power` flag, passed through; `live_generate` + replay untouched |
| `docs/AUTONOMOUS_LIVE_ROUTINE.md` | step 7: routine fetches broker settled BP (`get_portfolio.buying_power`) and passes the flag |
| `tests/test_live_runner.py` | new regression + boundary + exits-never-gated tests |

## Hard constraints (every role held to these)

1. **`config/universe*.json` `mode`/`live_enabled`/risk caps are HUMAN-ONLY** — untouched.
2. **`strategies/*.json` HUMAN-ONLY** — untouched.
3. **Exits are NEVER gated** — `settled_buying_power` caps only the entry/buy loop.
4. **Paper mode stays byte-identical** — `settled_buying_power=None` ⇒ current behavior exactly.
5. New behavior is effectively live-only (paper path passes `None`); no risk-cap/mode edits.
6. 100-char lines, `ruff format`/`ruff check` clean, mypy advisory. Full `pytest -m "not slow"` green.

## Roles

1. **Planner** (`architect`, read-only): re-verify touchpoints file:line-exact against current `src/`; produce exact diff plan + test plan; resolve design questions; flag risks. No code.
2. **Builder** (`backend-dev`): implement the plan exactly. Owns `src/` + the doc. No tests, no self-validation.
3. **Tester** (`tdd-developer`): the test plan, non-vacuous (each test must fail if its guard regresses — prove by mutation). Tests only.
4. **Validator** (`code-reviewer`, read-only): independently re-derive every load-bearing claim; reproduce non-vacuity; confirm constraints. PASS/FAIL, itemized. No fixes.

## Task table

| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| P | Planner | file:line diff + test plan | dispatched | — |
| B | Builder | implement plan | blocked on P | — |
| T | Tester | write non-vacuous tests | blocked on B | — |
| V | Validator | independent PASS/FAIL | blocked on T | — |

## Run log

- **44fb078** base (main tip). Branch `claude/settled-cash-sizing` created. Venv rebuilt with `[dev]`; `pytest tests/test_live_runner.py` = 105 passed. Coordination doc committed. Planner dispatched.
