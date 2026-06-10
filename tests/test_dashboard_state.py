"""Tests for the dashboard state builder (bonito.dashboard.state)."""

import json
from datetime import datetime, timedelta

import pytest

from bonito.dashboard.state import build_dashboard_state
from bonito.data.models import BarData
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.paper import PaperLedger, PaperPosition
from bonito.trading.signals import TradeIntent

LAST_BAR = datetime(2026, 6, 5)
AS_OF = datetime(2026, 6, 8)


def make_bars(symbol: str, closes: list[float], end: datetime = LAST_BAR) -> BarData:
    n = len(closes)
    start = end - timedelta(days=n - 1)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[start + timedelta(days=i) for i in range(n)],
        opens=closes,
        highs=[c * 1.01 for c in closes],
        lows=[c * 0.99 for c in closes],
        closes=closes,
        volumes=[1_000_000.0] * n,
    )


class FakeStore:
    def __init__(self, bars: dict[str, BarData]):
        self.bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self.bars.get(symbol)


STRATEGY = {
    "name": "dash_test",
    "description": "test strategy",
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
    "exit_rules": [],
    "stop_loss": {"type": "trailing_atr", "value": 2.0, "atr_period": 14},
    "take_profit": {"type": "percent", "value": 0.10},
    "regime_filter": {"symbol": "SPY", "sma_period": 5},
}


