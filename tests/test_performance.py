"""Tests for ledger performance reporting (bonito.trading.performance)."""

import json
from datetime import datetime, timedelta

from bonito.data.models import BarData
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.paper import PaperFill, PaperLedger, PaperPosition
from bonito.trading.performance import (
    build_performance_report,
    closed_trades_from_fills,
    period_returns,
    trade_stats,
)

START = datetime(2026, 1, 1)


def day(i: int) -> datetime:
    return START + timedelta(days=i)


def fill(symbol: str, side: str, price: float, on: datetime, qty: float = 1.0) -> PaperFill:
    return PaperFill(
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        notional=price * qty,
        reason="test",
        filled_at=on,
    )


class FakeStore:
    def __init__(self, bars: dict[str, BarData]):
        self.bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self.bars.get(symbol.upper())


def flat_bars(symbol: str, n: int, price: float = 100.0) -> BarData:
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[day(i) for i in range(n)],
        opens=[price] * n,
        highs=[price * 1.001] * n,
        lows=[price * 0.999] * n,
        closes=[price] * n,
        volumes=[1_000_000.0] * n,
    )


def make_universe(tmp_path, symbols=("AAA",)) -> UniverseConfig:
    strategy = {
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
    path = tmp_path / "s.json"
    path.write_text(json.dumps(strategy))
    return UniverseConfig(
        name="t",
        symbols=list(symbols),
        strategy_path=str(path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        risk={"starting_cash_usd": 1000.0},
    )


class TestClosedTradesFromFills:
    def test_no_fills(self):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        assert closed_trades_from_fills(ledger) == []

    def test_open_position_not_closed(self):
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [fill("AAA", "buy", 100.0, day(1))]
        assert closed_trades_from_fills(ledger) == []

    def test_simple_round_trip(self):
        ledger = PaperLedger(cash=1010.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("AAA", "sell", 110.0, day(2)),
        ]
        closed = closed_trades_from_fills(ledger)
        assert len(closed) == 1
        t = closed[0]
        assert t.symbol == "AAA"
        assert t.entry_price == 100.0
        assert t.exit_price == 110.0
        assert t.pnl == 10.0
        assert t.return_pct == 10.0

    def test_fifo_across_two_lots(self):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1), qty=1.0),
            fill("AAA", "buy", 200.0, day(2), qty=1.0),
            fill("AAA", "sell", 150.0, day(3), qty=1.5),
        ]
        closed = closed_trades_from_fills(ledger)
        # First 1.0 share closes against the $100 lot, the remaining 0.5
        # against the $200 lot — FIFO, not average cost.
        assert len(closed) == 2
        assert closed[0].entry_price == 100.0 and closed[0].quantity == 1.0
        assert closed[1].entry_price == 200.0 and closed[1].quantity == 0.5

    def test_symbols_isolated(self):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("BBB", "buy", 50.0, day(1)),
            fill("AAA", "sell", 120.0, day(2)),
        ]
        closed = closed_trades_from_fills(ledger)
        assert len(closed) == 1
        assert closed[0].symbol == "AAA"


class TestTradeStats:
    def test_no_trades(self):
        assert trade_stats([]) == (None, None)

    def test_all_wins_profit_factor_undefined(self):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("AAA", "sell", 110.0, day(2)),
        ]
        closed = closed_trades_from_fills(ledger)
        win_rate, pf = trade_stats(closed)
        assert win_rate == 100.0
        assert pf is None  # no losses to divide by

    def test_mixed_wins_and_losses(self):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("AAA", "sell", 110.0, day(2)),  # +10
            fill("BBB", "buy", 100.0, day(1)),
            fill("BBB", "sell", 95.0, day(2)),  # -5
        ]
        closed = closed_trades_from_fills(ledger)
        win_rate, pf = trade_stats(closed)
        assert win_rate == 50.0
        assert pf == 2.0  # 10 gross profit / 5 gross loss


class TestPeriodReturns:
    def test_empty(self):
        assert period_returns([], []) == []

    def test_short_history_skips_long_windows(self):
        dates = [day(0), day(1), day(2)]
        equity = [1000.0, 1010.0, 1020.0]
        results = period_returns(dates, equity, windows=(("1D", 1), ("1W", 5), ("All", None)))
        labels = [r.label for r in results]
        assert "1D" in labels and "All" in labels
        assert "1W" not in labels  # only 3 days of history, needs >5

    def test_1d_return_value(self):
        dates = [day(0), day(1), day(2)]
        equity = [1000.0, 1010.0, 1030.0]
        results = period_returns(dates, equity, windows=(("1D", 1),))
        assert results[0].return_pct == round((1030.0 / 1010.0 - 1) * 100, 2)

    def test_benchmark_alpha(self):
        dates = [day(0), day(1)]
        equity = [1000.0, 1100.0]  # +10%
        benchmark = {day(0): 100.0, day(1): 105.0}  # +5%
        results = period_returns(dates, equity, benchmark, windows=(("All", None),))
        r = results[0]
        assert r.return_pct == 10.0
        assert r.benchmark_return_pct == 5.0
        assert r.alpha_pct == 5.0

    def test_no_benchmark_leaves_alpha_none(self):
        dates = [day(0), day(1)]
        equity = [1000.0, 1100.0]
        results = period_returns(dates, equity, benchmark=None, windows=(("All", None),))
        assert results[0].benchmark_return_pct is None
        assert results[0].alpha_pct is None


class TestBuildPerformanceReport:
    def test_full_report(self, tmp_path):
        universe = make_universe(tmp_path)
        ledger = PaperLedger(cash=1010.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("AAA", "sell", 110.0, day(2)),
        ]
        store = FakeStore(
            {
                "AAA": flat_bars("AAA", 4, price=100.0),
                "SPY": flat_bars("SPY", 4, price=500.0),
            }
        )

        report = build_performance_report(universe, ledger, store, {}, end=day(3))

        assert report.realized_pnl == 0.0  # PaperLedger.realized_pnl unset by raw fill list
        assert len(report.closed_trades) == 1
        assert report.win_rate_pct == 100.0
        assert any(p.label == "Inception" for p in report.periods)

    def test_live_quotes_override_final_equity_point(self, tmp_path):
        universe = make_universe(tmp_path)
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [fill("AAA", "buy", 100.0, day(1))]
        # record_fill() keeps .positions and .fills in sync on every real
        # write path — set both by hand here to match that invariant.
        ledger.positions = {
            "AAA": PaperPosition(
                symbol="AAA",
                quantity=1.0,
                entry_price=100.0,
                entry_date=day(1),
                high_water_mark=100.0,
            )
        }
        store = FakeStore({"AAA": flat_bars("AAA", 3, price=100.0)})

        report = build_performance_report(universe, ledger, store, {"AAA": 150.0}, end=day(2))

        assert report.current_equity == 900.0 + 1 * 150.0

    def test_no_fills_yields_no_periods(self, tmp_path):
        universe = make_universe(tmp_path)
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        report = build_performance_report(universe, ledger, FakeStore({}), {}, end=day(3))
        assert report.periods == []
        assert report.closed_trades == []
