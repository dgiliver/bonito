# Live-vs-paper fidelity — 4-role coordination

**Task**: implement `docs/RFC_LIVE_FIDELITY.md` §5 (design) + §7 (tests) per the
resolved §8 decisions, via the strict 4-role pipeline (no role does another's
job; orchestrator is sole writer of this doc).

## Resolved decisions (RFC §8, user sign-off 2026-06-29)
- **D1 = hard-halt** new entries on ledger-vs-broker drift > 0.5% of a position's
  shares (fail-closed; exits/flatten ALWAYS allowed).
- **D2 = keep 50 bps** mean live-vs-replay band; always surface worst-fill bps.
- **D3 = record actual broker qty + `no_fill`** (ledger matches broker by
  construction; partial fills and rejections logged explicitly).
- **D4 = log-only** settlement/buying-power check.
- **D5 = strengthen the go-live gate** (≥2 wks green live-vs-replay at 1-share,
  reconcile clean each cycle) — a `tasks/todo.md` update, not code.

## Hard constraints (non-negotiable)
- **Human-only, never touched:** `config/universe.live.json` /
  `config/universe.json` `mode`/`live_enabled`/risk caps, and `strategies/*.json`.
  This pipeline changes execution/account-management *plumbing*, not policy.
- **Exits are NEVER gated.** The drift gate (D1) blocks only NEW entries; a
  flatten/exit/stop must always be allowed (mirror the entry-blocklist /
  settled-bar pattern).
- **Do not break paper mode.** The daily paper automation runs `execute_paper`;
  the drift gate and `no_fill`/actual-qty recording are live-mode concerns and
  must be guarded so paper behaves exactly as today (the determinism + tracking
  tests must stay green).
- The fidelity *engine* already exists (tracking is ledger-agnostic; reconcile /
  record-fill / preflight exist) — extend and gate it, don't rebuild it.

## Roles & sequencing (strict)
1. **Planner** (`architect`, read-only): re-verify the RFC §10 touchpoints
   against current `src/` (preflight/`PreflightReport`/`reconcile_positions`;
   `record-fill`/`execute_paper`/`PaperLedger`; `tracking.py` thresholds;
   `generate_intents` equity marking). Produce the file:line-exact diff plan +
   the §7 test plan, decide how broker positions reach the drift gate (param vs
   a reconcile step before preflight), and flag the paper-mode-safety guards.
   NO code.
2. **Builder** (`backend-dev`): implement the plan — D1 drift gate in preflight,
   D3 actual-qty + `no_fill` in record-fill/ledger, D2 mode-aware tracking band,
   real-price kill-switch marking (fail-closed on missing price), D4 log-only
   note, D5 `tasks/todo.md` gate update. Owns `src/` + the touched docs.
3. **Tester** (`tdd-developer`): the §7 test plan — drift gate (ok / fail-closed /
   exits-still-allowed), fill recording (partial qty, `no_fill`, ledger==broker),
   kill-switch marking (missing price → fail-closed, no entry_price fallback),
   live-vs-replay threshold WARN, reconcile property. Non-vacuous. Tests only.
4. **Validator** (`code-reviewer`, read-only): independently re-verify; confirm
   exits are never gated, paper mode is unchanged (determinism + existing
   tracking tests green), no human-only file touched, tests non-vacuous,
   ruff/full-suite clean. PASS/FAIL, itemized. Does NOT fix.

