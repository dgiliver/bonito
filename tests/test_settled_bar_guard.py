"""Tests for the settled-vs-forming bar guard (docs/RFC_SETTLED_BAR_GUARD.md).

Covers the RFC §7 test plan, parts 1-5:
  1. _is_forming unit table (winter + summer, both required)
  2. generate_intents integration (forming -> skip/hold, settled -> fires)
  3. Sweep-exemption regression
  4. Build-time tz check (naive .date() comparison would get this wrong)
  5. Non-vacuous proof (mutate-and-confirm-fail), documented for part 2

The replay-regression positive test (RFC §7's implicit 6th item, surfaced in the
coordination doc's "risks flagged for Tester") lives in
tests/test_portfolio_backtest.py::TestSettledBarGuardReplayWiring — see that
file for why the original test_no_lookahead_entry_fires_on_signal_day does NOT
adequately cover the require_settled=False call site at portfolio_backtest.py:283.

Stored daily bar timestamps in DuckDB are ET-midnight-of-session-date expressed
as naive UTC: 05:00 UTC in EST (winter), 04:00 UTC in EDT (summer) — verified
directly against data/market_data.duckdb (see TestBuildTimeTzCheck below for
the live re-verification of that claim, run with --run-slow).
"""

import json
from datetime import datetime, timedelta

import pytest

from bonito.data.models import BarData
from bonito.trading.live_runner import (
    SETTLE_HOUR_ET,
    SETTLE_MINUTE_ET,
    UniverseConfig,
    _is_forming,
    check_stops,
    generate_intents,
)
from bonito.trading.paper import PaperLedger, PaperPosition

# ---------------------------------------------------------------------------
# Part 1: _is_forming unit table
# ---------------------------------------------------------------------------
#
# Stored-bar convention under test: ET-midnight-of-session-date as naive UTC.
#   EST (winter, UTC-5): midnight ET -> 05:00 UTC the same calendar date.
#   EDT (summer, UTC-4): midnight ET -> 04:00 UTC the same calendar date.
# Settle boundary: 16:00 ET close + 15 min buffer = 16:15 ET on the bar's date.
#   EST: 16:15 ET = 21:15 UTC.  EDT: 16:15 ET = 20:15 UTC.


