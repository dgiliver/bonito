"""Tests for PositionMonitor's sync P&L/drawdown methods (bonito.trading.monitor).

Scope (Decision #1, tasks/phase2_coordination.md): only the 5 sync methods —
unrealized_pnl, total_exposure, record_trade_pnl, update_peak_equity, drawdown.
refresh_positions/positions are intentionally NOT covered here — refresh_positions
is a one-line passthrough to broker.get_positions(), already covered by
tests/test_trading_broker.py, and pulling in a broker fake is out of scope for
this dependency-free file. PositionMonitor's __init__ requires a Broker, but
none of the 5 methods under test ever call it, so a plain object() sentinel is
sufficient and keeps the file free of broker mocking machinery.
"""

import pytest

from bonito.trading.models import Position
from bonito.trading.monitor import PositionMonitor


def make_monitor() -> PositionMonitor:
    """PositionMonitor with a sentinel broker — never invoked by the methods under test."""
    return PositionMonitor(broker=object())  # type: ignore[arg-type]


def make_position(
    symbol: str = "AAPL",
    qty: float = 10.0,
    side: str = "long",
    entry_price: float = 100.0,
    current_price: float = 110.0,
    unrealized_pnl: float = 100.0,
    market_value: float = 1100.0,
) -> Position:
    return Position(
        symbol=symbol,
        qty=qty,
        side=side,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=unrealized_pnl,
        market_value=market_value,
    )


class TestUnrealizedPnl:
    def test_sums_pnl_across_multiple_positions(self):
        monitor = make_monitor()
        monitor._positions = [
            make_position(symbol="AAPL", unrealized_pnl=100.0),
            make_position(symbol="GOOGL", unrealized_pnl=-40.0),
        ]
        assert monitor.unrealized_pnl == pytest.approx(60.0)

    def test_empty_positions_returns_zero(self):
        monitor = make_monitor()
        monitor._positions = []
        assert monitor.unrealized_pnl == 0.0


class TestTotalExposure:
    def test_sums_market_value_across_multiple_positions(self):
        monitor = make_monitor()
        monitor._positions = [
            make_position(symbol="AAPL", market_value=1100.0),
            make_position(symbol="GOOGL", market_value=2500.0),
        ]
        assert monitor.total_exposure == pytest.approx(3600.0)

    def test_empty_positions_returns_zero(self):
        monitor = make_monitor()
        monitor._positions = []
        assert monitor.total_exposure == 0.0


class TestRecordTradePnl:
    def test_accumulates_positive_and_negative_pnl_across_calls(self):
        monitor = make_monitor()
        monitor.record_trade_pnl(50.0)
        assert monitor._realized_pnl == pytest.approx(50.0)

        monitor.record_trade_pnl(-20.0)
        assert monitor._realized_pnl == pytest.approx(30.0)

        monitor.record_trade_pnl(75.0)
        assert monitor._realized_pnl == pytest.approx(105.0)

    def test_starts_at_zero(self):
        monitor = make_monitor()
        assert monitor._realized_pnl == 0.0


class TestUpdatePeakEquityAndDrawdown:
    def test_drawdown_is_zero_when_peak_still_zero(self):
        """Zero-peak guard (monitor.py:53): must not divide by zero."""
        monitor = make_monitor()
        monitor._positions = [make_position(market_value=1000.0)]
        assert monitor._peak_equity == 0.0
        assert monitor.drawdown == 0.0

    def test_peak_moves_up_on_new_high(self):
        monitor = make_monitor()
        monitor.update_peak_equity(1000.0)
        assert monitor._peak_equity == 1000.0

        monitor.update_peak_equity(1500.0)
        assert monitor._peak_equity == 1500.0

    def test_peak_never_falls_on_lower_equity(self):
        """The ratchet: a lower value than the current peak must not lower it."""
        monitor = make_monitor()
        monitor.update_peak_equity(1500.0)
        monitor.update_peak_equity(1000.0)
        assert monitor._peak_equity == 1500.0

    def test_peak_unchanged_on_equal_equity(self):
        monitor = make_monitor()
        monitor.update_peak_equity(1000.0)
        monitor.update_peak_equity(1000.0)
        assert monitor._peak_equity == 1000.0

    def test_drawdown_computed_against_current_market_value(self):
        monitor = make_monitor()
        monitor.update_peak_equity(1000.0)
        monitor._positions = [make_position(market_value=800.0)]
        assert monitor.drawdown == pytest.approx(0.2)

    def test_drawdown_zero_at_peak(self):
        monitor = make_monitor()
        monitor.update_peak_equity(1000.0)
        monitor._positions = [make_position(market_value=1000.0)]
        assert monitor.drawdown == pytest.approx(0.0)

    def test_drawdown_after_peak_ratchets_up_then_price_falls(self):
        """Full ratchet + drawdown interaction: peak climbs, then a pullback
        is measured against the highest peak ever seen, not the latest equity."""
        monitor = make_monitor()
        monitor.update_peak_equity(1000.0)
        monitor.update_peak_equity(1200.0)
        monitor.update_peak_equity(900.0)  # lower value — must not move the peak
        assert monitor._peak_equity == 1200.0

        monitor._positions = [make_position(market_value=900.0)]
        assert monitor.drawdown == pytest.approx((1200.0 - 900.0) / 1200.0)