## Task table
| ID | Role | Task | Status | Result |
|----|------|------|--------|--------|
| F-1 | Planner | Re-verify RFC touchpoints; file:line diff plan + test plan; broker-positions-into-gate design; paper-safety guards | architect | done | RFC line numbers all accurate. **Key design (orchestrator-verified):** broker positions reach the D1 gate via the EXISTING `bonito live reconcile` step (the Routine already runs it fail-closed before preflight/run; `cli.py:1207` already exits 1 on drift) — so D1 is a refinement (0.5%-tolerance + `fatal_drift`/`reconcile_gate`, entry-only) NOT new plumbing; `preflight` stays broker-data-free. Kill-switch fail-closed goes in `generate_intents` (live-gated `LivePricingError`), NOT `equity()` (verified on the replay path `portfolio_backtest.py:302` → must stay byte-identical). D3: kw-only `fill_quantity=None` on apply_buy/sell + zero-qty `no_fill`; record-fill calls apply_buy/sell directly (execute_paper untouched). D2: `MAX_MEAN_FILL_BPS_LIVE=50` mode-aware band + zero-qty filter. 10 enumerated paper-safety guards; non-vacuous §7 test plan (incl. the monkeypatch test that's the only real proof of mode-awareness given equal bands). Orchestrator confirmed the 3 linchpins (reconcile-already-gates, equity-on-replay-path, apply_sell-ignores-intent.quantity). |
| F-2 | Builder | Implement §5 (D1-D4) + D5 todo update | backend-dev | done | Implemented all 5 decisions. D1: `fatal_drift`/`fatal_reasons` on a 0.5%-of-larger-leg tolerance + dust floor, `reconcile_gate`, CLI 3-branch fail-closed (hard-halt on fatal, warn+exit0 on sub-tolerance). D3: kw-only `fill_quantity` (default None → byte-identical), partial sells, `record_no_fill` (zero-qty fill), record-fill `--shares/--no-fill` calling apply_buy/sell directly. D2: mode-aware band (=50), `no_fill_count`, zero-qty excluded. Kill-switch: `LivePricingError` in generate_intents (live-gated, before equity()); `equity()` untouched. D4 log-only note; D5 todo gate. **Orchestrator verified directly:** execute_paper/preflight/equity defs NOT in the diff; kill-switch + D4 are `mode=="live"`-gated; D1 math sound; 123 passed across the 5 changed-surface test files (paper byte-identical); ruff clean; config/strategies untouched. Committed `205bb28`. |
| F-3 | Tester | §7 test plan, non-vacuous | tdd-developer | done | `tests/test_live_fidelity.py` — 27 tests across all 6 groups (drift gate incl. exits-not-gated structural guard + CLI 3-branch; fill recording incl. ledger==broker; zero-qty tracking; kill-switch live/paper pair; the monkeypatch band test; reconcile boundary). Non-vacuity demonstrated by mutation for the drift boundary, kill-switch live-gate, and band mode-awareness (RED with bug / GREEN after revert). Suite 873 passed; ruff clean. **Orchestrator independently reproduced** the drift-boundary non-vacuity (`>`→`>=` → boundary test RED, revert → green) and read the exits-not-gated test directly. Committed `57d2734`. |
| F-4 | Validator | Independent re-verify; PASS/FAIL | code-reviewer | done | **PASS** (all 9 items). Independently: computed the D1 math by hand (boundary strict-`>` exact at 1.0==0.005*200), confirmed `execute_paper`/`preflight`/`equity` defs untouched via `git diff 205bb28^..205bb28`, traced exits-never-gated (check_stops has no broker param / no reconcile call; the exit loop precedes the new D1 code), reproduced mutations (a) drift `>`→`>=` and (b) kill-switch guard removal (RED/GREEN). 873 passed, ruff clean, tree clean, no human-only file touched. Two non-blocking notes: a loose test assertion (orchestrator tightened → `sub-tolerance`+`drift`) and `reconcile_gate` duplicating the drift loop for non-default tolerances (tech debt; deferred to the review loop). |

## Run log
- Orchestrator: drafted `docs/RFC_LIVE_FIDELITY.md`; user resolved all 5 §8
  decisions to the recommended options and said "let's do it". Created this doc;
  dispatching Planner (F-1). Live config / live_enabled / risk caps human-only
  throughout; exits never gated; paper mode must stay byte-identical.
- Planner (F-1) done; orchestrator verified the 3 linchpins (reconcile already
  gates fail-closed pre-run; equity() on the replay path; apply_sell ignores
  intent.quantity). Builder (F-2) done; orchestrator verified the determinism
  surfaces are untouched, the new logic is live-gated, and 123 changed-surface
  tests pass (paper byte-identical). Committed `205bb28`. Dispatching Tester
  (F-3) for the §7 non-vacuous regression plan.
- Tester (F-3) done: 27 non-vacuous tests, suite 873 passed, ruff clean.
  Orchestrator independently reproduced the drift-boundary non-vacuity and
  confirmed the exits-not-gated structural guard is real. Committed `57d2734`.
  Dispatching Validator (F-4) for the final independent PASS/FAIL.
- Validator (F-4) done: **PASS**, all 9 items re-derived from scratch. Two
  non-blocking notes; orchestrator tightened the one loose test assertion,
  deferred the `reconcile_gate` dedup to the review loop.
- **Pipeline complete. All 4 roles done, Validator PASS.** RFC_LIVE_FIDELITY §5
  shipped: D1 drift gate (fail-closed, entry-only), D3 actual-qty + no_fill, D2
  mode-aware band, kill-switch real-price fail-closed, D4 log-only note, D5
  go-live gate. Paper byte-identical; exits never gated; live config /
  live_enabled / risk caps untouched. Commits: `205bb28` (impl), `57d2734`
  (tests), + closeout. Next: `/review-loop` the branch, then it gates the
  go-live rehearsal (RFC §9).