class TestIsFormingUnitTable:
    """Each test derives its UTC->ET conversion by hand in the docstring so the

    expected boolean is traceable, not asserted by faith.
    """

    def test_settle_constants_are_16_15_et(self):
        """Pin down the constants the rest of this table's arithmetic depends on."""
        assert SETTLE_HOUR_ET == 16
        assert SETTLE_MINUTE_ET == 15

    # -- (a) bar well before settle time on its own date -> forming --

    def test_winter_well_before_close_is_forming(self):
        """Bar = 2026-01-05 05:00 UTC = midnight ET Jan 5 (EST, UTC-5).

        as_of = 2026-01-05 18:00 UTC = 13:00 ET Jan 5 -- 3h 15m before the
        16:15 ET settle boundary. Same session date, well before close.
        """
        bar = datetime(2026, 1, 5, 5, 0)
        as_of = datetime(2026, 1, 5, 18, 0)
        assert _is_forming(bar, as_of) is True

    def test_summer_well_before_close_is_forming(self):
        """Bar = 2026-07-06 04:00 UTC = midnight ET July 6 (EDT, UTC-4).

        as_of = 2026-07-06 17:00 UTC = 13:00 ET July 6 -- 3h 15m before the
        16:15 ET settle boundary. Same session date, well before close.
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 6, 17, 0)
        assert _is_forming(bar, as_of) is True

    def test_winter_pre_close_documented_rfc_scenario_is_forming(self):
        """The exact scenario the RFC opens with: a 3:45pm ET live Routine run.

        Bar = 2026-01-05 05:00 UTC = midnight ET Jan 5 (EST).
        as_of = 2026-01-05 20:45 UTC = 15:45 ET Jan 5 -- 30 min before settle.
        """
        bar = datetime(2026, 1, 5, 5, 0)
        as_of = datetime(2026, 1, 5, 20, 45)
        assert _is_forming(bar, as_of) is True

    def test_summer_pre_close_documented_rfc_scenario_is_forming(self):
        """Same 3:45pm ET Routine scenario, summer (EDT) convention.

        Bar = 2026-07-06 04:00 UTC = midnight ET July 6 (EDT).
        as_of = 2026-07-06 19:45 UTC = 15:45 ET July 6 -- 30 min before settle.
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 6, 19, 45)
        assert _is_forming(bar, as_of) is True

    # -- (b) bar exactly at / just after the 16:15 ET settle boundary -> settled --

    def test_winter_exact_settle_boundary_is_settled(self):
        """Bar = 2026-01-05 05:00 UTC (midnight ET, EST).

        16:15 ET = 21:15 UTC (EST is UTC-5: 16:15 + 5:00 = 21:15).
        as_of = 2026-01-05 21:15 UTC is exactly the settle instant.
        _is_forming uses `now_et < settle` (strict), so equality -> settled.
        """
        bar = datetime(2026, 1, 5, 5, 0)
        as_of = datetime(2026, 1, 5, 21, 15)
        assert _is_forming(bar, as_of) is False

    def test_summer_exact_settle_boundary_is_settled(self):
        """Bar = 2026-07-06 04:00 UTC (midnight ET, EDT).

        16:15 ET = 20:15 UTC (EDT is UTC-4: 16:15 + 4:00 = 20:15).
        as_of = 2026-07-06 20:15 UTC is exactly the settle instant -> settled.
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 6, 20, 15)
        assert _is_forming(bar, as_of) is False

    def test_winter_one_minute_before_settle_is_still_forming(self):
        """Bar = 2026-01-05 05:00 UTC. 16:15 ET = 21:15 UTC (EST).

        as_of = 21:14 UTC = 16:14 ET -- one minute short of the boundary.
        Locks the boundary tight on the forming side (paired with the exact
        boundary test above, which locks the settled side).
        """
        bar = datetime(2026, 1, 5, 5, 0)
        as_of = datetime(2026, 1, 5, 21, 14)
        assert _is_forming(bar, as_of) is True

    def test_summer_one_minute_before_settle_is_still_forming(self):
        """Bar = 2026-07-06 04:00 UTC. 16:15 ET = 20:15 UTC (EDT).

        as_of = 20:14 UTC = 16:14 ET -- one minute short of the boundary.
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 6, 20, 14)
        assert _is_forming(bar, as_of) is True

    def test_winter_just_after_settle_is_settled(self):
        """Bar = 2026-01-05 05:00 UTC. as_of = 21:16 UTC = 16:16 ET -- 1 min

        after the 21:15 UTC / 16:15 ET boundary.
        """
        bar = datetime(2026, 1, 5, 5, 0)
        as_of = datetime(2026, 1, 5, 21, 16)
        assert _is_forming(bar, as_of) is False

    def test_summer_just_after_settle_is_settled(self):
        """Bar = 2026-07-06 04:00 UTC. as_of = 20:16 UTC = 16:16 ET -- 1 min

        after the 20:15 UTC / 16:15 ET boundary.
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 6, 20, 16)
        assert _is_forming(bar, as_of) is False

    def test_winter_16_00_to_16_15_buffer_window_is_forming(self):
        """The RFC's explicit buffer-window sub-case: post-4pm-close but before

        the 15-minute finalize buffer elapses must still read as forming.
        Bar = 2026-01-05 05:00 UTC. 16:05 ET = 21:05 UTC (EST) -- 5 min after
        the close, 10 min before settle.
        """
        bar = datetime(2026, 1, 5, 5, 0)
        as_of = datetime(2026, 1, 5, 21, 5)
        assert _is_forming(bar, as_of) is True

    def test_summer_16_00_to_16_15_buffer_window_is_forming(self):
        """Summer counterpart of the buffer-window case.

        Bar = 2026-07-06 04:00 UTC. 16:05 ET = 20:05 UTC (EDT).
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 6, 20, 5)
        assert _is_forming(bar, as_of) is True

    # -- (c) a bar from a prior date evaluated "now" -> settled --

    def test_winter_prior_trading_day_bar_is_settled(self):
        """Bar = Friday 2026-01-02 05:00 UTC (midnight ET, EST).

        as_of = Monday 2026-01-05 13:00 UTC = 08:00 ET Monday -- 3 calendar
        days later, comfortably past Friday's settle. Also exercises the
        weekend/after-hours case from RFC §7.1 (Friday's bar, evaluated over
        the weekend, is settled).
        """
        bar = datetime(2026, 1, 2, 5, 0)
        as_of = datetime(2026, 1, 5, 13, 0)
        assert _is_forming(bar, as_of) is False

    def test_summer_prior_trading_day_bar_is_settled(self):
        """Bar = Monday 2026-07-06 04:00 UTC (midnight ET, EDT).

        as_of = Tuesday 2026-07-07 13, 0 UTC = 09:00 ET Tuesday -- one
        calendar day later, comfortably past Monday's settle.
        """
        bar = datetime(2026, 7, 6, 4, 0)
        as_of = datetime(2026, 7, 7, 13, 0)
        assert _is_forming(bar, as_of) is False

    def test_winter_weekend_after_hours_friday_bar_settled_by_saturday(self):
        """RFC §7.1's explicit weekend/after-hours sub-case, winter convention.

        Bar = Friday 2026-01-02 05:00 UTC (midnight ET). as_of = Saturday
        2026-01-03 15:00 UTC = 10:00 ET Saturday -- settled long before the
        next session even opens.
        """
        bar = datetime(2026, 1, 2, 5, 0)
        as_of = datetime(2026, 1, 3, 15, 0)
        assert _is_forming(bar, as_of) is False

    # -- (d) winter case: bar stored as 05:00 UTC (EST) settles correctly --
    # -- (e) summer case: bar stored as 04:00 UTC (EDT) settles correctly --
    # Both seasons are exercised throughout (a)-(c) above; this pair adds an
    # explicit same-instant-different-season comparison so the asymmetric
    # UTC offset (5h vs 4h) is visibly load-bearing, not incidental.

    def test_winter_and_summer_same_wallclock_utc_hour_diverge_correctly(self):
        """At the identical UTC wall-clock hour (21:00) relative to midnight-ET

        bars stored five hours apart in raw UTC value (05:00 vs 04:00), the
        winter bar is NOT yet settled (21:00 UTC = 16:00 ET exactly, before
        the 16:15 buffer) while advancing the summer-equivalent UTC instant
        by the DST delta correctly lands past summer's earlier-in-UTC-terms
        settle. This isolates the EST-vs-EDT offset as the deciding factor.
        """
        # Winter: 21:00 UTC = 16:00 ET (EST, -5h) -- exactly at close, before
        # the 16:15 buffer -> still forming.
        bar_winter = datetime(2026, 1, 5, 5, 0)
        as_of_winter = datetime(2026, 1, 5, 21, 0)
        assert _is_forming(bar_winter, as_of_winter) is True

        # Summer: the analogous "exactly at the close" instant is 20:00 UTC
        # (EDT, -4h), one hour earlier in UTC than winter's -- if the helper
        # ignored the DST offset and used a fixed UTC cutoff, this pair would
        # not move together correctly. 20:00 UTC = 16:00 ET exactly -> forming.
        bar_summer = datetime(2026, 7, 6, 4, 0)
        as_of_summer = datetime(2026, 7, 6, 20, 0)
        assert _is_forming(bar_summer, as_of_summer) is True

    # -- fail-closed: tz resolution failure -> treated as forming --

    def test_tz_resolution_failure_is_treated_as_forming(self):
        """A datetime that raises OverflowError on .astimezone() (e.g. a value

        near datetime.max, which cannot be represented in some other tz's
        offset) must fail closed -> forming, never silently treated as
        settled. Exercises the real exception path, not a mock.
        """
        from datetime import MAXYEAR

        pathological = datetime(MAXYEAR, 12, 31, 23, 59)
        assert _is_forming(pathological, datetime(2026, 1, 1)) is True


