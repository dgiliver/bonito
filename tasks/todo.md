# Full Codebase + Docs Audit (2026-06-18) — tech-lead pass, pending sign-off

Full audit across architecture, backend, frontend, security, docs/CI (5
parallel agent passes + direct verification of the top finding). Nothing
below has been fixed yet — this is the plan, awaiting direction on scope
and the two items that need a product/business decision (flagged ⚠️).
Full findings with file:line and severity rationale are in chat, not
duplicated here in full to avoid making this file worse (see the Medium
finding below about this file's own size).

## Phase 0 — stop-the-bleeding (DONE 2026-06-18)
- [x] RESOLVED: `api/routes/trading.py` `deploy_bot` + `trading/bot.py` (the
      Alpaca path) stays — it's the separate "smart trader" product surface,
      not the personal Robinhood pipeline. Hardened to match the Robinhood
      pipeline's safety architecture: daily-loss kill switch (`TradingBot.
      _check_kill_switch()` — flattens positions + halts on breach, new
      `"halted"` status, only resumable via deliberate human action since
      `resume()` rejects non-`"paused"` bots), a `live_enabled`-style
      human-only flag (`settings.alpaca_live_trading_enabled`, default
      `False`, gated at both the API route and the agent tool with a 403/
      `ToolResult(success=False)`), and a risk-acknowledgment parity fix
      (`DeployBotTool` was missing the `acknowledge_risks` gate the API
      route already had — closed). 9 new tests (5 kill-switch, 4 master-
      switch); full suite 721 passed / 1 skipped / 0 failed.
- [x] Strategy DSL indicator-type allowlist (`backtest/strategy.py:97-117`)
      was decorative — any string fell through to
      `getattr(pandas_ta, indicator_type)` in `indicators.py:68` with zero
      enforcement against `PANDAS_TA_INDICATORS`. `_validate_indicator_type`
      now raises `ValueError` on anything outside `PANDAS_TA_INDICATORS` /
      `ROLLING_INDICATOR_TYPES` / the builtin enum, and
      `_compute_pandas_ta_indicator` re-checks defensively before the
      `getattr` in case a config bypasses pydantic validation entirely.
- [x] RESOLVED: License is Proprietary. Fixed `README.md` badge + License
      section to match `pyproject.toml` (was MIT — contradiction).
- [x] Removed production debug `fetch()`/`console.log` instrumentation
      (`hypothesisId`/`sessionId:"debug-session"` → `127.0.0.1:7242`) from
      `BaseChartPanel.ts`, `PanelChartPanel.tsx`, `PriceChartPanel.tsx`,
      `IntelligentChartV2.tsx`, `CrosshairSync.ts`, `ChartContainer.tsx` —
      was firing on every render/data-update/crosshair-move.
- [x] `_CREDENTIAL_PASSWORD` hardcoded fallback (`"dev-password-change-in-
      prod"`) removed. New `get_credential_password()` raises `RuntimeError`
      if `BONITO_CREDENTIAL_PASSWORD` is unset instead of silently encrypting
      broker secrets with a key that lives in source control.

Verified clean: ruff and mypy show zero *new* issues anywhere in the tree
(confirmed via `git stash`/`git stash pop` against every touched file —
remaining findings are pre-existing: enum-inheritance `UP042` style nits,
one `F541`, numpy/pandas assignment narrowing in `indicators.py`, and
`AlpacaCredentials` `SecretStr` arg-type errors in `api/routes/trading.py`,
none introduced by this pass).

Scope for this pass was Phase 0 only, per sign-off. Phases 1-3 stay queued
below until a future pass.

## Phase 1 — process guardrails (this week) — DONE 2026-06-19
- [x] No CI workflow runs tests/lint/types on PRs or general pushes — only
      cron trading jobs + one push-to-main workflow that excludes a test
      file and one test by name. Add a real `ci.yml`: pytest -m "not slow" +
      ruff + mypy, on every PR/push.
- [x] mypy is commented out of `.pre-commit-config.yaml` despite CLAUDE.md
      claiming it runs — re-enable or fix the doc.
- [x] De-duplicate kill-filter/`strategy_hash` logic: `autoresearch_trading.py`
      reimplements `trading/validation.py`'s `kill_verdict`/`strategy_hash`
      with a different, inconsistent threshold (`MIN_TRADES=30` absolute vs.
      `MIN_TRADES_PER_YEAR=7.0` rate). Import the shared one; reconcile
      thresholds deliberately.
- [x] `rsi()`/`atr()` share the exact "assumes index 0 is valid" precondition
      that caused the MACD signal-line NaN bug (fixed this week in `ema()`)
      — not yet triggered by any current call site, but unguarded. Apply the
      same fix + a NaN-prefixed-input regression test.
- [x] Add a CLI-level smoke test (`typer.testing.CliRunner`) running
      `bonito backtest` on a regime-filtered strategy end-to-end — this is
      exactly the blind spot that let the missing-`regime_data` bug ship
      undetected.
- [x] Backfill `docs/EXPERIMENT_LOG.md` with this week's findings: the MACD
      bug, the CLI `regime_data` bug, and the deployed-strategy kill-filter
      failure (see the 2026-06-18 review above) — discipline has slipped to
      adoption/rejection-only, contradicting its "canonical record" charter.

### Review (2026-06-19) — Phase 1 shipped via 4-role pipeline
Built as a strict Planner→Builder→Tester→Validator pipeline (no role does
another's job), coordinated through `tasks/phase1_coordination.md`. All 6
items implemented, tested, and independently validated **PASS**. Commits:
`f64b0dc` (ci.yml) → `a00e593`/`3d57607` (CI unblock: UP042 ignore +
non-hermetic-test exclusion, both mirroring `deploy-bot.yml`'s existing
precedent) → `a97acb0` (P1-2/3/4-fix/6) → `0768502` (P1-4/5 tests).
**CI is green.** Suite: 725 passed / 1 skipped (pre-existing) / 9 deselected;
ruff clean; mypy advisory hook verified exits 0 over the 157 pre-existing
errors without hiding any new ones. Validator reproduced every check from
scratch and reverted-then-restored `indicators.py`/`cli.py` to confirm the
new regression tests genuinely catch the original bugs (not vacuous).
Follow-ups punted to Phase 2 (below): the `UP042` → `StrEnum` migration and
the ruff-pin/`.venv` version drift — both surfaced, both non-blocking, both
deliberately out of this phase's scope.

## Phase 2 — near-term hardening (DONE 2026-06-22 — see `tasks/phase2_coordination.md`)
- [x] Test `trading/monitor.py` (P&L/drawdown — zero coverage today) and
      `autoresearch_trading.py`'s pure functions (`split_data`,
      `validate_no_lookahead`, `apply_kill_filters`). — P2-1, commit `a32cf0d`.
- [x] Deliberate `str, Enum` → `enum.StrEnum` migration for the 7 domain
      enums currently behind the `UP042` ignore in `pyproject.toml` (added
      2026-06-19 to unblock CI without a wide-blast-radius behavioral change
      under time pressure). `StrEnum` changes `str(member)` from
      `"ClassName.MEMBER"` to the plain value — verify nothing depends on the
      old format (these enums are embedded in JSON strategy configs) before
      migrating, then drop the ignore. Same "tracked follow-up" status the
      mypy backlog already has via `TODO(P1-2)` in `ci.yml`. — P2-2, commit
      `69cecbd`.
- [x] Reconcile ruff versions: `.pre-commit-config.yaml` pins
      `ruff-pre-commit` to v0.8.2, `pyproject.toml` floors `ruff>=0.8.0`, but
      the `.venv` ships a much newer ruff whose formatter wraps
      parenthesized asserts differently — so `make format` and the pinned
      pre-commit hook disagree on style (cosmetic; `ruff check`/CI unaffected).
      Bump the pin to match the `.venv` (or pin the floor) so all three agree.
      — P2-3, commit `69cecbd`.
- [x] Add `broker_order_id` to `PaperFill`/`TradeIntent`; require it for
      live-mode fills; reject `record-fill` in paper mode. — P2-4, commit
      `69cecbd` (+ `afe6a8a` for 3 docs that still showed the old flag-less
      invocation, caught by the Validator).
- [x] Add a confirmation requirement to `PaperLedger.resume()` (currently
      human-only by convention, not by any enforced precondition). — P2-5,
      commit `69cecbd`.
- [x] Document the Robinhood account-scoping boundary (••••8597, cash-only)
      explicitly as non-code-enforceable in `docs/AUTONOMOUS_LIVE_ROUTINE.md`;
      add a runbook check if the MCP exposes account identity. — P2-6, commit
      `69cecbd`.
- [x] Frontend: delete dead `IntelligentChart.tsx` V1 (2,587 lines, zero live
      importers) + its test + the `index.ts` re-export. Align the
      `PanelChartPanel`/`PriceChartPanel` init `useEffect` dependency arrays
      to the documented `[height, config]` pattern (or explicitly document
      the resize-based alternative). Type the `any` usage concentrated in
      `ChartContainer.tsx`/`BaseChartPanel.ts`. Fix ~8 default-export
      violations (`AdvancedChart`, `EquityChart`, `Chat`, `Sidebar`, etc.).
      — P2-7, commits `659ea87`/`1f28162`/`06671b0`/`334f781`/`f31377d`.
- [x] Zero Playwright tests exist despite tooling/skill references implying
      otherwise — scaffold a minimal config + 1-2 smoke specs, or correct
      the docs. — P2-8, commit `fd8600c`.

## Phase 3 — housekeeping
- [ ] Archive this file's fully-completed session sections to
      `tasks/archive/` — single 500+ line file mixing active and long-done
      work, flagged by the docs audit as already unwieldy.
- [ ] Archive/remove 9 orphaned `strategies/*.json` files not referenced by
      any universe config.
- [ ] Backfill `CHANGELOG.md` (stale at 0.5.0 vs. actual 0.9.0) or deprecate
      it explicitly in favor of `EXPERIMENT_LOG.md`/this file.
- [ ] Fix `.claude/rules/architecture.md`'s dependency-direction rule — it's
      stated backwards vs. reality (`agent` imports `tools`, not the reverse;
      otherwise accurate and clean).
- [ ] Compute `avg_exposure` properly in `backtest/engine.py` instead of the
      hardcoded `0.5` placeholder; check whether research grading silently
      treats it as real.
- [ ] Extract `UniverseConfig` out of `trading/live_runner.py` into its own
      module — `research/` currently imports `live_runner` purely for this,
      coupling research to the live runner.
- [ ] Misc low-severity: `StochasticPanel` missing live crosshair value
      display (RSI/MACD have it), `preflight()` has no top-level
      try/except (unhandled exception ≠ clean `PreflightReport(ok=False)`),
      `ingest_data` API has no input validation/length limit on symbol list,
      `credential_store.py` silently swallows decrypt failures with no
      logging.



Two tracks, both additive (no existing code path changes behavior unless a
new candidate actually clears the existing gates).

## Track A — bridge `bonito research run` into the real adoption gate

Today `autoresearch_trading.py` (32 indicator types, LLM-mutated, one change
at a time) only checks its own train/2024-validation split with a soft
overfit rule (val ≥ 0.5×train) and writes the rolling winner to
`research_output/<symbol>/best_strategy.json`. It never touches the 2025+
holdout, never runs the project's real kill filter
(`trading/validation.py::kill_verdict`, which differs from this loop's own
looser internal constants — `MIN_TRADES=30` total vs. the rest of the
system's `MIN_TRADES_PER_YEAR=7.0`), and never runs account-level replay.
`strategies/adx_trend_strategy.json` + `adx_momentum_aapl.json` (both
2025-12-09, `last_backtest: null`, unreferenced by any universe file) are
proof this has produced candidates with no path to promotion before.

- [ ] New `src/bonito/research/wide_net_bridge.py`: `validate_wide_net_candidate()`
      — load `best_strategy.json` (unwrap `{"config": {...}}` like
      `load_seed_strategy` does), backtest the full range, slice with
      `window_metrics()` using `auto_research.py`'s `rolling_windows()`
      cutpoints (not the loop's own 2024 cutoff), gate with `kill_verdict()`.
      Reject silently (log + stop) on failure — nothing written.
- [ ] On pass: build a `Bundle` exactly like `propose_default_swap()` does
      (write candidate JSON to `strategies/`, propose as default-strategy
      swap or per-symbol assignment) and feed it into the EXISTING graded
      bundle loop in `run_auto_research()` alongside narrow-grid bundles.
      `decide_adoption()`, `backtest_account()`, `sync_live_config()` —
      all untouched, all reused as-is.
- [ ] New explicit CLI: `bonito research promote-wide-net <path>` (dry-run
      report by default, `--apply` to write) — deliberately A SEPARATE,
      MANUAL command, not folded into the unattended Saturday cron. An
      LLM-discovered structural change is exactly the kind of decision that
      should stay a reviewed action.
- [ ] Tests: fixture `best_strategy.json` with known metrics; pass/fail
      paths through `validate_wide_net_candidate`; `Bundle` composition.
- [ ] Once a real run produces a candidate worth keeping, log it in
      `docs/EXPERIMENT_LOG.md` with a pre-registered criterion (existing
      protocol) — same bar as any narrow-grid adoption.

`autoresearch_trading.py`'s internal mutation loop is not modified at all —
zero risk to the existing tool.

## Track B — widen `cluster_research.py` beyond the EMA-cross template

`GridSpec` + `candidate_grid()` (`cluster_research.py:55-66,159-220`)
generate all ~450 candidates from ONE structural template (EMA-cross entry
+ RSI<X filter + EMA-cross exit + ATR trailing stop + mandatory
SPY>SMA200 regime gate), varying only 3 numeric axes. This is the actual
search space for both `bonito research clusters` and the weekly
`bonito research auto` — it has never tried ADX, MACD, Bollinger, or any
of the other 28+ indicator types the wide-net loop is allowed to use.

- [x] Split `candidate_grid()` into named template builders, each small on
      purpose (~30-50 candidates, not 450×N):
      `_ema_cross_candidates()` (today's loop, moved verbatim),
      `_adx_trend_candidates()` (ADX(14)>threshold entry gate),
      `_macd_cross_candidates()` (MACD/signal crossover),
      `_bbands_meanrev_candidates()` (close crosses lower/upper band
      — the one genuinely mean-reverting family, structurally different
      from the other three trend-following templates).
- [x] Every new template MUST still set
      `regime_filter={"symbol": "SPY", "sma_period": 200}` unconditionally
      — preserves the documented invariant ("regime filter is always on,
      a structural risk decision, not a knob"). Verified by test.
- [x] `candidate_grid()` becomes the concatenation of all template builders.
      Same return type (`list[StrategyConfig]`), so `research_cluster()`,
      `run_auto_research()`, `decide_adoption()`, `sync_live_config()`, and
      the `cli.py` candidate count need ZERO changes — they're already
      template-agnostic.
- [x] Extend `GridSpec` with one small nested spec per new template
      (`adx`/`macd`/`bbands: ...Grid | None = None`, `None` = template
      disabled). `candidate_grid()` with no args is byte-identical to
      before (450 EMA-only candidates) — the weekly cron is unaffected.
- [x] Tests in `tests/test_cluster_research.py`: one per new template
      (right indicator types only, regime_filter always present, candidate
      count matches sub-grid combinatorics) + a total-count regression test.
- [x] Smoke-tested `bonito research clusters --templates ...` end-to-end
      (no `--apply`) on a 1-symbol/short-window universe — see review below
      for why the full-universe dry run wasn't the chosen verification path.

Zero Anthropic API cost — pure vectorized backtesting like today. Only
wall-clock scales (candidates × cluster members).

**Sequencing**: Track B first — lower-risk (offline, deterministic, easy
to test), and its templates give Track A's bridge something to sanity-check
LLM output against once ADX/MACD/BBands structures exist locally.

## API credits — do you need to add any?

- **Track B / existing `research auto`/`research clusters`: no.** Zero LLM
  calls anywhere in `cluster_research.py` or `auto_research.py` — pure
  NumPy backtesting. Confirmed via grep (no `anthropic`/`openai` imports).
- **Track A's input, `bonito research run` (= `make research`): yes.**
  `autoresearch_trading.py` instantiates its own `anthropic.Anthropic(api_key=...)`
  client from `ANTHROPIC_API_KEY` and calls `claude-sonnet-4-20250514`
  directly (`autoresearch_trading.py:19,31,247-248,522`) — this is metered
  API spend on console.anthropic.com, **separate from any Claude Code /
  Claude.ai subscription**, even though it's the same env var.
  - Volume: default `--iterations 1000`, 5 mutations/call (`MUTATIONS_PER_BATCH`)
    → ~200 API calls per full run (fewer if it converges early).
  - Each call: ~2-4K input tokens (rules + full StrategyConfig JSON schema,
    re-sent every call — no prompt caching configured) + up to 4,096 output
    tokens (5 full strategy JSONs). Rough estimate at current Sonnet-class
    pricing: **~$5-15 per 1000-iteration run.** Check console.anthropic.com
    for exact current per-token rates before relying on this figure.
  - This tool has run before (it's what produced the orphaned ADX
    strategies) — not new in kind, just confirming the key needs a funded
    balance to run again. A recurring cadence (e.g. weekly) would run
    roughly $20-60/month.
  - Recommend topping up modestly (~$20) to comfortably cover several
    validation runs while Track A's bridge is being built and tested.

## Review (2026-06-18 session) — Track B shipped + regime-sweep + 2 root-cause bugs

**Track B is done**: `cluster_research.py` now has 4 template families behind
`GridSpec` (`ema` always-on default, `adx`/`macd`/`bbands` opt-in via
`None`-by-default nested specs). `candidate_grid()` with no args is still
exactly 450 EMA-only candidates — the weekly cron (`bonito research auto`)
and `run_cluster_research()`'s default behavior are byte-identical to
before. `bonito research clusters --templates ema,adx,macd,bbands` is the
new human-driven entry point (450+27+18+16 = 511 candidates when all four
are requested); validated end-to-end on a throwaway 1-symbol/short-window
universe (real universe + full window timed out at 2 min — expected cost at
33 symbols × 511 candidates, not a bug) — confirmed candidate counts match
exactly and a real MACD-template candidate (`c_macd5-35-5_rsi60_atr2.0`) won
the train ranking, proving the new templates flow correctly end-to-end, not
just at the CLI-parsing level.

**Root-cause bug #1 — MACD signal line was 100% NaN, platform-wide, since
before this session.** `ema()` (`backtest/indicators.py`) seeded its
recursive computation from `np.mean(prices[:period])`, assuming index 0 is
always valid. MACD's signal line is `ema(macd_line, signal_period)`, and
`macd_line` itself starts with `slow_period - 1` NaNs (its own warm-up) — so
the signal line's seed was `NaN`, which then propagated forward forever
through the recursive update (`result[i] = prices[i]*m + result[i-1]*(1-m)`).
Every MACD signal/histogram value, for every strategy that has ever used
them, was NaN. This silently neutered the entire `macd_cross` template
before the fix (zero entries — `crosses_above`/`crosses_below` against NaN
never fires). Fixed by seeding `ema()` from the first valid (non-NaN)
window instead of index 0 — behavior-identical for raw price input (which
starts valid at index 0), correct for derived series with leading NaN.
Added a regression test (`test_signal_line_is_not_all_nan`) and strengthened
two previously-weak tests that asserted array shape/keys but never checked
for NaN (one had a silent-skip guard that meant its core assertion never
actually ran). Verified: MACD signal NaN count on a 33-year SPY series went
from 8,402/8,402 to 33/8,402 (just the genuine warm-up), 355 real crossovers
now detected.

**Root-cause bug #2 — `bonito backtest` crashed on the deployed production
strategy.** The CLI command never fetched or passed `regime_data`, so any
strategy with a `regime_filter` (including `strategies/deployed_strategy.json`
— what's actually trading) raised inside the engine. Found incidentally while
building the regime-sweep command below, which needs the identical
regime-data-fetch logic. Fixed by fetching the regime symbol's bars (with
the same `REGIME_WARMUP_DAYS` padding `live_runner.py` uses) before running
the engine. Verified against both a regime-filtered and a non-regime-filtered
strategy — no regression on the existing path.

**New permanent capability: `bonito research regime-sweep <strategy.json>`**
(`src/bonito/research/regime_sweep.py`, 13 tests). Runs ONE full-history
backtest, then slices it into fixed historical stress windows (GFC
crash+grind, COVID crash, COVID V-recovery, 2022 bear/chop, 2023-25 AI bull,
plus a full-history aggregate row) and compares each to a buy-and-hold
benchmark over the same window — the question a train/holdout split alone
doesn't answer ("does this survive a crash," not just "does this generalize
past its tuning window"). Reports CAGR (not raw cumulative %, which reads as
alarming/overfit-flavored over multi-decade spans) and flags any window with
fewer than 10 trades as `low_sample` — a short window's Sharpe is a
near-meaningless point estimate and shouldn't be silently trusted either
direction.

**Finding — the live deployed strategy fails its own kill filter over full
history.** Running `regime-sweep` against `strategies/deployed_strategy.json`
(what's actually trading the paper/live universe today) surfaced: full-history
max drawdown 38.2%, above the platform's own 25% kill-switch cap; Sharpe 0.93.
2022 bear/chop CAGR -21.9%, worse than SPY's -18.7% that year. GFC-window CAGR
-7.1% (fails, though better than SPY's -9.2%). COVID crash/recovery and
2023-25 bull windows are all `low_sample` (2/8/37 trades) so their Sharpe
numbers shouldn't be over-read. **This is a real risk-posture finding, not
yet acted on** — flagged here for a human decision, consistent with
`mode`/`live_enabled`/risk-cap changes being human-only controls. Worth a
deliberate look at the pre-live checklist below before the next sign-off
review.

**Template family results** (regime-swept individually, full history):
`ema_cross` already has known holdout winners (existing per-symbol
assignments). `adx_trend` and `macd_cross` (post-fix) both produce legitimate
winners on at least one train/holdout split. `bbands_meanrev` is
structurally low-frequency on a persistently-uptrending instrument like SPY
(strict AND of "crosses below lower band" + "RSI oversold" rarely co-occurs
outside of sharp selloffs) — not a bug, just a template that needs a
mean-reverting or range-bound symbol to get enough samples to be trustworthy.

**Verification**: 712 passed / 1 skipped (`pytest tests/ -q -m "not slow"`,
up from 699 before this session — the +13 are `test_regime_sweep.py`). Ruff
clean on every file touched. mypy: zero *new* error categories — the
dict-vs-pydantic-model pattern in the 3 new templates is the same
pre-existing, intentionally-tolerated pattern the EMA template already had
(`strict = false`, "Relaxed for MVP" per `pyproject.toml`, not CI-enforced);
fixed the one genuinely new narrowing issue (`cli.py`'s new regime-sweep
benchmark logic) by checking `strategy.regime_filter is not None` instead of
`regime_data is not None` so mypy can actually prove what's already true at
runtime.

**Not done this session (explicit user ask was Track B only)**: Track A
(the wide-net bridge) is untouched — still pending, see above.

# Account-Level Backtest (2026-06-11) — "backtest the account, not the strategy"

- [x] `trading/portfolio_backtest.py`: day-by-day replay through the REAL
      live pipeline (generate_intents → execute_paper → PaperLedger) — caps,
      daily-buy limits, cash buffer, regime gate, pinning, kill switch all
      apply. ReplayStore serves point-in-time slices → look-ahead is
      structurally impossible. Fills at signal close (paper behavior, not
      the engine's next-open rule).
- [x] Intraday 15-min sweep approximated from daily OHLC: stop fires off
      the low vs PRIOR-HWM level (same-day ratchet never saves you), fills
      at level or at open on gaps; TP mirrors off the high; stop beats TP
      in the same bar. ATR from bars through the previous close.
- [x] `signals.stop_level()` / `take_profit_level()` extracted — single
      source of stop math (stop_loss_triggered now derives from it).
- [x] Root-cause fix: `ema()`/`rsi()` crashed on data shorter than the
      period (IndexError) — now return all-NaN per convention. Found by the
      replay's early-window slices; engine was never exposed because stored
      history was always long.
- [x] CLI `bonito live backtest-account` (+ `make live-backtest-account`):
      summary panel, train/holdout kill verdicts on the ACCOUNT curve,
      per-symbol P&L contribution, saved JSON to livetrade/research/.
- [x] 12 replay tests + 2 indicator edge tests; suite 620 passed.

## Review — first account replay (2022-01-01 → 2026-06-11, $5k, 12s runtime)

**$5,000 → $13,295 (+165.9%) | Sharpe 1.19 | Max DD 23.4% | 688 trades |
win 48% | PF 1.41 | kill switch NEVER fired | all 3 windows PASS:**
| window | trades | ret % | sharpe | DD % | verdict |
|---|---|---|---|---|---|
| Full | 688 | +165.9 | 1.19 | 23.4 | PASS |
| Train | 393 | +67.3 | 0.93 | 23.4 | PASS |
| Holdout | 295 | +58.4 | 1.81 | 18.7 | PASS |

**The headline insight: the account passes everywhere the single symbols
fail.** Per-symbol validation passes 3/25 (drawdowns 30–90%); the account
passes all windows because $1k slices + 5-position cap + cash buffer turn
huge single-name drawdowns into small account dents. Even TE (−86%
single-symbol holdout) contributed +$422 at account level. Top: DELL
+$1,605, ARM +$1,389, SNDK +$1,347. Worst: IREN −$270.

**Risk caveat: max DD 23.4% vs the 25% kill switch — 1.6 points from a
permanent halt.** A slightly worse path trips flatten+halt and the curve
flatlines. Watch this at the two-week review; consider whether the halt
threshold and per-position sizing leave enough margin.

Known approximations (documented in the module): paper fills at signal
close (no spread/commission — calibration pending vs real fills);
intraday sweep modeled from daily OHLC, not 15-min quotes.

# Intraday Stop Automation + Pre-Live Stubs (2026-06-11)

- [x] `bonito live sweep [--execute] [--no-refresh]` — self-contained intraday
      stop sweep: refreshes daily bars for open positions only (ATR source),
      fetches live quotes via yfinance (`bonito/data/quotes.py`), runs the
      same check-stops path. Missing quote = hold + warn, all-missing = exit 1.
- [x] `.github/workflows/intraday-stops.yml` — every 15 min, 13:00–21:45 UTC
      Mon–Fri; in-job guard trims to 9:30–16:00 ET (DST-proof via zoneinfo)
      and skips when flat or non-paper. Shares concurrency group
      `livetrade-state` with the daily cycle so ledger commits never race.
      Failure opens ONE GitHub issue (no 26-issues-a-day spam).
- [x] `entry_allowlist` on UniverseConfig — when set, only listed symbols may
      open NEW positions; exits never gated. Default null = no change.
      This is the pre-live lever for restricting to kill-filter passers.
- [x] `config/universe.live.json` — DRAFT $150 live config (max_position $30,
      buffer $5, allowlist COST/MSFT/TSM). mode="live" but live_enabled=false:
      inert until explicit sign-off flips it.
- [x] `make live-sweep`; runbook updated; tests (allowlist, ATR helper,
      refresh subset, quote fetcher)
- [x] Smoke test: first real sweep took SNDK out at $1829.73 on the 10%
      take-profit → +$125.31 realized (entry $1625.98 on 2026-06-10).

## Pre-live checklist (Phase 3 — every box needs doing before flags flip)

- [ ] ≥2 weeks of paper history → review ~2026-06-24: win rate, max DD,
      holding periods vs backtest; paper fill prices vs backtest's 0.1%
      commission assumption (Robinhood = commission-free + spread) →
      recalibrate engine costs if material.
- [ ] Re-run `bonito live backtest-universe` and update
      `entry_allowlist` in universe.live.json to the CURRENT holdout
      passers (COST/MSFT/TSM as of 2026-06-10 — stale by flip time).
- [ ] Re-run `bonito research clusters` with the longer holdout; apply any
      passing per-symbol assignments.
- [ ] Review universe.live.json caps against actual account balance.
- [ ] Decide allowlist-vs-blocklist for live: the stale COST/MSFT/TSM
      allowlist is now redundant (replay gate + auto-managed blocklist
      cover it) — recommend dropping it at flip.
- [ ] Broker-side stop orders for live: after each live entry, place a GTC
      stop_market at the broker (level from signals.stop_level); the daily
      cycle cancels+replaces to ratchet trailing stops. Robinhood enforces
      stops 24/7 — no Claude session, laptop, or phone needed for
      intraday protection. Track stop order IDs in the live ledger.
      This REPLACES the need for an all-day /loop session in live mode.
- [ ] ≥2 weeks of GREEN live-vs-replay tracking at 1-share size
      (`bonito live tracking -u config/universe.live.json` OK every cycle)
      AND `bonito live reconcile` clean (no fatal drift) every cycle.
      This replaces the weaker "paper-vs-replay" criterion: live-at-min-size
      exercises the real broker path (actual qty, T+1 settlement, real spread)
      and is far stronger evidence before scaling size.
      See RFC §9 rehearsal loop: reconcile → preflight → run → place (MCP) →
      record actual fill → tracking → assert OK each cycle.
- [x] Live MCP rehearsal on the Agentic account (••••8597, NEVER margin) —
      DONE 2026-06-12: RIVN 1-share round trip. Buy limit $15.75 → filled
      $15.7478 (~200ms); sell limit $15.74 → filled $15.7501 (price
      improvement). Zero fees, placed_agent=agentic on both legs, book
      flat after. Order IDs 6a2c3437-…f16d (buy), 6a2c345b-…8dfc (sell).
      Margin account rejected by API design (agentic_allowed=false). ✅
- [ ] USER SIGN-OFF, then flip `live_enabled: true` in universe.live.json
      and point the daily session at it. Live placement stays in Claude
      sessions via MCP — the Actions workflows are paper-only by guard.
- [ ] (Optional, fully hands-off) Create the scheduled live Routine per
      docs/AUTONOMOUS_LIVE_ROUTINE.md: Robinhood as a claude.ai connector,
      `/schedule` weekdays ~3:45pm ET, prompt runs reconcile → preflight →
      run → place → record → commit. Dogfood on paper / live_enabled:false
      first (proves container-on-schedule + connector auth, places nothing).
      This removes the last human checkpoint, so it comes AFTER sign-off.
      ✅ RESOLVED 2026-06-25: `bonito live refresh`+`run` now carry a
      settled-vs-forming-bar guard (`_is_forming` in `live_runner.py`,
      stdlib `zoneinfo`, fail-closed) — entries skip and exits hold on a
      forming (pre-close) bar instead of pricing off yfinance's still-forming
      daily print. This was the mechanism behind the 06-10 ORCL/ARM tracking
      WARN (see `tasks/arm_fill_gap_coordination.md` Decision #3); full
      design in `docs/RFC_SETTLED_BAR_GUARD.md`, build history in
      `tasks/settled_bar_guard_coordination.md` (4-role pipeline, Validator
      PASS). Net effect: the schedule no longer affects correctness, only
      how often a pre-close run suppresses a trade — 3:45pm ET is fine to
      keep (see `docs/AUTONOMOUS_LIVE_ROUTINE.md` "Picking the time").
      Accepted residual: half-day sessions (~9/yr) close at 13:00 ET, so the
      guard reads them as forming until 16:15 ET and any run in that window
      skips — a missed trade, never a mis-trade (see `tasks/lessons.md`).

# Per-Cluster Strategy Research (2026-06-10/11)

- [x] `research/cluster_research.py`: vol clustering, 144-candidate grid, train-rank → holdout-gate
- [x] Cross-sectional sanity: candidate must pass train kill filter on majority of cluster
- [x] `apply_assignments()`: per-symbol strategy JSONs + `symbol_strategies` merge (winner==default → skip)
- [x] CLI `bonito research clusters` (`--apply` to write; dry-run report otherwise)
- [x] Tests (10 passed, 1 skipped); full suite 598 passed; ruff clean
- [x] First real sweep + report committed (`livetrade/research/`)
- [x] Commit + push

## Review (2026-06-10/11 session)

**Per-cluster research** (`src/bonito/research/cluster_research.py`):
universe symbols are bucketed by annualized realized vol (defensive <30%,
core <50%, growth <75%, speculative ≥75%), then a fixed 144-candidate grid
(EMA pairs 8/21·10/26·12/26·20/50 × RSI cap 60/68/75 × ATR mult
1.5/2.0/2.5/3.0 × TP 10%/20%/none — all with SPY>SMA200 regime + ATR
trailing stop, non-negotiable) is ranked per cluster on TRAIN-window median
Sharpe across members passing the train kill filter. The single winner is
then gated once on the holdout kill filter per symbol. Only (symbol,
strategy) pairs that pass holdout AND differ from the default strategy are
ever assigned. `bonito research clusters --apply` writes winners to
`strategies/` and merges into `universe.symbol_strategies`; without
`--apply` it's a dry-run report saved to `livetrade/research/`.

**First sweep** (train 2022→2025, holdout 2025→2026-06-10): defensive
(COST+MSFT) produced a winner — `c_ema20-50_rsi60_atr2.5_tp20`, train
score 2.90 — but both symbols missed the holdout min-trades gate (9 and 7
vs ~11 needed). Core/growth/speculative had no candidate passing the train
filter on a majority of members. **Zero assignments — the holdout gate
doing its job.** All 25 symbols stay on the deployed default. Re-run after
more holdout history accumulates (`bonito research clusters`).

# Enhancement Build (2026-06-10) — validation harness, regime filter, ATR stops, $5k paper

- [x] `trading/validation.py`: kill-filter thresholds + windowed (train/holdout) metrics + verdict + strategy_hash
- [x] DSL: `RegimeFilterConfig` (SPY > SMA200 gate) on StrategyConfig
- [x] Engine: optional `regime_data` param masks long entries
- [x] signals.py: trailing_atr/atr stop support in live path + `regime_allows_long`
- [x] paper.py: pin strategy (hash + config snapshot) on positions; ledger peak_equity/halted
- [x] live_runner.py: per-symbol strategy map, pinned-strategy exits, regime gate on entries, portfolio kill switch
- [x] CLI: backtest-universe → holdout split + verdict column + regime; `live resume`; status shows HALT
- [x] universe.json → $5k paper caps; re-seed ledger at $5k
- [x] Compare variants (baseline / ATR stop / ATR+regime), deploy winner to deployed_strategy.json
- [x] Tests for all of the above; full suite green (581 passed)
- [x] Commit + push

## Review (2026-06-10 session)

Network unblocked → Phase 2 executed, then enhancement build:

**Validation harness**: `backtest-universe` now runs one full-range sim per
symbol, slices equity/trades into train ([start, holdout)) and holdout
([holdout, end]) windows, and prints a kill-filter verdict computed on the
holdout (trades ≥ 7/yr scaled to window, DD ≤ 25%, Sharpe ≤ 3.0).
`--strategy file.json` overrides for variant comparison; `--holdout none`
reverts to full-period verdicts.

**Variant comparison** (holdout 2025-01-01 → 2026-06-10, medians across 25):
| variant | pass | med H.Sharpe | med H.DD% | med H.Ret% |
|---|---|---|---|---|
| baseline 1.6% trail | 2 | 0.72 | 48.2 | +13.4 |
| atr2.5 | 2 | 1.13 | 43.0 | +46.5 |
| **atr2.0+regime (deployed)** | **3** | 0.89 | 42.8 | +19.8 |

Deployed `ema_cross_rsi_atr_regime` v2.0: 2.0×ATR(14) trailing stop +
SPY>SMA200 regime gate. Trade churn fell ~70% (220→~55 trades/symbol).
Holdout passers: COST, MSFT, TSM. Near-misses: WDC (only Sharpe 3.82>3.0),
LLY (DD 27%>25%).

**New safety rails**: positions pin their strategy at entry (hash + full
config snapshot — exits always use the entering config); portfolio kill
switch flattens + halts at 25% drawdown from peak equity (clear with
`bonito live resume`, human-only); regime risk-off blocks entries but never
exits; missing ATR/regime data = hold/risk-off, never guess.

**Paper account re-seeded at $5,000** (max_position $1000, 5 positions,
$100 buffer, 25% DD halt). First cycle filled MU/SNDK/DELL at $1k each.

**Dashboard (added same session)**: standalone read-only web app at
`make dashboard` / `bonito dashboard` (port 8050) — `src/bonito/dashboard/`
(FastAPI + single static page, Bonito Mediterranean Pastel theme, no build
step). Shows account stat cards, open positions with live trailing-stop /
take-profit levels and distances, regime status (SPY vs SMA200), risk caps
with drawdown-vs-kill-switch meter, equity curve reconstructed from fills,
recent fills, kill-switch banner, staleness warnings. Auto-refreshes every
30s. 7 state-builder tests.

**Automation (added same session)**: `.github/workflows/paper-trading.yml`
runs the full paper cycle at 22:30 UTC weekdays and commits `livetrade/`
back as a heartbeat (`chore(livetrade): daily paper cycle …`). Paper-mode
guard hard-stops if universe mode ever flips; failures open a GitHub
issue so unmanaged positions are never silent. ⚠️ GitHub fires schedules
only from the DEFAULT branch — the cron activates when this branch merges
to main (manual `workflow_dispatch` also only registers then). All steps
rehearsed locally end-to-end 2026-06-10; second same-day run filled ORCL
+ ARM → portfolio fully deployed 5/5, $100 cash buffer, equity $5,042.57.
Note: max_daily_buys is per-run; the cron runs once daily.

Decision points for Phase 3 (live):
- Paper trades ALL 25 symbols for system-validation throughput; before
  flipping live, restrict entries to kill-filter passers (COST/MSFT/TSM as
  of today) via `symbol_strategies` or a passer allowlist.
- Backtest costs (0.1% commission default) don't match Robinhood
  commission-free + spread reality; calibrate against paper fills.

# Robinhood Autonomous Trading — Plan (Option A)

Goal: trade a 21-symbol universe on Robinhood with $150 (Agentic cash account,
agentic_allowed=true), fully autonomous via scheduled Claude sessions that run
Bonito signal code locally and execute orders through the Robinhood MCP.
Paper mode first; live only after validation.

## Architecture

```
DuckDB bars (yfinance daily refresh)
        │
bonito live run ──► TradeIntents (JSON)
        │                  │
   paper mode         live mode (Claude session)
        │                  │
PaperLedger (repo)    Robinhood MCP: review → place → record-fill
        │                  │
   livetrade/state committed + pushed each session
```

Key constraints discovered:
- Robinhood MCP has NO historical bars → data refresh stays on yfinance.
- This remote env blocks Yahoo hosts → user must allowlist query1/query2.finance.yahoo.com
  (or run refresh locally) before daily sessions can refresh data.
- Fractional/dollar orders fill regular-hours only → daily flow runs during RTH.
- Container is ephemeral → ledger state lives in repo, committed every session.
- Live orders only on account ••••8597 ("Agentic", cash, $150).

## Phase 1 — Core module + tests (this session)
- [ ] `config/universe.json` — 21 symbols, risk caps, mode=paper, live_enabled=false
- [ ] `src/bonito/trading/signals.py` — pure per-bar rule/condition evaluation,
      stop-loss/take-profit checks, TradeIntent generation (extracted from bot.py)
- [ ] Refactor `bot.py` to delegate evaluation to signals.py (existing tests stay green)
- [ ] `src/bonito/trading/paper.py` — PaperLedger: cash, positions, fills,
      mark-to-market, JSON persistence
- [ ] `src/bonito/trading/live_runner.py` — orchestration: signals across universe,
      paper execution, stop checks, status
- [ ] CLI `bonito live ...`: refresh, run, signals, check-stops, status, backtest-universe
- [ ] Tests: `test_live_signals.py`, `test_paper_ledger.py`, `test_live_runner.py`
- [ ] Skill `.claude/skills/robinhood-trade/SKILL.md` — daily + intraday runbooks
- [ ] `livetrade/` state dir + seeded paper ledger ($150)
- [ ] Make targets: `live-run`, `live-status`

## Phase 2 — Validation (needs Yahoo allowlist or local run)
- [ ] Backfill universe data (2022-01-01 → today)
- [ ] `bonito live backtest-universe` — deployed strategy across all 21 symbols,
      kill-filter (min trades, max DD, Sharpe sanity)
- [ ] ≥2 weeks paper trading via daily sessions; review win rate / drawdown

## Phase 3 — Live enablement
- [ ] Flip `live_enabled: true` in universe.json (explicit user sign-off)
- [ ] Live flow: review_equity_order → confirm caps → place_equity_order (ref_id UUID)
      → record-fill → reconcile vs get_equity_positions
- [ ] Intraday: /loop session during RTH checks stops via MCP quotes every 15m

## Risk caps ($150 account)
- max_position_usd: 30, max_positions: 5, min_cash_buffer: 5
- max_daily_buys: 3, long-only, dollar-based market orders, RTH only
- Strategy: ema_cross_rsi_optimized (EMA 10/26 cross + RSI<68 filter,
  1.6% trailing stop, 10% take profit) — already validated on SPY by autoresearch

## Review (2026-06-09 session)

Phase 1 complete. Built and verified:
- `signals.py` extracted from bot.py (bot now delegates; all 85 pre-existing
  trading tests green). Fixed a float-precision edge in take-profit triggers.
- `paper.py` ledger + `live_runner.py` orchestration + `bonito live` CLI
  (refresh / signals / run / check-stops / status / record-fill /
  backtest-universe).
- 66 new tests; full CI-equivalent suite: 494 passed, 12 skipped.
- End-to-end smoke test with synthetic bars: 3 entries filled at $30 each,
  caps enforced, intraday trailing stop correctly fired on a −4% move.
- Paper ledger seeded at $150. Account verified live: Robinhood "Agentic"
  cash account ••••8597, agentic_allowed=true, $150 buying power, all 21
  symbols tradable + fractional.

Blockers for Phase 2:
- Yahoo Finance hosts not in this environment's network allowlist — needed
  for `bonito live refresh` and `backtest-universe` on real data.
  Re-verified 2026-06-09: query1/query2.finance.yahoo.com still 403
  ("Host not in allowlist"); Stooq/Alpha Vantage/Tiingo/Nasdaq also blocked.
- ~~TE = T1 Energy Inc. assumed~~ — confirmed by user 2026-06-09: TE is
  T1 Energy Inc.
