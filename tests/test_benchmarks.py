"""Tests for market-relative benchmarks (bonito.trading.benchmarks) and their wiring.

Report-only by contract: these numbers must never gate trading, never fail a
refresh, and never change the tracking status.
"""

import json
from datetime import date, datetime, timedelta

import pytest
from typer.testing import CliRunner

from bonito.cli import app
from bonito.data.models import BarData
from bonito.trading.benchmarks import (
    HOLD_UNIVERSE,
    benchmark_series,
    compare_to_market,
    hold_universe_curve,
    ledger_market_comparison,
    refresh_benchmarks,
    window_return,
)
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.paper import PaperFill, PaperLedger, PaperPosition

START = datetime(2026, 1, 1, 5)  # bar timestamps carry a time-of-day, like the real store


def day(i: int) -> datetime:
    return START + timedelta(days=i)


def bars(symbol: str, closes: list[float]) -> BarData:
    n = len(closes)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[day(i) for i in range(n)],
        opens=closes,
        highs=closes,
        lows=closes,
        closes=closes,
        volumes=[1.0] * n,
    )


class FakeStore:
    def __init__(self, data: dict[str, BarData], raise_for: tuple[str, ...] = ()):
        self.data = data
        self.raise_for = raise_for

    def get_bars(self, symbol, start, end, timeframe="1d"):
        if symbol in self.raise_for:
            raise RuntimeError("store down")
        b = self.data.get(symbol)
        if b is None:
            return None
        # Filter by [start, end] on the bar timestamp, like the real DuckDB store.
        keep = [i for i, t in enumerate(b.timestamps) if start <= t <= end]
        if not keep:
            return None
        pick = lambda xs: [xs[i] for i in keep]  # noqa: E731
        return BarData(
            symbol=symbol,
            timeframe="1d",
            timestamps=pick(b.timestamps),
            opens=pick(b.opens),
            highs=pick(b.highs),
            lows=pick(b.lows),
            closes=pick(b.closes),
            volumes=pick(b.volumes),
        )

    def ingest_from_yahoo(self, symbol, start, end, timeframe="1d"):
        if symbol in self.raise_for:
            raise RuntimeError("yahoo down")
        return 10


