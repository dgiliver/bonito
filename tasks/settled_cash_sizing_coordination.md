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
| P | Planner | file:line diff + test plan | ✅ done | plan verified (see below) |
| B | Builder | implement plan | ✅ done | 3832f6a |
| T | Tester | write non-vacuous tests | ✅ done | d84d3c1 |
| V | Validator | independent PASS/FAIL | ✅ **PASS** | all 7 claims re-derived |

## Planner output (verified by orchestrator)

Spot-check PASSED: `available` (the variable) is read only at `live_runner.py:334/368/412`, all inside the buy loop (`for symbol in universe.symbols:` @349); lines 478/496 are the English word. **Exits (242–278) never touch it → cap cannot gate exits.** Call sites confirmed: `cli.py:1007`=`live_signals` (leave), `cli.py:1062`=`live_run` (modify).

Planner corrections folded in:
- The CLI command is **`live_signals`** (the `signals` cmd @1007), NOT `live_generate` — leave untouched.
- Typer option must be bare **`float = typer.Option(None, …)`** (cli.py has no `from __future__ import annotations`; mirror the `--dollars` idiom @1606), not `float | None`.
- The one-line ternary is 102 chars → use the `ruff format`-canonical wrapped form.
- Do **NOT** renumber `AUTONOMOUS_LIVE_ROUTINE.md` steps (cross-referenced throughout) — fold the `get_portfolio` fetch into step 7 prose; also add "one get_portfolio" to the tool-call preamble @193.
- `position_pct_equity` composes for free: `available` is already inside `min(target, max_position_usd, available)` @368 — lowering it can only lower `dollar`.
- Replay (`portfolio_backtest.py:282`, keyword args) + `live_signals` never pass the param → both stay None/byte-identical. Builder must NOT thread it into the replay.

Touchpoints: `live_runner.py` sig 207–213 + `available` 330–334; `cli.py` `live_run` sig 1028–1032 + call 1062; `docs/AUTONOMOUS_LIVE_ROUTINE.md` step 7 @287–289 + preamble @193; tests → `TestGenerateIntents` @107 (fixtures `universe`@82, `uptrend_store`@102, `_open_position`@697, `AS_OF`@29).

## Run log

- **44fb078** base (main tip). Branch created, venv rebuilt with `[dev]`, `pytest tests/test_live_runner.py` = 105 passed. Coordination doc committed (**bc219dc**). Planner dispatched.
- **Planner returned + spot-checked (PASS).** Load-bearing claim (exits-never-gated) independently grep-verified. Plan + corrections folded above. Builder dispatched with the plan embedded verbatim.
- **Builder returned; orchestrator reviewed diffs directly.** Builder's `ruff format` had normalized ~7 pre-existing unrelated lines (reconcile/resolve_pending/read_cycle_lock in live_runner; 4 console.print/qty_label in cli). To keep the PR surgical I reverted both `.py` files to main and re-applied only the 5 intended edits by hand; the doc edit kept as-is. Result: `git diff --stat` = 3 files, +33/−8. `ruff check` clean; none of the new lines appear in `ruff format --diff`; `import bonito.cli` OK. Full fast suite: **917 passed, 8 skipped, 1 failed**. The 1 failure (`test_trailing_stops.py::…test_full_flow_create_and_backtest_trailing`) is **pre-existing + unrelated**: fails identically on clean main (verified by stashing), references none of the changed code, and fails on `No data found for SPY. Run 'bonito ingest SPY'` — an empty-DuckDB env/data-setup issue, not a regression. Implementation committed **3832f6a**. Tester dispatched.
- **Tester returned; orchestrator re-verified non-vacuity independently.** 5 tests added to `TestGenerateIntents`. Tester again triggered the whole-file `ruff format` drift (7 pre-existing hunks in the test file); I reverted the test file to main and re-inserted ONLY the 5-test block → surgical **1 hunk, +81, 0 reformatting**; my block confirmed format-clean via `ruff format --diff`. I independently reproduced the mutation proof: forcing `spendable = ledger.cash` reddens `test_settled_bp_below_cash_caps_dollar_amount` + `test_settled_bp_below_min_order_skips_all_buys`; restore → 5 green. `ruff check` clean; `tests/test_live_runner.py` **105 → 110 passing**; `git status` shows src clean. Tests committed **d84d3c1**. Validator dispatched.
- **Validator returned: PASS.** All 7 claims independently re-derived from source (not the doc): (1) exits never gated — proven by exhaustive `available`/`spendable` occurrence classification AND a fault-injection (gated exit on `settled_bp==0` → test E caught it); (2) paper byte-identical + all non-CLI call sites pass None (ran test_settled_bar_guard/live_fidelity/portfolio_backtest → 72+14 pass, no regression); (3) monotonic composition with `position_pct_equity`; (4) no human-only file touched (`git diff` on config/strategies empty); (5) teeth reproduced (B/D red under cap-drop mutation); (6) CLI wiring real + imports; (7) 110 pass, ruff clean, diff surgical (independently verified pre-existing format debt is identical on base 44fb078). **Non-blocking finding:** test A (`test_settled_bp_none_is_identical_to_current`) is logically redundant with existing coverage — documentation-value only, not an independent regression guard. Decision: KEEP (explicit named contract assertion for the None path; harmless). No FAIL items → no role loop needed.

## Phase 1 CLOSEOUT

**Validator PASS.** Implementation `3832f6a` + tests `d84d3c1`, both surgical, on `claude/settled-cash-sizing`. Branch diff vs `44fb078`: 4 code/doc files, +114/−8, 8 additive hunks. Residual caveat: test A is documentation-only (Validator finding, accepted). Next: Phase 2 — push branch, open PR, gated `pr-reviewer` loop → ACCEPTABLE → merge.