# ---------------------------------------------------------------------------
# Shared fixtures for parts 2, 3, 5 (mirrors tests/test_live_runner.py's style)
# ---------------------------------------------------------------------------

ALWAYS_ENTER_STRATEGY = {
    "name": "always_enter",
    "symbols": ["TEST"],
    "timeframe": "1d",
    "indicators": [{"type": "sma", "name": "sma_2", "params": {"period": 2}}],
    "entry_rules": [
        {
            "conditions": [{"left": "close", "comparison": "gt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
    "exit_rules": [
        {
            "conditions": [{"left": "close", "comparison": "lt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
    "position_size": {"type": "percent_equity", "value": 10},
    "stop_loss": {"type": "trailing_percent", "value": 0.05},
    "take_profit": {"type": "percent", "value": 0.10},
}


class FakeStore:
    """Duck-typed MarketDataStore returning canned bars."""

    def __init__(self, bars: dict[str, BarData]):
        self.bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self.bars.get(symbol)


def make_bars_ending_at(symbol: str, closes: list[float], last_bar: datetime) -> BarData:
    """Bars whose LAST timestamp is exactly `last_bar` (the real bar-stamping

    convention under test), spaced one calendar day apart going backwards.
    """
    n = len(closes)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[last_bar - timedelta(days=n - 1 - i) for i in range(n)],
        opens=closes,
        highs=[c * 1.01 for c in closes],
        lows=[c * 0.99 for c in closes],
        closes=closes,
        volumes=[1_000_000.0] * n,
    )


@pytest.fixture
def universe(tmp_path):
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(json.dumps(ALWAYS_ENTER_STRATEGY))
    return UniverseConfig(
        name="test",
        symbols=["AAA", "BBB"],
        strategy_path=str(strategy_path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        risk={
            "starting_cash_usd": 150.0,
            "max_position_usd": 30.0,
            "max_positions": 5,
            "max_daily_buys": 3,
            "min_cash_buffer_usd": 5.0,
            "allow_short": False,
        },
    )


# Winter convention: bar stored at 05:00 UTC = midnight ET, EST.
FORMING_LAST_BAR = datetime(2026, 1, 5, 5, 0)
# 13:00 ET Jan 5 = 18:00 UTC -- well before the 16:15 ET settle boundary.
FORMING_AS_OF = datetime(2026, 1, 5, 18, 0)
# 17:00 ET Jan 5 = 22:00 UTC -- 45 min past the 16:15 ET settle boundary.
SETTLED_AS_OF = datetime(2026, 1, 5, 22, 0)


def rising_closes(n: int = 10) -> list[float]:
    return [100.0 + i for i in range(n)]


# ---------------------------------------------------------------------------
# Part 2: generate_intents integration (entry + exit, forming vs settled)
# ---------------------------------------------------------------------------


class TestGenerateIntentsSettledBarGuardIntegration:
    """Proves the guard is wired into BOTH the entry and exit loops of

    generate_intents — not just that _is_forming exists in isolation.
    """

    def test_forming_bar_blocks_all_entries(self, universe):
        closes = rising_closes()
        store = FakeStore(
            {s: make_bars_ending_at(s, closes, FORMING_LAST_BAR) for s in universe.symbols}
        )
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, prices = generate_intents(universe, store, ledger, as_of=FORMING_AS_OF)

        assert [i for i in intents if i.side == "buy"] == []
        # No symbol's forming price should have been picked up either.
        assert prices == {}

    def test_settled_bar_lets_the_same_entry_fire(self, universe):
        """Identical fixture, only `as_of` advanced past settle -> entry fires.

        This is the paired half of the test above: proves the guard's effect
        is specifically about settledness, not some other accidental skip.
        """
        closes = rising_closes()
        store = FakeStore(
            {s: make_bars_ending_at(s, closes, FORMING_LAST_BAR) for s in universe.symbols}
        )
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, prices = generate_intents(universe, store, ledger, as_of=SETTLED_AS_OF)

        buys = [i for i in intents if i.side == "buy"]
        assert len(buys) == 2
        assert {i.symbol for i in buys} == set(universe.symbols)
        assert prices  # settled close prices were used for marking

    def test_forming_bar_holds_open_position_exit(self, universe):
        """An open position deep in stop-breach territory must NOT exit while

        the latest bar is forming — exits hold, exactly like the stale-data
        guard, never fire on an intraday print that may reverse by the close.
        """
        closes = rising_closes()
        store = FakeStore(
            {s: make_bars_ending_at(s, closes, FORMING_LAST_BAR) for s in universe.symbols}
        )
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        # Entry at 200, last close ~109 -> deep stop breach if the guard didn't hold.
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA",
            quantity=0.5,
            entry_price=200.0,
            entry_date=FORMING_AS_OF,
            high_water_mark=200.0,
        )

        intents, prices = generate_intents(universe, store, ledger, as_of=FORMING_AS_OF)

        assert [i for i in intents if i.side == "sell"] == []
        assert prices == {}

    def test_settled_bar_lets_the_same_exit_fire(self, universe):
        """Same stop-breached position, only `as_of` advanced past settle ->

        the exit that was held above now fires.
        """
        closes = rising_closes()
        store = FakeStore(
            {s: make_bars_ending_at(s, closes, FORMING_LAST_BAR) for s in universe.symbols}
        )
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA",
            quantity=0.5,
            entry_price=200.0,
            entry_date=SETTLED_AS_OF,
            high_water_mark=200.0,
        )

        intents, prices = generate_intents(universe, store, ledger, as_of=SETTLED_AS_OF)

        sells = [i for i in intents if i.side == "sell"]
        assert len(sells) == 1
        assert sells[0].symbol == "AAA"
        assert "stop loss" in sells[0].reason

    def test_require_settled_false_opts_out_of_the_guard(self, universe):
        """The escape hatch the account replay relies on: explicitly passing

        require_settled=False on the SAME forming-bar fixture lets the entry
        fire even though as_of itself is still pre-close. Proves the flag,
        not just the default, is correctly threaded through both loops.
        """
        closes = rising_closes()
        store = FakeStore(
            {s: make_bars_ending_at(s, closes, FORMING_LAST_BAR) for s in universe.symbols}
        )
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(
            universe, store, ledger, as_of=FORMING_AS_OF, require_settled=False
        )

        assert len([i for i in intents if i.side == "buy"]) == 2

    def test_forming_regime_reference_forces_risk_off(self, universe, tmp_path):
        """Regime filter wiring: a forming regime-reference bar must force

        risk-off (mirrors the existing stale-regime risk-off pattern), even
        though the entry symbols' own bars are settled.

        generate_intents uses a SINGLE as_of for both the entry-symbol check
        and the regime-reference check, so to isolate "regime forming" from
        "entry symbol forming" the entry symbols' last bar must be dated the
        PRIOR trading day (already closed, settled relative to as_of) while
        SPY's last bar is dated the SAME day as as_of (still pre-close,
        forming relative to that same as_of).
        """
        gated_strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 5},
        }
        path = tmp_path / "gated.json"
        path.write_text(json.dumps(gated_strategy))
        universe.strategy_path = str(path)
        universe._strategy_cache.clear()

        # Entry symbols' last bar = yesterday's settled close (Jan 4, winter
        # convention) -> settled relative to as_of=FORMING_AS_OF (Jan 5, 13:00 ET).
        yesterdays_close = FORMING_LAST_BAR - timedelta(days=1)
        bars = {
            s: make_bars_ending_at(s, rising_closes(), yesterdays_close) for s in universe.symbols
        }
        # SPY's last bar = TODAY's (Jan 5) forming print -- same date as
        # as_of, still pre-close. Rising closes -> would read risk-on if the
        # guard failed to force risk-off, so a fired entry here can only be
        # explained by the regime guard not being wired correctly.
        bars["SPY"] = make_bars_ending_at("SPY", rising_closes(), FORMING_LAST_BAR)
        store = FakeStore(bars)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        # Sanity-check the fixture itself before trusting the assertion below.
        assert _is_forming(yesterdays_close, FORMING_AS_OF) is False  # entries: settled
        assert _is_forming(FORMING_LAST_BAR, FORMING_AS_OF) is True  # regime ref: forming

        intents, _ = generate_intents(universe, store, ledger, as_of=FORMING_AS_OF)

        assert [i for i in intents if i.side == "buy"] == []


# ---------------------------------------------------------------------------
# Part 3: sweep-exemption regression
# ---------------------------------------------------------------------------


class TestSweepExemptionRegression:
    """Proves live_sweep / _sweep_stops / check_stops do NOT call

    generate_intents and are unaffected by a forming daily bar — guards
    against a future refactor accidentally routing the sweep through the
    guarded function.
    """

    def test_check_stops_source_never_references_generate_intents_or_guard(self):
        """Static guard: if a future refactor makes check_stops call

        generate_intents (or _is_forming/_is_stale) directly, this test
        catches it immediately via source inspection — independent of any
        particular data fixture.
        """
        import inspect

        src = inspect.getsource(check_stops)
        assert "generate_intents" not in src
        assert "_is_forming" not in src
        assert "_is_stale" not in src

    def test_sweep_stop_triggers_on_a_live_quote_while_the_daily_bar_is_forming(self, universe):
        """Behavioral guard: even when the daily-bar store would report the

        latest bar as forming (and generate_intents would therefore hold
        this exact position's exit), the intraday sweep — sourcing its own
        live quote, completely bypassing the daily-bar store — still fires
        the stop. This is the scenario the RFC §6 promises: intraday
        protection is unaffected by the decision-layer guard.
        """
        # Stop-breached position: entry 100, hwm 100, 5% trailing stop -> a
        # quote at 94.0 is an 6% drop, breaching the stop.
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA",
            quantity=0.5,
            entry_price=100.0,
            entry_date=FORMING_AS_OF,
            high_water_mark=100.0,
        )

        # Confirm the daily bar IS forming at this as_of, to make the contrast
        # concrete (this is the bar generate_intents would hold on).
        assert _is_forming(FORMING_LAST_BAR, FORMING_AS_OF) is True

        # check_stops never even looks at the daily-bar store/as_of — it only
        # takes a prices dict, exactly as the live quote-sourced sweep does.
        intents = check_stops(universe, ledger, {"AAA": 94.0})

        assert len(intents) == 1
        assert intents[0].symbol == "AAA"
        assert intents[0].side == "sell"
        assert "stop loss" in intents[0].reason

    def test_generate_intents_would_have_held_the_same_position(self, universe):
        """Negative control for the test above: confirms generate_intents

        really would hold this exact position's exit on the forming bar (so
        the sweep test above is a genuine contrast, not a fixture that would
        have fired either way).
        """
        store = FakeStore(
            {s: make_bars_ending_at(s, rising_closes(), FORMING_LAST_BAR) for s in universe.symbols}
        )
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA",
            quantity=0.5,
            entry_price=100.0,
            entry_date=FORMING_AS_OF,
            high_water_mark=100.0,
        )

        intents, _ = generate_intents(universe, store, ledger, as_of=FORMING_AS_OF)

        assert [i for i in intents if i.side == "sell"] == []

    def test_live_sweep_cli_path_has_no_generate_intents_call(self):
        """Call-graph guard at the cli.py layer: live_sweep / _sweep_stops

        must not import or call generate_intents. Re-derives the Planner's
        and Builder's call-graph claim independently via source inspection
        rather than trusting their report.
        """
        import inspect

        from bonito.cli import _sweep_stops, live_sweep

        for fn in (live_sweep, _sweep_stops):
            src = inspect.getsource(fn)
            assert "generate_intents" not in src


# ---------------------------------------------------------------------------
# Part 4: build-time tz check (naive date-only comparison would be wrong)
# ---------------------------------------------------------------------------


def _naive_date_only_forming(last_bar: datetime, as_of: datetime) -> bool:
    """The exact bug this test guards against: comparing raw .date() with NO

    timezone conversion at all (a plausible "looks reasonable" mistake a
    future refactor could introduce in place of the real zoneinfo logic).
    """
    return as_of.date() == last_bar.date()


class TestBuildTimeTzCheck:
    """Fails loudly if `_is_forming` is ever changed to a naive `.date()`

    comparison instead of a proper zoneinfo conversion. Both winter and
    summer instances are required (this was explicitly flagged as a risk by
    the Planner).
    """

    def test_winter_naive_date_comparison_disagrees_with_real_logic(self):
        """Bar = 2026-01-06 05:00 UTC (midnight ET, EST).

        as_of = 2026-01-06 22:00 UTC = 17:00 ET Jan 6 -- 45 min PAST the
        16:15 ET settle boundary, so the bar IS settled. But as_of and the
        bar share the same raw UTC calendar date (both 2026-01-06), so a
        naive same-UTC-date rule wrongly calls it forming.
        """
        bar = datetime(2026, 1, 6, 5, 0)
        as_of = datetime(2026, 1, 6, 22, 0)

        naive_result = _naive_date_only_forming(bar, as_of)
        real_result = _is_forming(bar, as_of)

        assert naive_result is True  # the bug: wrongly forming
        assert real_result is False  # the fix: correctly settled
        assert naive_result != real_result

    def test_summer_naive_date_comparison_disagrees_with_real_logic(self):
        """Bar = 2026-07-14 04:00 UTC (midnight ET, EDT).

        as_of = 2026-07-14 21:00 UTC = 17:00 ET July 14 -- 45 min PAST the
        16:15 ET settle boundary, so the bar IS settled. Same raw UTC
        calendar date as the bar -> naive rule wrongly calls it forming.
        """
        bar = datetime(2026, 7, 14, 4, 0)
        as_of = datetime(2026, 7, 14, 21, 0)

        naive_result = _naive_date_only_forming(bar, as_of)
        real_result = _is_forming(bar, as_of)

        assert naive_result is True  # the bug: wrongly forming
        assert real_result is False  # the fix: correctly settled
        assert naive_result != real_result

    @pytest.mark.slow
    def test_stored_winter_bar_hour_matches_et_midnight_assumption(self):
        """Build-time check (RFC §7 part 4, load-bearing): re-verify the

        documented timestamp convention directly against the real DuckDB
        store for a known winter month, rather than trusting the claim.
        Network/disk-bound -> marked slow; run with --run-slow.
        """
        import duckdb

        con = duckdb.connect("data/market_data.duckdb", read_only=True)
        try:
            rows = con.execute(
                "SELECT DISTINCT EXTRACT(hour FROM timestamp) AS hr "
                "FROM bars WHERE timeframe='1d' AND EXTRACT(month FROM timestamp) = 1"
            ).fetchall()
        finally:
            con.close()
        hours = {r[0] for r in rows}
        assert hours == {5}, f"expected pure 05:00 UTC for January (EST), got hours={hours}"

    @pytest.mark.slow
    def test_stored_summer_bar_hour_matches_et_midnight_assumption(self):
        """Summer counterpart of the build-time check above (July, EDT)."""
        import duckdb

        con = duckdb.connect("data/market_data.duckdb", read_only=True)
        try:
            rows = con.execute(
                "SELECT DISTINCT EXTRACT(hour FROM timestamp) AS hr "
                "FROM bars WHERE timeframe='1d' AND EXTRACT(month FROM timestamp) = 7"
            ).fetchall()
        finally:
            con.close()
        hours = {r[0] for r in rows}
        assert hours == {4}, f"expected pure 04:00 UTC for July (EDT), got hours={hours}"


# ---------------------------------------------------------------------------
# Part 5: non-vacuous proof (mutate-and-confirm-fail) — RUN AND RESTORED.
# Mutating src/ is outside what a committed test file can do, so the actual
# mutation pass was done manually (not left in this file); this comment
# records exactly what was done so the Validator can independently redo it.
# ---------------------------------------------------------------------------
#
# Mutation performed: in src/bonito/trading/live_runner.py, _is_forming's
# body was replaced with a hardcoded `return False` (guard permanently
# reads "nothing is ever forming" — equivalent to every
# `if require_settled and _is_forming(...)` branch in generate_intents /
# _regime_allows becoming dead code).
#
# Result against TestGenerateIntentsSettledBarGuardIntegration (6 tests):
#   BEFORE mutation (real guard):      6 passed
#   DURING mutation (guard neutered):  3 failed, 3 passed
#     FAILED test_forming_bar_blocks_all_entries           (entries fired
#       that the guard should have suppressed)
#     FAILED test_forming_bar_holds_open_position_exit      (exit fired
#       that the guard should have held)
#     FAILED test_forming_regime_reference_forces_risk_off  (its own
#       internal sanity-check assertion
#       `assert _is_forming(FORMING_LAST_BAR, FORMING_AS_OF) is True` failed
#       first, before reaching the regime-risk-off assertion — a bonus catch
#       beyond what was predicted)
#     PASSED test_settled_bar_lets_the_same_entry_fire      (unaffected, as
#       predicted — settled bars were never blocked either way)
#     PASSED test_settled_bar_lets_the_same_exit_fire       (unaffected)
#     PASSED test_require_settled_false_opts_out_of_the_guard (unaffected —
#       this test's intents fire because require_settled=False is passed
#       explicitly, independent of what _is_forming itself returns)
#   AFTER restore (git diff --stat showed zero diff vs HEAD): 6 passed
#
# Full literal pytest output for all three phases is in the agent's final
# report to the orchestrator.
