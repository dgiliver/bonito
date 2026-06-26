"""Tests for the account-level replay backtest (bonito.trading.portfolio_backtest)."""

import json
from datetime import datetime, timedelta

import pytest

from bonito.data.models import BarData
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.portfolio_backtest import ReplayStore, backtest_account

START = datetime(2026, 1, 1)


def day(i: int) -> datetime:
    return START + timedelta(days=i)


def make_ohlc(symbol: str, rows: list[tuple[float, float, float, float]]) -> BarData:
    """Bars from explicit (open, high, low, close) rows, one per day from START."""
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[day(i) for i in range(len(rows))],
        opens=[r[0] for r in rows],
        highs=[r[1] for r in rows],
        lows=[r[2] for r in rows],
        closes=[r[3] for r in rows],
        volumes=[1_000_000.0] * len(rows),
    )


def flat_bars(symbol: str, n: int, price: float = 100.0) -> BarData:
    return make_ohlc(symbol, [(price, price * 1.001, price * 0.999, price)] * n)


BASE_STRATEGY = {
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


def make_universe(tmp_path, strategy: dict, symbols: list[str], **risk) -> UniverseConfig:
    path = tmp_path / f"{strategy['name']}.json"
    path.write_text(json.dumps(strategy))
    return UniverseConfig(
        name="replay-test",
        symbols=symbols,
        strategy_path=str(path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        risk={
            "starting_cash_usd": 150.0,
            "max_position_usd": 30.0,
            "max_positions": 5,
            "max_daily_buys": 3,
            "min_cash_buffer_usd": 5.0,
            "allow_short": False,
            **risk,
        },
    )


class TestReplayStore:
    def test_point_in_time_slicing(self):
        replay = ReplayStore({"AAA": flat_bars("AAA", 10)})
        sliced = replay.get_bars("AAA", START, day(4))
        assert len(sliced) == 5
        assert sliced.timestamps[-1] == day(4)
        assert replay.get_bars("AAA", day(20), day(30)) is None
        assert replay.get_bars("ZZZ", START, day(4)) is None

    def test_bar_at_and_trading_days(self):
        replay = ReplayStore({"AAA": flat_bars("AAA", 3, price=50.0)})
        assert replay.bar_at("AAA", day(1))["close"] == 50.0
        assert replay.bar_at("AAA", day(9)) is None
        assert replay.trading_days(["AAA", "MISSING"], START, day(9)) == [day(i) for i in range(3)]


class TestCapsAndCompetition:
    def test_daily_buy_cap_then_position_fill(self, tmp_path):
        universe = make_universe(tmp_path, BASE_STRATEGY, ["AAA", "BBB", "CCC", "DDD"])
        replay = ReplayStore({s: flat_bars(s, 6) for s in universe.symbols})

        result = backtest_account(universe, replay, START, day(5))

        assert result.trades == []  # nothing exits on flat prices
        # Entries need 2 bars: 3 buys on day 1 (max_daily_buys), the 4th on day 2.
        assert result.max_concurrent_positions == 4
        assert len(result.open_positions) == 4
        # $150 - 4 × $30 = $30 cash left, above the $5 buffer.
        assert result.final_equity == pytest.approx(150.0, rel=1e-3)
        assert result.pct_days_in_market == pytest.approx(5 / 6)

    def test_cash_buffer_limits_entries(self, tmp_path):
        universe = make_universe(tmp_path, BASE_STRATEGY, ["AAA", "BBB"], starting_cash_usd=40.0)
        replay = ReplayStore({s: flat_bars(s, 4) for s in universe.symbols})

        result = backtest_account(universe, replay, START, day(3))

        # $40 cash, $5 buffer → one $30 position, then $5 available < $30
        # but >= $1 min order → second entry gets the remaining $5.
        assert result.max_concurrent_positions == 2
        assert result.final_equity == pytest.approx(40.0, rel=1e-3)


class TestIntradayStops:
    def stop_universe(self, tmp_path):
        return make_universe(tmp_path, BASE_STRATEGY, ["AAA"])

    def trailing_rows(self):
        return [
            (100, 100, 100, 100),  # d0 warmup
            (100, 100, 100, 100),  # d1: entry at close 100
            (100, 106, 100, 105),  # d2: HWM ratchets to 106 (high)
            (105, 105, 98, 99),  # d3: low pierces 106*0.95=100.7
        ]

    def test_trailing_stop_fills_at_level(self, tmp_path):
        universe = self.stop_universe(tmp_path)
        replay = ReplayStore({"AAA": make_ohlc("AAA", self.trailing_rows())})

        result = backtest_account(universe, replay, START, day(3))

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.exit_price == pytest.approx(106 * 0.95)
        assert trade.exit_date == day(3)
        assert "intraday" in trade.reason

    def test_daily_only_fills_at_close(self, tmp_path):
        universe = self.stop_universe(tmp_path)
        replay = ReplayStore({"AAA": make_ohlc("AAA", self.trailing_rows())})

        result = backtest_account(universe, replay, START, day(3), intraday_stops=False)

        assert len(result.trades) == 1
        # Without the sweep, the stop is only seen at the close: worse fill.
        assert result.trades[0].exit_price == pytest.approx(99.0)

    def test_gap_through_stop_fills_at_open(self, tmp_path):
        universe = self.stop_universe(tmp_path)
        rows = [
            (100, 100, 100, 100),
            (100, 100, 100, 100),  # entry at 100, stop level 95
            (90, 92, 88, 91),  # gaps below the level → fill at open
        ]
        replay = ReplayStore({"AAA": make_ohlc("AAA", rows)})

        result = backtest_account(universe, replay, START, day(2))
        assert result.trades[0].exit_price == pytest.approx(90.0)

    def test_take_profit_fills_at_level(self, tmp_path):
        universe = self.stop_universe(tmp_path)
        rows = [
            (100, 100, 100, 100),
            (100, 100, 100, 100),  # entry at 100, TP level 110
            (101, 112, 101, 108),  # high tags 110 intraday
        ]
        replay = ReplayStore({"AAA": make_ohlc("AAA", rows)})

        result = backtest_account(universe, replay, START, day(2))

        trade = result.trades[0]
        assert trade.exit_price == pytest.approx(110.0)
        assert "take profit" in trade.reason
        assert result.realized_pnl == pytest.approx((110 - 100) * 0.3)


class TestKillSwitch:
    def test_halt_flattens_and_persists(self, tmp_path):
        no_stop = {**BASE_STRATEGY, "name": "no_stop", "stop_loss": None, "take_profit": None}
        universe = make_universe(tmp_path, no_stop, ["AAA", "BBB", "CCC"])
        rows = [
            (100, 100, 100, 100),
            (100, 100, 100, 100),  # entries: 3 × $30 at 100, cash 60
            (50, 50, 50, 50),  # equity 60 + 0.9×50 = 105 → 30% DD → halt
            (50, 50, 50, 50),
            (50, 50, 50, 50),
        ]
        replay = ReplayStore({s: make_ohlc(s, rows) for s in universe.symbols})

        result = backtest_account(universe, replay, START, day(4))

        assert result.halted
        assert result.halt_date == day(2)
        assert "drawdown" in result.halt_reason
        assert result.open_positions == {}  # flattened
        assert len(result.trades) == 3
        assert all(t.exit_date == day(2) for t in result.trades)
        # No re-entries after the halt even though the entry rule still fires.
        assert result.equity_curve[-1] == pytest.approx(105.0)
        assert result.max_drawdown == pytest.approx(0.30, abs=0.01)


class TestRegimeAndLookahead:
    def test_risk_off_regime_blocks_every_entry(self, tmp_path):
        gated = {
            **BASE_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 5},
        }
        universe = make_universe(tmp_path, gated, ["AAA"])
        spy = make_ohlc("SPY", [(p, p, p, p) for p in range(120, 100, -2)])  # falling
        replay = ReplayStore({"AAA": flat_bars("AAA", 10), "SPY": spy})

        result = backtest_account(universe, replay, START, day(9))

        assert result.trades == []
        assert result.open_positions == {}
        assert result.final_equity == pytest.approx(150.0)

    def test_no_lookahead_entry_fires_on_signal_day(self, tmp_path):
        threshold = {
            **BASE_STRATEGY,
            "name": "threshold",
            "entry_rules": [
                {
                    "conditions": [{"left": "close", "comparison": "gt", "right": 100.0}],
                    "logic": "AND",
                    "side": "long",
                }
            ],
        }
        universe = make_universe(tmp_path, threshold, ["AAA"])
        prices = [90.0] * 5 + [105.0] * 3
        replay = ReplayStore({"AAA": make_ohlc("AAA", [(p, p, p, p) for p in prices])})

        result = backtest_account(universe, replay, START, day(7))

        # The rule first holds on day 5 — nothing before may enter.
        assert len(result.open_positions) == 1
        flat_until = result.equity_curve[:5]
        assert all(e == pytest.approx(150.0) for e in flat_until)


class TestSettledBarGuardReplayWiring:
    """Closes a real gap: START/day() above are naive midnight (e.g. 2026-01-01 00:00:00),

    which is NOT the production bar-timestamp convention. Converted to ET, naive midnight
    is always several hours into the *previous* day's evening — already well past every
    session's 16:15 ET settle boundary — so `_is_forming(d, d) -> False` for every `d` built
    from `day(i)` regardless of `require_settled`. That makes every existing replay test in
    this file (including test_no_lookahead_entry_fires_on_signal_day above) pass identically
    whether `portfolio_backtest.py:283` passes `require_settled=False` or the guard's own
    default of `True` — i.e. they do NOT exercise the replay call site's opt-out at all.

    Confirmed by hand before writing this test:
        _is_forming(datetime(2026, 1, 1), datetime(2026, 1, 1)) == False  (always settled)

    These tests instead use the REAL stored-bar convention — ET-midnight-of-session-date
    expressed as naive UTC (verified against data/market_data.duckdb: 05:00 UTC in EST/winter,
    04:00 UTC in EDT/summer) — under which a bar's own timestamp IS forming relative to
    itself (midnight ET is always before that same day's 16:15 ET settle):

        _is_forming(datetime(2026, 1, 5, 5, 0), datetime(2026, 1, 5, 5, 0)) == True

    so `require_settled=False` is the only thing that lets the replay act at all. Without it,
    `backtest_account` would silently produce zero trades and zero open positions over any
    window — exactly the "zero the entire replay" regression the settled-bar guard RFC
    (docs/RFC_SETTLED_BAR_GUARD.md §5.4) flagged as the reason the replay call site must pass
    require_settled=False.
    """

    WINTER_START = datetime(2026, 1, 5, 5, 0)  # ET-midnight-of-D as naive UTC, EST (winter)
    SUMMER_START = datetime(2026, 7, 6, 4, 0)  # ET-midnight-of-D as naive UTC, EDT (summer)

    def realistic_day(self, base: datetime, i: int) -> datetime:
        return base + timedelta(days=i)

    def _rising_bars_at(self, base: datetime, n: int = 6) -> BarData:
        closes = [100.0 + i for i in range(n)]
        return BarData(
            symbol="AAA",
            timeframe="1d",
            timestamps=[self.realistic_day(base, i) for i in range(n)],
            opens=closes,
            highs=[c * 1.01 for c in closes],
            lows=[c * 0.99 for c in closes],
            closes=closes,
            volumes=[1_000_000.0] * n,
        )

    def test_winter_replay_fires_an_entry_through_the_real_call_site(self, tmp_path):
        """Multi-day winter-convention replay: require_settled=False at the real call

        site (portfolio_backtest.py:283) must let the entry actually fire and the
        position accrue unrealized P&L as price rises.
        """
        universe = make_universe(tmp_path, BASE_STRATEGY, ["AAA"])
        bars = self._rising_bars_at(self.WINTER_START, n=6)
        replay = ReplayStore({"AAA": bars})

        result = backtest_account(
            universe, replay, self.WINTER_START, self.realistic_day(self.WINTER_START, 5)
        )

        assert "AAA" in result.open_position_entries
        assert result.open_position_entries["AAA"].entry_price == pytest.approx(101.0)
        assert result.open_positions["AAA"] > 0  # unrealized P&L, price rose post-entry
        assert result.final_equity > result.starting_cash

    def test_summer_replay_fires_an_entry_through_the_real_call_site(self, tmp_path):
        """Same proof as the winter case, but with the EDT (04:00 UTC) bar convention —

        both DST seasons must independently exercise require_settled=False correctly.
        """
        universe = make_universe(tmp_path, BASE_STRATEGY, ["AAA"])
        bars = self._rising_bars_at(self.SUMMER_START, n=6)
        replay = ReplayStore({"AAA": bars})

        result = backtest_account(
            universe, replay, self.SUMMER_START, self.realistic_day(self.SUMMER_START, 5)
        )

        assert "AAA" in result.open_position_entries
        assert result.open_position_entries["AAA"].entry_price == pytest.approx(101.0)
        assert result.open_positions["AAA"] > 0
        assert result.final_equity > result.starting_cash


class TestResultIntegrity:
    def test_determinism_and_accounting(self, tmp_path):
        universe = make_universe(tmp_path, BASE_STRATEGY, ["AAA", "BBB"])
        rows = [
            (100, 100, 100, 100),
            (100, 100, 100, 100),
            (102, 112, 102, 108),  # AAA TP fires at 110
            (108, 109, 107, 108),
            (108, 109, 107, 108),
        ]
        bars = {"AAA": make_ohlc("AAA", rows), "BBB": flat_bars("BBB", 5)}

        r1 = backtest_account(universe, ReplayStore(bars), START, day(4))
        r2 = backtest_account(universe, ReplayStore(bars), START, day(4))

        assert r1.equity_curve == r2.equity_curve
        assert [t.exit_price for t in r1.trades] == [t.exit_price for t in r2.trades]
        # final equity == starting cash + realized + unrealized
        assert r1.final_equity == pytest.approx(
            r1.starting_cash + r1.realized_pnl + r1.unrealized_pnl, abs=0.01
        )
        dates = [t.exit_date for t in r1.trades]
        assert dates == sorted(dates)
        assert r1.window_metrics(START, day(4)).trades == len(r1.trades)