@pytest.fixture
def universe(tmp_path):
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(json.dumps(STRATEGY))
    return UniverseConfig(
        name="dash-universe",
        symbols=["AAA", "BBB"],
        strategy_path=str(strategy_path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        risk={
            "starting_cash_usd": 5000.0,
            "max_position_usd": 1000.0,
            "max_positions": 5,
            "max_daily_buys": 3,
            "min_cash_buffer_usd": 100.0,
            "allow_short": False,
            "max_drawdown_halt": 0.25,
        },
    )


def store_with(universe_symbols: list[str], spy_up: bool = True) -> FakeStore:
    flat = [100.0] * 30
    bars = {s: make_bars(s, flat) for s in universe_symbols}
    spy = [100.0 + i for i in range(30)] if spy_up else [130.0 - i for i in range(30)]
    bars["SPY"] = make_bars("SPY", spy)
    return FakeStore(bars)


def open_position(
    ledger: PaperLedger, symbol: str, entry: float, qty: float, hwm: float | None = None
):
    ledger.positions[symbol] = PaperPosition(
        symbol=symbol,
        quantity=qty,
        entry_price=entry,
        entry_date=AS_OF - timedelta(days=3),
        high_water_mark=hwm if hwm is not None else entry,
        strategy_name="dash_test",
    )


class TestDashboardState:
    def test_empty_ledger(self, universe):
        ledger = PaperLedger(cash=5000.0, starting_cash=5000.0)
        state = build_dashboard_state(universe, ledger, store_with(universe.symbols), as_of=AS_OF)

        assert state["mode"] == "paper"
        assert state["account"]["equity"] == 5000.0
        assert state["positions"] == []
        assert state["fills"] == []
        assert state["equity_curve"] == []
        assert state["universe"]["strategy_name"] == "dash_test"

    def test_position_row_pnl_and_levels(self, universe):
        # Flat bars at 100 → ATR = 2.0 (range 99..101 each bar).
        # Entry 90, hwm 100 → trailing stop = 100 - 2*2 = 96; TP = 99.
        ledger = PaperLedger(cash=4000.0, starting_cash=5000.0)
        open_position(ledger, "AAA", entry=90.0, qty=10.0, hwm=100.0)
        state = build_dashboard_state(universe, ledger, store_with(universe.symbols), as_of=AS_OF)

        row = state["positions"][0]
        assert row["symbol"] == "AAA"
        assert row["current_price"] == 100.0
        assert row["market_value"] == 1000.0
        assert row["unrealized_pnl"] == pytest.approx(100.0)
        assert row["unrealized_pct"] == pytest.approx(11.11, abs=0.01)
        assert row["stop_price"] == pytest.approx(96.0)
        assert row["stop_distance_pct"] == pytest.approx(4.0)
        assert row["take_profit_price"] == pytest.approx(99.0)
        assert row["days_held"] == 3
        assert not row["stale"]

        assert state["account"]["equity"] == pytest.approx(5000.0)
        assert state["account"]["open_positions"] == 1

    def test_regime_status_risk_on_and_off(self, universe):
        ledger = PaperLedger(cash=5000.0, starting_cash=5000.0)
        on = build_dashboard_state(
            universe, ledger, store_with(universe.symbols, spy_up=True), as_of=AS_OF
        )
        off = build_dashboard_state(
            universe, ledger, store_with(universe.symbols, spy_up=False), as_of=AS_OF
        )
        assert on["regime"]["risk_on"] is True
        assert off["regime"]["risk_on"] is False
        assert on["regime"]["symbol"] == "SPY"
        assert on["regime"]["close"] is not None
        assert on["regime"]["sma"] is not None

    def test_halt_and_drawdown_surface(self, universe):
        ledger = PaperLedger(cash=4000.0, starting_cash=5000.0, peak_equity=5000.0)
        ledger.halt("drawdown 30% >= 25% cap")
        state = build_dashboard_state(universe, ledger, store_with(universe.symbols), as_of=AS_OF)

        assert state["account"]["halted"] is True
        assert "drawdown" in state["account"]["halt_reason"]
        assert state["account"]["drawdown_pct"] == pytest.approx(20.0)  # 4000 vs 5000 peak

    def test_equity_curve_from_fills(self, universe):
        ledger = PaperLedger(cash=5000.0, starting_cash=5000.0)
        intent = TradeIntent(
            symbol="AAA",
            side="buy",
            dollar_amount=1000.0,
            reason="test",
            signal_price=100.0,
            signal_date=AS_OF - timedelta(days=3),
            strategy_name="dash_test",
        )
        fill = ledger.apply_buy(intent, fill_price=100.0)
        fill.filled_at = AS_OF - timedelta(days=3)

        state = build_dashboard_state(universe, ledger, store_with(universe.symbols), as_of=AS_OF)
        curve = state["equity_curve"]
        assert len(curve) == 4  # fill day through as_of inclusive
        # Flat closes at 100 → equity stays at starting cash all the way.
        assert all(p["equity"] == pytest.approx(5000.0) for p in curve)

    def test_stale_data_flagged(self, universe):
        old = AS_OF - timedelta(days=30)
        bars = {s: make_bars(s, [100.0] * 30, end=old) for s in universe.symbols}
        bars["SPY"] = make_bars("SPY", [100.0 + i for i in range(30)], end=old)
        ledger = PaperLedger(cash=4000.0, starting_cash=5000.0)
        open_position(ledger, "AAA", entry=90.0, qty=10.0)

        state = build_dashboard_state(universe, ledger, FakeStore(bars), as_of=AS_OF)
        assert state["positions"][0]["stale"] is True
        assert state["data_freshness"]["stale"] is True

    def test_fills_newest_first(self, universe):
        ledger = PaperLedger(cash=5000.0, starting_cash=5000.0)
        for i, symbol in enumerate(["AAA", "BBB"]):
            intent = TradeIntent(
                symbol=symbol,
                side="buy",
                dollar_amount=500.0,
                reason=f"entry {i}",
                signal_price=100.0,
                signal_date=AS_OF,
                strategy_name="dash_test",
            )
            fill = ledger.apply_buy(intent, fill_price=100.0)
            fill.filled_at = AS_OF - timedelta(days=2 - i)

        state = build_dashboard_state(universe, ledger, store_with(universe.symbols), as_of=AS_OF)
        assert [f["symbol"] for f in state["fills"]] == ["BBB", "AAA"]