def make_universe(tmp_path, symbols=("AAA", "BBB")) -> UniverseConfig:
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "name": "s",
                "symbols": list(symbols),
                "timeframe": "1d",
                "indicators": [],
                "entry_rules": [
                    {
                        "conditions": [{"left": "close", "comparison": "gt", "right": 0.0}],
                        "logic": "AND",
                        "side": "long",
                    }
                ],
                "exit_rules": [],
            }
        )
    )
    return UniverseConfig(
        name="t",
        symbols=list(symbols),
        strategy_path=str(path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        risk={"starting_cash_usd": 1000.0},
    )


D = [day(i).date() for i in range(5)]


class TestHoldUniverseCurve:
    def test_equal_weight_daily_rebalanced(self):
        # +10% and -10% on the same day average to 0; then both +5% → +5%.
        closes = {"A": {D[0]: 100, D[1]: 110, D[2]: 115.5}, "B": {D[0]: 100, D[1]: 90, D[2]: 94.5}}
        curve = hold_universe_curve(closes, D[:3])
        assert curve[D[1]] == pytest.approx(1.0)
        assert curve[D[2]] == pytest.approx(1.05)

    def test_symbol_listing_mid_window_joins_from_its_first_close(self):
        closes = {"A": {D[0]: 100, D[1]: 110, D[2]: 110}, "B": {D[1]: 50, D[2]: 60}}
        curve = hold_universe_curve(closes, D[:3])
        assert curve[D[1]] == pytest.approx(1.10)  # B's listing day isn't a return
        assert curve[D[2]] == pytest.approx(1.10 * 1.10)  # A 0%, B +20% → +10%

    def test_missing_bar_keeps_the_move_across_the_gap(self):
        """A symbol missing day 1 still contributes its day0→day2 move on day 2."""
        closes = {"A": {D[0]: 100, D[2]: 120}, "B": {D[0]: 100, D[1]: 100, D[2]: 100}}
        curve = hold_universe_curve(closes, D[:3])
        assert curve[D[2]] == pytest.approx(1.10)  # (+20% + 0%) / 2

    def test_day_with_no_data_carries_value(self):
        closes = {"A": {D[0]: 100, D[2]: 120}}
        curve = hold_universe_curve(closes, D[:3])
        assert curve[D[1]] == pytest.approx(1.0)  # no fabricated return


class TestWindowReturn:
    def test_first_on_or_after_last_on_or_before(self):
        s = {D[0]: 100.0, D[2]: 110.0, D[4]: 121.0}
        assert window_return(s, D[1], D[3]) is None  # only one point inside
        assert window_return(s, D[0], D[4]) == pytest.approx(0.21)
        assert window_return(s, D[1], D[4]) == pytest.approx(0.10)

    def test_empty_is_none(self):
        assert window_return({}, D[0], D[4]) is None


class TestBenchmarkSeries:
    def test_includes_spy_qqq_and_hold_universe(self, tmp_path):
        store = FakeStore({s: bars(s, [100, 101, 102]) for s in ("SPY", "QQQ", "AAA", "BBB")})
        out = benchmark_series(store, make_universe(tmp_path), day(0), day(2))
        assert set(out) == {"SPY", "QQQ", HOLD_UNIVERSE}

    def test_low_universe_coverage_reads_na_not_a_cherry_picked_hold(self, tmp_path):
        """The intraday container only refreshes open positions: 1 of 4 symbols
        is not 'the universe' — hold-universe must be absent, not computed."""
        u = make_universe(tmp_path, symbols=("AAA", "BBB", "CCC", "DDD"))
        store = FakeStore({"SPY": bars("SPY", [1, 2, 3]), "AAA": bars("AAA", [1, 2, 3])})
        assert HOLD_UNIVERSE not in benchmark_series(store, u, day(0), day(2))

    def test_store_errors_degrade_to_absent(self, tmp_path):
        store = FakeStore({"AAA": bars("AAA", [1, 2])}, raise_for=("SPY", "QQQ", "BBB"))
        out = benchmark_series(store, make_universe(tmp_path), day(0), day(1))
        assert "SPY" not in out and "QQQ" not in out


class TestCompareToMarket:
    def test_excess_points_and_na(self):
        series = {"SPY": {D[0]: 100.0, D[4]: 103.0}}
        cmp = compare_to_market(-12.0, D[0], D[4], series, labels=("SPY", "QQQ"))
        assert cmp.benchmark_return_pct == {"SPY": 3.0, "QQQ": None}
        assert cmp.excess_pts == {"SPY": -15.0, "QQQ": None}
        line = cmp.line()
        assert "SPY +3.00% (-15.00pts)" in line and "QQQ n/a" in line


class TestLedgerMarketComparison:
    def test_no_fills_is_none(self, tmp_path):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        assert (
            ledger_market_comparison(ledger, FakeStore({}), make_universe(tmp_path), {}, day(4))
            is None
        )

    def test_marks_unpriced_at_last_close_and_anchors_first_fill_session(self, tmp_path):
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [
            PaperFill(
                symbol="AAA",
                side="buy",
                quantity=1.0,
                price=100.0,
                notional=100.0,
                reason="t",
                filled_at=day(2),
            )
        ]
        ledger.positions = {
            "AAA": PaperPosition(
                symbol="AAA",
                quantity=1.0,
                entry_price=100.0,
                entry_date=day(2),
                high_water_mark=100.0,
            )
        }
        store = FakeStore(
            {
                "AAA": bars("AAA", [100, 100, 100, 100, 150]),  # last close 150, entry 100
                "SPY": bars("SPY", [100, 110, 120, 120, 132]),
            }
        )
        cmp = ledger_market_comparison(ledger, store, make_universe(tmp_path), {}, day(4))
        # equity 900 + 150 = 1050 → +5%, NOT +0% (entry-price fallback)
        assert cmp.account_return_pct == pytest.approx(5.0)
        # SPY runs from the first fill's session close (day 2 = 120), the same anchor
        # as `live performance` — not the prior close: 132/120 = +10%
        assert cmp.since == day(2).date()
        assert cmp.benchmark_return_pct["SPY"] == pytest.approx(10.0)

    def test_stale_benchmark_reads_na_not_a_shorter_window(self, tmp_path):
        """A frozen series (refresh failing) must not pass for a current return."""
        series = {"SPY": {D[0]: 100.0, D[1]: 110.0}}
        until = D[1] + timedelta(days=30)
        cmp = compare_to_market(0.0, D[0], until, series, labels=("SPY",))
        assert cmp.benchmark_return_pct["SPY"] is None
        fresh = compare_to_market(0.0, D[0], D[1] + timedelta(days=3), series, labels=("SPY",))
        assert fresh.benchmark_return_pct["SPY"] == pytest.approx(10.0)


class TestRefreshIsNeverFatal:
    def test_refresh_benchmarks_swallows_failures(self, tmp_path):
        out = refresh_benchmarks(make_universe(tmp_path), FakeStore({}, raise_for=("QQQ",)))
        assert out == {"SPY": 10, "QQQ": -1}

    def test_live_refresh_exits_0_when_only_benchmarks_fail(self, tmp_path, monkeypatch):
        """`live refresh` failing fails the paper workflow's whole cycle — a
        benchmark outage must warn, never flip the exit code."""
        import bonito.cli as cli
        import bonito.trading.live_runner as lr

        u = make_universe(tmp_path)
        monkeypatch.setattr(cli, "_load_universe", lambda path: u)
        monkeypatch.setattr(cli, "_get_store", lambda: FakeStore({}, raise_for=("SPY", "QQQ")))
        monkeypatch.setattr(lr, "refresh_data", lambda universe, store: {"AAA": 5, "BBB": 5})
        result = CliRunner().invoke(app, ["live", "refresh"])
        assert result.exit_code == 0, result.output
        assert "benchmark refresh failed" in " ".join(result.output.split())


class TestNeverGates:
    def test_trading_path_does_not_import_benchmarks(self):
        """Same invariant as health: the decision path must not depend on it."""
        import inspect

        import bonito.trading.live_runner as lr

        assert "benchmarks" not in inspect.getsource(lr)

    def test_tracking_status_unaffected_when_market_comparison_fails(self, tmp_path, monkeypatch):
        import bonito.trading.tracking as tr

        u = make_universe(tmp_path, symbols=("AAA",))
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [
            PaperFill(
                symbol="AAA",
                side="buy",
                quantity=1.0,
                price=100.0,
                notional=100.0,
                reason="t",
                filled_at=day(2),
            )
        ]
        store = FakeStore({"AAA": bars("AAA", [100.0] * 6), "SPY": bars("SPY", [100.0] * 6)})
        baseline = tr.run_tracking(u, ledger, store, end=day(5))
        assert baseline.market is not None

        def boom(*a, **k):
            raise RuntimeError("benchmarks broken")

        monkeypatch.setattr(tr, "ledger_market_comparison", boom)
        broken = tr.run_tracking(u, ledger, store, end=day(5))
        assert broken.market is None
        assert broken.status == baseline.status and broken.reasons == baseline.reasons


class TestPerformanceMarketColumns:
    def test_period_market_returns_populated(self, tmp_path):
        from bonito.trading.performance import build_performance_report

        u = make_universe(tmp_path, symbols=("AAA",))
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [
            PaperFill(
                symbol="AAA",
                side="buy",
                quantity=1.0,
                price=100.0,
                notional=100.0,
                reason="t",
                filled_at=day(0),
            )
        ]
        store = FakeStore(
            {
                "AAA": bars("AAA", [100.0] * 8),
                "SPY": bars("SPY", [100.0, 100, 100, 100, 100, 100, 100, 110.0]),
                "QQQ": bars("QQQ", [100.0] * 7 + [95.0]),
            }
        )
        report = build_performance_report(u, ledger, store, {}, day(7))
        inception = next(p for p in report.periods if p.label == "Inception")
        assert inception.market["SPY"] == pytest.approx(10.0)
        assert inception.market["QQQ"] == pytest.approx(-5.0)
        assert inception.market[HOLD_UNIVERSE] == pytest.approx(0.0)


def test_dates_are_compared_as_calendar_days():
    """Bars carry 04:00/05:00 timestamps; windows are by calendar date."""
    assert window_return(
        {date(2026, 1, 1): 1.0, date(2026, 1, 2): 2.0}, date(2026, 1, 1), date(2026, 1, 2)
    ) == pytest.approx(1.0)


def test_late_day_fill_timestamp_still_anchors_on_that_session(tmp_path):
    """Real fills land ~21:32 while bars are stamped 05:00: querying bars from the
    fill's timestamp dropped that session and started the benchmarks a day late
    (status said SPY +2.75% while performance said +2.19% for the same account)."""
    ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
    ledger.fills = [
        PaperFill(
            symbol="AAA",
            side="buy",
            quantity=0.0,
            price=100.0,
            notional=0.0,
            reason="no_fill: queued",
            filled_at=day(2) + timedelta(hours=16),
        )
    ]
    store = FakeStore({"SPY": bars("SPY", [100, 110, 120, 126, 132])})
    cmp = ledger_market_comparison(ledger, store, make_universe(tmp_path), {}, day(4))
    assert cmp.benchmark_return_pct["SPY"] == pytest.approx(10.0)  # 120 → 132, not 126 → 132


def test_performance_columns_null_a_stale_benchmark(tmp_path):
    """Same gate as `live status`: a frozen QQQ reads n/a in `live performance`."""
    from bonito.trading.performance import build_performance_report

    u = make_universe(tmp_path, symbols=("AAA",))
    ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
    ledger.fills = [
        PaperFill(
            symbol="AAA",
            side="buy",
            quantity=1.0,
            price=100.0,
            notional=100.0,
            reason="t",
            filled_at=day(0),
        )
    ]
    n = 20
    store = FakeStore(
        {
            "AAA": bars("AAA", [100.0] * n),
            "SPY": bars("SPY", [100.0] * (n - 1) + [110.0]),
            "QQQ": bars("QQQ", [100.0, 120.0]),  # froze on day 1
        }
    )
    inception = next(
        p
        for p in build_performance_report(u, ledger, store, {}, day(n - 1)).periods
        if p.label == "Inception"
    )
    assert inception.market["SPY"] == pytest.approx(10.0)
    assert inception.market["QQQ"] is None
