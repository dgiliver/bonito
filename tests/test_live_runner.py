"""Tests for the daily live runner (bonito.trading.live_runner)."""

import json
from datetime import UTC as UTC_TZ
from datetime import datetime, timedelta

import pytest

from bonito.data.models import BarData
from bonito.trading.live_runner import (
    PendingOrderOutcome,
    UniverseConfig,
    check_stops,
    execute_paper,
    generate_intents,
    in_intraday_sweep_window,
    pending_orders,
    preflight,
    read_cycle_lock,
    release_cycle_lock,
    resolve_pending_fills,
    save_intents,
    try_acquire_cycle_lock,
)
from bonito.trading.paper import PaperFill, PaperLedger
from bonito.trading.signals import TradeIntent

LAST_BAR = datetime(2026, 6, 5)
AS_OF = datetime(2026, 6, 8)  # within staleness window


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
    """Duck-typed MarketDataStore returning canned bars."""

    def __init__(self, bars: dict[str, BarData]):
        self.bars = bars

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self.bars.get(symbol)


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


@pytest.fixture
def universe(tmp_path):
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(json.dumps(ALWAYS_ENTER_STRATEGY))
    return UniverseConfig(
        name="test",
        symbols=["AAA", "BBB", "CCC", "DDD"],
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


def uptrend_store(symbols: list[str]) -> FakeStore:
    closes = [100.0 + i for i in range(30)]
    return FakeStore({s: make_bars(s, closes) for s in symbols})


class TestGenerateIntents:
    def test_generates_capped_buys(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, prices = generate_intents(universe, store, ledger, as_of=AS_OF)

        buys = [i for i in intents if i.side == "buy"]
        assert len(buys) == 3  # max_daily_buys, not all 4 symbols
        assert all(i.dollar_amount == 30.0 for i in buys)
        assert all(i.symbol in universe.symbols for i in buys)
        assert prices["AAA"] == 129.0

    def test_respects_max_positions(self, universe):
        universe.risk.max_positions = 2
        universe.risk.max_daily_buys = 5
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert len([i for i in intents if i.side == "buy"]) == 2

    def test_open_positions_count_against_cap(self, universe):
        universe.risk.max_positions = 2
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        # Entry near current price (~+0.8%) so neither stop nor TP fires
        _open_position(ledger, "AAA", quantity=0.3, entry_price=128.0, hwm=129.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert [i for i in intents if i.side == "sell"] == []
        buys = [i for i in intents if i.side == "buy"]
        assert len(buys) == 1
        assert buys[0].symbol != "AAA"  # never re-enter an open symbol

    def test_pending_exit_frees_position_slot(self, universe):
        universe.risk.max_positions = 2
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        # Deep red position → exit fires → slot frees for a second buy
        _open_position(ledger, "AAA", quantity=0.3, entry_price=200.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert len([i for i in intents if i.side == "sell"]) == 1
        assert len([i for i in intents if i.side == "buy"]) == 2

    def test_unresolved_pending_buy_blocks_a_second_entry(self, universe):
        """A prior cycle's buy that queued and hasn't resolved has no
        ledger.positions entry yet — the entry loop must still not place a
        second real buy for it."""
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.fills.append(
            PaperFill(
                symbol="AAA", side="buy", quantity=0.0, price=100.0, notional=0.0,
                reason="no_fill: order queued, market closed",
                filled_at=datetime(2026, 6, 5, tzinfo=UTC_TZ), broker_order_id="order-1",
            )
        )
        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        buys = [i for i in intents if i.side == "buy"]
        assert "AAA" not in {i.symbol for i in buys}  # not re-bought
        # A resolved sentinel (dead order) does NOT block — that symbol is free.
        ledger.fills[0].reason += "; resolved=cancelled"
        intents2, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert "AAA" in {i.symbol for i in intents2 if i.side == "buy"}

    def test_cash_buffer_blocks_buys(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=5.5, starting_cash=150.0)  # only $0.50 above buffer

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert [i for i in intents if i.side == "buy"] == []

    def test_partial_cash_shrinks_position(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=25.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        buys = [i for i in intents if i.side == "buy"]
        assert len(buys) == 1
        assert buys[0].dollar_amount == 20.0  # 25 - 5 buffer

    def test_stale_data_skipped(self, universe):
        old_end = AS_OF - timedelta(days=30)
        closes = [100.0 + i for i in range(30)]
        store = FakeStore({s: make_bars(s, closes, end=old_end) for s in universe.symbols})
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, prices = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert intents == []
        assert prices == {}

    def test_missing_data_skipped(self, universe):
        store = FakeStore({})
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert intents == []

    def test_exit_generated_for_stop_breach(self, universe):
        # Position entered at 200, price collapsed to ~129 → trailing stop fires
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=200.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        sells = [i for i in intents if i.side == "sell"]
        assert len(sells) == 1
        assert sells[0].symbol == "AAA"
        assert sells[0].quantity == 0.5
        assert "stop loss" in sells[0].reason

    def test_take_profit_exit(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        # Entry at 100, last close 129 = +29% > 10% TP. Keep hwm at the
        # current price so the trailing stop doesn't fire first.
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=129.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        sells = [i for i in intents if i.side == "sell"]
        assert len(sells) == 1
        assert "take profit" in sells[0].reason


class TestExecutePaper:
    def test_sells_run_before_buys(self, universe):
        ledger = PaperLedger(cash=1.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)

        intents = [
            _intent("BBB", "buy", dollar_amount=30.0),
            _intent("AAA", "sell", quantity=1.0),
        ]
        prices = {"AAA": 110.0, "BBB": 50.0}
        fills, errors = execute_paper(ledger, intents, prices)

        assert errors == []
        assert [f.side for f in fills] == ["sell", "buy"]
        # Sell freed $110, buy spent $30
        assert ledger.cash == pytest.approx(81.0)

    def test_missing_price_is_an_error_not_silent(self, universe):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        fills, errors = execute_paper(ledger, [_intent("AAA", "buy", dollar_amount=30.0)], {})
        assert fills == []
        assert len(errors) == 1
        assert "no fill price" in errors[0]

    def test_rejection_does_not_abort_batch(self, universe):
        ledger = PaperLedger(cash=35.0, starting_cash=150.0)
        intents = [
            _intent("AAA", "buy", dollar_amount=30.0),
            _intent("BBB", "buy", dollar_amount=30.0),  # insufficient after first
        ]
        fills, errors = execute_paper(ledger, intents, {"AAA": 100.0, "BBB": 100.0})
        assert len(fills) == 1
        assert len(errors) == 1


class TestCheckStops:
    def test_stop_triggers_intraday(self, universe):
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=100.0)

        intents = check_stops(universe, ledger, {"AAA": 94.0})  # 5% trailing stop
        assert len(intents) == 1
        assert intents[0].side == "sell"
        assert "stop loss" in intents[0].reason

    def test_no_trigger_above_stop(self, universe):
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=100.0)

        intents = check_stops(universe, ledger, {"AAA": 99.0})
        assert intents == []

    def test_hwm_updates_on_new_high(self, universe):
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=100.0)

        check_stops(universe, ledger, {"AAA": 108.0})
        assert ledger.positions["AAA"].high_water_mark == 108.0

    def test_take_profit_intraday(self, universe):
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        # hwm tracks the price so trailing stop stays quiet; +12% hits TP
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=112.0)

        intents = check_stops(universe, ledger, {"AAA": 112.0})
        assert len(intents) == 1
        assert "take profit" in intents[0].reason

    def test_missing_price_holds(self, universe):
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0)
        assert check_stops(universe, ledger, {}) == []


class TestSaveIntents:
    def test_writes_json_file(self, tmp_path):
        intents = [_intent("AAA", "buy", dollar_amount=30.0)]
        path = save_intents(intents, directory=tmp_path)
        loaded = json.loads(path.read_text())
        assert loaded[0]["symbol"] == "AAA"
        assert loaded[0]["side"] == "buy"


def _pending_sentinel(symbol, side, order_id, price=100.0) -> PaperFill:
    return PaperFill(
        symbol=symbol,
        side=side,
        quantity=0.0,
        price=price,
        notional=0.0,
        reason="no_fill: order queued, market closed",
        filled_at=datetime(2026, 7, 22, 20, 47, tzinfo=None),
        broker_order_id=order_id,
    )


class TestResolvePendingFills:
    def _ledger(self) -> PaperLedger:
        return PaperLedger(cash=100.0, starting_cash=100.0)

    def test_pending_orders_lists_only_id_bearing_unresolved_sentinels(self):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        # True rejection (no order id) — must be invisible to pending listing.
        idless = _pending_sentinel("BBB", "sell", None)
        ledger.fills.append(idless)
        # Already-resolved sentinel — must also be invisible.
        done = _pending_sentinel("CCC", "buy", "order-3")
        done.reason += "; resolved=cancelled"
        ledger.fills.append(done)
        # Real (non-zero-qty) fill — never pending.
        ledger.fills.append(
            PaperFill(
                symbol="DDD", side="buy", quantity=1.0, price=10.0, notional=10.0,
                reason="live fill", filled_at=datetime(2026, 7, 22), broker_order_id="order-4",
            )
        )
        listed = pending_orders(ledger)
        assert [e["broker_order_id"] for e in listed] == ["order-1"]

    def test_filled_buy_replaces_sentinel_with_real_position(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        executed = datetime(2026, 7, 23, 13, 30, tzinfo=UTC_TZ)
        report = resolve_pending_fills(
            universe,
            ledger,
            {
                "order-1": PendingOrderOutcome(
                    state="filled",
                    filled_quantity=0.05,
                    average_price=400.0,
                    notional=20.0,
                    executed_at=executed,
                )
            },
        )
        assert report.errors == []
        assert len(report.resolved) == 1
        assert "AAA" in ledger.positions
        pos = ledger.positions["AAA"]
        assert pos.quantity == 0.05
        assert pos.entry_price == 400.0
        assert pos.entry_date == executed
        assert ledger.cash == 80.0  # notional debited exactly
        # The stale sentinel is gone; the real fill remains.
        assert not [f for f in ledger.fills if f.quantity == 0]
        real = [f for f in ledger.fills if f.symbol == "AAA"][0]
        assert real.quantity == 0.05
        assert real.broker_order_id == "order-1"
        assert real.filled_at == executed
        # Strategy pinned, same as a live-recorded buy.
        assert pos.strategy_hash

    def test_filled_sell_closes_existing_position(self, universe):
        ledger = self._ledger()
        _open_position(ledger, "NOW", 0.18517, 101.15)
        ledger.fills.append(_pending_sentinel("NOW", "sell", "order-2", price=104.53))
        report = resolve_pending_fills(
            universe,
            ledger,
            {
                "order-2": PendingOrderOutcome(
                    state="filled", filled_quantity=0.18517, average_price=103.10
                )
            },
        )
        assert report.errors == []
        assert "NOW" not in ledger.positions  # fully closed
        assert ledger.cash == pytest.approx(100.0 + 0.18517 * 103.10)
        assert not [f for f in ledger.fills if f.quantity == 0]
        sell = [f for f in ledger.fills if f.side == "sell"][0]
        assert sell.broker_order_id == "order-2"

    def test_still_queued_left_untouched(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(
            universe, ledger, {"order-1": PendingOrderOutcome(state="queued")}
        )
        assert report.still_pending and not report.resolved and not report.errors
        assert len(pending_orders(ledger)) == 1  # still pending next time

    def test_dead_order_marks_sentinel_resolved(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(
            universe, ledger, {"order-1": PendingOrderOutcome(state="cancelled")}
        )
        assert report.expired and not report.errors
        assert pending_orders(ledger) == []  # no longer pending
        assert len(ledger.fills) == 1  # sentinel kept as the no-fill record
        assert "resolved=cancelled" in ledger.fills[0].reason

    def test_missing_outcome_is_an_error_not_silent(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(universe, ledger, {})
        assert report.errors and not report.resolved
        assert len(pending_orders(ledger)) == 1  # untouched

    def test_unknown_state_is_an_error_not_a_guess(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(
            universe, ledger, {"order-1": PendingOrderOutcome(state="mystery")}
        )
        assert report.errors
        assert len(pending_orders(ledger)) == 1

    def test_filled_buy_with_existing_position_errors(self, universe):
        ledger = self._ledger()
        _open_position(ledger, "AAA", 1.0, 100.0)
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(
            universe,
            ledger,
            {"order-1": PendingOrderOutcome(state="filled", filled_quantity=0.1, average_price=100.0)},
        )
        assert report.errors
        assert ledger.positions["AAA"].quantity == 1.0  # untouched

    def test_filled_sell_without_position_errors(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("NOW", "sell", "order-2"))
        report = resolve_pending_fills(
            universe,
            ledger,
            {"order-2": PendingOrderOutcome(state="filled", filled_quantity=0.1, average_price=100.0)},
        )
        assert report.errors
        assert len(pending_orders(ledger)) == 1  # untouched, still needs a human

    def test_notional_falls_back_to_qty_times_price(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(
            universe,
            ledger,
            {"order-1": PendingOrderOutcome(state="filled", filled_quantity=0.0344, average_price=399.01)},
        )
        assert report.errors == []
        assert ledger.cash == pytest.approx(100.0 - round(0.0344 * 399.01, 2))

    def test_filled_without_quantity_or_price_errors(self, universe):
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        report = resolve_pending_fills(
            universe, ledger, {"order-1": PendingOrderOutcome(state="filled")}
        )
        assert report.errors
        assert len(pending_orders(ledger)) == 1

    def test_notional_prefers_broker_amount_over_recompute(self, universe):
        """The broker's actual charged amount (fees/rounding) must win over
        qty*price when supplied — otherwise every resolved buy drifts cash by
        a few cents. Uses a notional deliberately != round(qty*price)."""
        ledger = self._ledger()
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        # qty*price = 0.05 * 400 = 20.00, but the broker charged 20.07 (fee/rounding).
        resolve_pending_fills(
            universe,
            ledger,
            {
                "order-1": PendingOrderOutcome(
                    state="filled", filled_quantity=0.05, average_price=400.0, notional=20.07
                )
            },
        )
        assert ledger.cash == pytest.approx(100.0 - 20.07)  # supplied notional, NOT 20.00

    def test_naive_executed_at_normalized_so_tracking_can_sort_fills(self, universe):
        """Regression (same class as CycleLock's naive-as_of fix): a naive
        executed_at from get_equity_orders must be coerced to UTC-aware before
        it lands on a fill, or a later sorted(fills, key=filled_at) — which
        `bonito live tracking` does — raises TypeError on mixed tz-awareness."""
        ledger = self._ledger()
        # A pre-existing aware fill, as every paper.py-produced fill is.
        ledger.fills.append(
            PaperFill(
                symbol="ZZZ", side="buy", quantity=1.0, price=10.0, notional=10.0,
                reason="live fill", filled_at=datetime(2026, 7, 22, tzinfo=UTC_TZ),
            )
        )
        ledger.fills.append(_pending_sentinel("AAA", "buy", "order-1"))
        # executed_at supplied WITHOUT a tz offset (the realistic hazard).
        outcome = PendingOrderOutcome.model_validate(
            {"state": "filled", "filled_quantity": 0.05, "average_price": 400.0,
             "executed_at": "2026-07-23T09:30:00"}
        )
        assert outcome.executed_at.tzinfo is not None  # coerced at validation
        resolve_pending_fills(universe, ledger, {"order-1": outcome})
        new_fill = [f for f in ledger.fills if f.symbol == "AAA"][0]
        assert new_fill.filled_at.tzinfo is not None
        assert ledger.positions["AAA"].entry_date.tzinfo is not None
        # The invariant that actually matters: fills remain mutually sortable.
        ordered = sorted(ledger.fills, key=lambda f: f.filled_at)
        assert len(ordered) == 2  # would have raised TypeError before the fix


class TestIntradaySweepWindow:
    """The DST-proof guard for the intraday Routine's UTC cron.

    Times are passed as UTC (naive or aware); the guard converts to ET. The
    critical cases are the two DST seasons: the SAME UTC instant maps to a
    different ET wall-clock, and the guard must key off ET, not UTC.
    """

    def _utc(self, y, mo, d, h, mi):
        return datetime(y, mo, d, h, mi, tzinfo=UTC_TZ)

    def test_edt_open_and_close_slots_are_in_window(self):
        # July = EDT (UTC-4). 13:30 UTC = 9:30 ET open; 19:30 UTC = 15:30 ET last slot.
        assert in_intraday_sweep_window(self._utc(2026, 7, 15, 13, 30)) is True
        assert in_intraday_sweep_window(self._utc(2026, 7, 15, 19, 30)) is True

    def test_edt_after_cutoff_slot_is_skipped(self):
        # 20:30 UTC = 16:30 ET in EDT — the extra superset slot, must be skipped.
        assert in_intraday_sweep_window(self._utc(2026, 7, 15, 20, 30)) is False

    def test_est_shifts_by_an_hour_but_window_holds(self):
        # January = EST (UTC-5). The SAME 13:30 UTC is now 8:30 ET — PRE-market, skip.
        assert in_intraday_sweep_window(self._utc(2026, 1, 15, 13, 30)) is False
        # 14:30 UTC = 9:30 ET open; 20:30 UTC = 15:30 ET last slot — both in.
        assert in_intraday_sweep_window(self._utc(2026, 1, 15, 14, 30)) is True
        assert in_intraday_sweep_window(self._utc(2026, 1, 15, 20, 30)) is True

    def test_stagger_slack_above_1530(self):
        # A 15:30 ET slot staggered to 15:40 ET still passes (<= 15:45 upper bound).
        assert in_intraday_sweep_window(self._utc(2026, 7, 15, 19, 40)) is True
        # ...but 15:50 ET does not (past the slack).
        assert in_intraday_sweep_window(self._utc(2026, 7, 15, 19, 50)) is False

    def test_weekend_is_out(self):
        # 2026-07-18 is a Saturday; a valid-looking ET time must still skip.
        assert in_intraday_sweep_window(self._utc(2026, 7, 18, 15, 30)) is False

    def test_naive_utc_input_accepted(self):
        assert in_intraday_sweep_window(datetime(2026, 7, 15, 13, 30)) is True


class TestCycleLock:
    def test_acquire_when_free_succeeds(self, universe, tmp_path):
        blocking = try_acquire_cycle_lock(universe, "daily", "run-1", directory=tmp_path)
        assert blocking is None
        lock = read_cycle_lock(universe, directory=tmp_path)
        assert lock is not None
        assert lock.holder == "daily"
        assert lock.run_id == "run-1"

    def test_acquire_when_held_and_fresh_is_blocked(self, universe, tmp_path):
        now = datetime(2026, 7, 21, 12, 0, 0)
        first = try_acquire_cycle_lock(universe, "daily", "run-1", as_of=now, directory=tmp_path)
        assert first is None

        blocking = try_acquire_cycle_lock(
            universe, "intraday", "run-2", as_of=now + timedelta(minutes=5), directory=tmp_path
        )
        assert blocking is not None
        assert blocking.holder == "daily"
        assert blocking.run_id == "run-1"
        # Blocked attempt must NOT overwrite the existing lock.
        still_there = read_cycle_lock(universe, directory=tmp_path)
        assert still_there.run_id == "run-1"

    def test_acquire_when_held_but_stale_reclaims(self, universe, tmp_path):
        now = datetime(2026, 7, 21, 12, 0, 0)
        try_acquire_cycle_lock(universe, "daily", "run-1", as_of=now, directory=tmp_path)

        reclaimer = try_acquire_cycle_lock(
            universe,
            "intraday",
            "run-2",
            as_of=now + timedelta(minutes=25),  # past the 20-minute stale threshold
            directory=tmp_path,
        )
        assert reclaimer is None  # acquired, not blocked
        lock = read_cycle_lock(universe, directory=tmp_path)
        assert lock.holder == "intraday"
        assert lock.run_id == "run-2"

    def test_release_with_matching_run_id_clears_lock(self, universe, tmp_path):
        try_acquire_cycle_lock(universe, "daily", "run-1", directory=tmp_path)
        cleared = release_cycle_lock(universe, "run-1", directory=tmp_path)
        assert cleared is True
        assert read_cycle_lock(universe, directory=tmp_path) is None

    def test_release_with_stale_run_id_is_a_safe_noop(self, universe, tmp_path):
        """The compare-and-delete guard: a preempted run's own release must
        never delete whoever's lock is actually current."""
        now = datetime(2026, 7, 21, 12, 0, 0)
        try_acquire_cycle_lock(universe, "daily", "run-1", as_of=now, directory=tmp_path)
        try_acquire_cycle_lock(
            universe, "intraday", "run-2", as_of=now + timedelta(minutes=25), directory=tmp_path
        )

        cleared = release_cycle_lock(universe, "run-1", directory=tmp_path)  # the preempted run
        assert cleared is False
        lock = read_cycle_lock(universe, directory=tmp_path)
        assert lock is not None
        assert lock.run_id == "run-2"  # untouched

    def test_release_when_nothing_held_is_a_noop(self, universe, tmp_path):
        assert release_cycle_lock(universe, "run-1", directory=tmp_path) is False

    def test_read_missing_lock_returns_none(self, universe, tmp_path):
        assert read_cycle_lock(universe, directory=tmp_path) is None

    def test_read_corrupt_lock_returns_none(self, universe, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / f"{universe.mode}_cycle_lock.json").write_text("{not valid json")
        assert read_cycle_lock(universe, directory=tmp_path) is None

    def test_naive_as_of_does_not_crash_against_a_tz_aware_stored_lock(self, universe, tmp_path):
        """Regression test: a naive as_of used to raise TypeError ('can't
        subtract offset-naive and offset-aware datetimes') when compared
        against a lock written via the default, tz-aware datetime.now(UTC)
        path -- the realistic case, since the CLI never passes as_of."""
        from datetime import UTC as _UTC

        first = try_acquire_cycle_lock(universe, "daily", "run-1", directory=tmp_path)  # aware
        assert first is None  # acquired

        naive_now = datetime.now(_UTC).replace(tzinfo=None)
        blocking = try_acquire_cycle_lock(
            universe, "intraday", "run-2", as_of=naive_now, directory=tmp_path
        )
        assert blocking is not None  # correctly still fresh, not a crash
        assert blocking.run_id == "run-1"

    def test_paper_and_live_use_separate_lock_files(self, tmp_path):
        paper = UniverseConfig(
            name="p",
            mode="paper",
            symbols=["AAA"],
            strategy_path="unused.json",
            data={"timeframe": "1d", "start_date": "2026-01-01"},
        )
        live = UniverseConfig(
            name="l",
            mode="live",
            symbols=["AAA"],
            strategy_path="unused.json",
            data={"timeframe": "1d", "start_date": "2026-01-01"},
        )
        try_acquire_cycle_lock(paper, "daily", "paper-run", directory=tmp_path)
        blocking = try_acquire_cycle_lock(live, "daily", "live-run", directory=tmp_path)
        assert blocking is None  # live's lock is independent of paper's
        assert read_cycle_lock(paper, directory=tmp_path).run_id == "paper-run"
        assert read_cycle_lock(live, directory=tmp_path).run_id == "live-run"


def _intent(symbol, side, dollar_amount=None, quantity=None) -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        side=side,
        dollar_amount=dollar_amount,
        quantity=quantity,
        reason="test",
        signal_price=100.0,
        signal_date=AS_OF,
        strategy_name="test",
    )


def _open_position(
    ledger: PaperLedger,
    symbol: str,
    quantity: float,
    entry_price: float,
    hwm: float | None = None,
) -> None:
    from bonito.trading.paper import PaperPosition

    ledger.positions[symbol] = PaperPosition(
        symbol=symbol,
        quantity=quantity,
        entry_price=entry_price,
        entry_date=AS_OF,
        high_water_mark=hwm if hwm is not None else entry_price,
    )


class TestReconcile:
    def _ledger_with(self, symbol="AAA", qty=0.5):
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        _open_position(ledger, symbol, quantity=qty, entry_price=100.0)
        return ledger

    def test_in_sync(self):
        from bonito.trading.live_runner import reconcile_positions

        report = reconcile_positions(self._ledger_with(), {"AAA": 0.5})
        assert report.in_sync is True
        assert "in sync" in report.describe()

    def test_flat_account_matches_empty_ledger(self):
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        assert reconcile_positions(ledger, {}).in_sync is True

    def test_broker_position_unknown_to_ledger_is_critical(self):
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        report = reconcile_positions(ledger, {"NVDA": 0.2})
        assert report.in_sync is False
        assert report.missing_in_ledger == {"NVDA": 0.2}
        assert "CRITICAL" in report.describe()

    def test_ledger_position_missing_at_broker(self):
        from bonito.trading.live_runner import reconcile_positions

        report = reconcile_positions(self._ledger_with("AAA"), {})
        assert report.in_sync is False
        assert report.missing_at_broker == ["AAA"]

    def test_quantity_mismatch(self):
        from bonito.trading.live_runner import reconcile_positions

        report = reconcile_positions(self._ledger_with("AAA", qty=0.5), {"AAA": 0.7})
        assert report.in_sync is False
        assert report.quantity_mismatch["AAA"] == {"ledger": 0.5, "broker": 0.7}

    def test_tolerance_absorbs_float_noise(self):
        from bonito.trading.live_runner import reconcile_positions

        report = reconcile_positions(self._ledger_with("AAA", qty=0.5), {"AAA": 0.500009})
        assert report.in_sync is True

    def test_dust_at_broker_ignored(self):
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        report = reconcile_positions(ledger, {"AAA": 0.00000001})
        assert report.in_sync is True

    def test_broker_extra_with_pending_buy_sentinel_is_not_fatal(self):
        """The intraday-coverage fix: a broker position the ledger doesn't hold,
        but with a matching unresolved pending-BUY sentinel, is an expected
        overnight fill — NOT fatal drift. So the intraday sweep can proceed
        instead of aborting all day after a daily-cycle buy."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.fills.append(_pending_sentinel("DELL", "buy", "order-dell"))
        report = reconcile_positions(ledger, {"DELL": 0.0416})
        assert report.fatal_drift is False  # would-be fatal, but pending-explained
        assert report.pending_explained == ["DELL"]
        assert report.missing_in_ledger == {"DELL": 0.0416}  # still surfaced
        assert report.in_sync is False  # there IS a (benign) discrepancy
        assert "pending fill" in report.describe()

    def test_broker_extra_without_a_sentinel_is_still_fatal(self):
        """The crash case this gate exists for: broker holds a position the
        ledger has NO record of (no pending sentinel) — genuinely unrecorded,
        must still hard-fail."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        report = reconcile_positions(ledger, {"DELL": 0.0416})  # no sentinel
        assert report.fatal_drift is True
        assert report.pending_explained == []

    def test_a_pending_sell_sentinel_does_not_explain_a_broker_extra(self):
        """Only a pending BUY explains a broker position the ledger lacks. A
        pending SELL sentinel for a symbol the broker still holds is unrelated
        and must NOT suppress the fatal check."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.fills.append(_pending_sentinel("DELL", "sell", "order-dell"))
        report = reconcile_positions(ledger, {"DELL": 0.0416})
        assert report.fatal_drift is True
        assert report.pending_explained == []

    def test_ledger_position_missing_at_broker_with_pending_sell_is_not_fatal(self):
        """Symmetric to the buy case: a ledger position the broker no longer
        holds, but with a matching unresolved pending-SELL sentinel, is an
        expected overnight sell fill (daily cycle queued it, it filled at open)
        — NOT drift. So the intraday sweep proceeds instead of aborting after a
        daily-cycle sell."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = self._ledger_with("ASML", qty=0.0108)  # open position
        ledger.fills.append(_pending_sentinel("ASML", "sell", "order-asml"))
        report = reconcile_positions(ledger, {})  # broker no longer holds it
        assert report.fatal_drift is False
        assert report.pending_explained == ["ASML"]
        assert report.missing_at_broker == ["ASML"]  # still surfaced
        assert "pending sell fill" in report.describe()

    def test_ledger_position_missing_at_broker_without_a_sentinel_is_still_fatal(self):
        """A ledger position the broker doesn't hold, with NO pending sell
        sentinel, is genuine drift (a vanished/unrecorded position) — fatal."""
        from bonito.trading.live_runner import reconcile_positions

        report = reconcile_positions(self._ledger_with("ASML", qty=0.0108), {})
        assert report.fatal_drift is True
        assert report.pending_explained == []

    def test_a_pending_buy_sentinel_does_not_explain_a_missing_at_broker(self):
        """Direction matters: a ledger position gone from the broker is only
        explained by a pending SELL, never a pending BUY."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = self._ledger_with("ASML", qty=0.0108)
        ledger.fills.append(_pending_sentinel("ASML", "buy", "order-asml"))
        report = reconcile_positions(ledger, {})
        assert report.fatal_drift is True
        assert report.pending_explained == []

    def test_mixed_pending_and_genuine_drift_still_fatal(self):
        """One pending-explained broker-extra + one genuine unexplained one:
        the genuine one keeps it fatal; the pending one is still classified."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.fills.append(_pending_sentinel("DELL", "buy", "order-dell"))
        report = reconcile_positions(ledger, {"DELL": 0.0416, "GHOST": 0.5})
        assert report.fatal_drift is True  # GHOST has no sentinel
        assert report.pending_explained == ["DELL"]
        assert any("GHOST" in r for r in report.fatal_reasons)
        assert not any("DELL" in r for r in report.fatal_reasons)

    def test_resolved_pending_sentinel_no_longer_explains(self):
        """Once a sentinel is marked resolved, it no longer suppresses drift
        (it's been dealt with) — the broker-extra becomes genuine drift again."""
        from bonito.trading.live_runner import reconcile_positions

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        s = _pending_sentinel("DELL", "buy", "order-dell")
        s.reason += "; resolved=cancelled"
        ledger.fills.append(s)
        report = reconcile_positions(ledger, {"DELL": 0.0416})
        assert report.fatal_drift is True
        assert report.pending_explained == []


NEVER_ENTER_STRATEGY = {
    **ALWAYS_ENTER_STRATEGY,
    "name": "never_enter",
    "entry_rules": [
        {
            "conditions": [{"left": "close", "comparison": "lt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
}


class TestKillSwitch:
    def test_drawdown_breach_flattens_and_halts(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0, peak_equity=200.0)
        # Position worth 0.5 * 129 = 64.50 → 68% drawdown from the 200 peak.
        # Entry near price with hwm at price so neither stop nor TP fires —
        # the only exit must come from the kill switch.
        _open_position(ledger, "AAA", quantity=0.5, entry_price=128.0, hwm=129.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)

        assert ledger.halted
        assert "drawdown" in ledger.halt_reason
        sells = [i for i in intents if i.side == "sell"]
        assert len(sells) == 1
        assert sells[0].symbol == "AAA"
        assert "kill switch" in sells[0].reason
        assert [i for i in intents if i.side == "buy"] == []

    def test_halted_ledger_generates_no_entries(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.halt("manual")

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert intents == []

    def test_halted_ledger_still_evaluates_exits(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.halt("manual")
        _open_position(ledger, "AAA", quantity=0.5, entry_price=200.0)  # deep stop breach

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        sells = [i for i in intents if i.side == "sell"]
        assert len(sells) == 1
        assert "stop loss" in sells[0].reason

    def test_disabled_kill_switch_never_halts(self, universe):
        universe.risk.max_drawdown_halt = None
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0, peak_equity=10_000.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=128.0, hwm=129.0)

        generate_intents(universe, store, ledger, as_of=AS_OF)
        assert not ledger.halted

    def test_no_halt_within_threshold(self, universe):
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0, peak_equity=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert not ledger.halted
        assert len([i for i in intents if i.side == "buy"]) == 3


class TestPerSymbolStrategies:
    def test_symbol_override_controls_entries(self, universe, tmp_path):
        never_path = tmp_path / "never.json"
        never_path.write_text(json.dumps(NEVER_ENTER_STRATEGY))
        universe.symbol_strategies = {"AAA": str(never_path)}
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        buys = {i.symbol for i in intents if i.side == "buy"}
        assert "AAA" not in buys
        assert buys == {"BBB", "CCC", "DDD"}

    def test_pinned_strategy_governs_exit(self, universe):
        # Position pinned to a 1%-TP strategy; the universe's current
        # strategy has a 10% TP. Price is +0.8% over entry → only the
        # pinned config exits.
        from bonito.backtest.strategy import StrategyConfig

        pinned = StrategyConfig(
            **{
                **NEVER_ENTER_STRATEGY,
                "name": "tight_tp",
                "take_profit": {"type": "percent", "value": 0.001},
                "stop_loss": None,
            }
        )
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.3, entry_price=128.0, hwm=129.0)
        ledger.positions["AAA"].strategy_config = pinned.model_dump(mode="json")

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        sells = [i for i in intents if i.side == "sell"]
        assert len(sells) == 1
        assert sells[0].strategy_name == "tight_tp"
        assert "take profit" in sells[0].reason

    def test_execute_paper_pins_strategy(self, universe):
        from bonito.trading.live_runner import execute_paper

        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        intents, prices = generate_intents(universe, store, ledger, as_of=AS_OF)
        strategies = {
            i.symbol: universe.load_strategy_for(i.symbol) for i in intents if i.side == "buy"
        }

        fills, errors = execute_paper(ledger, intents, prices, strategies=strategies)
        assert errors == []
        for symbol in {i.symbol for i in intents if i.side == "buy"}:
            assert ledger.positions[symbol].pinned_strategy() is not None
            assert ledger.positions[symbol].strategy_hash != ""


class TestRegimeGate:
    def regime_universe(self, universe, tmp_path, spy_closes: list[float]) -> FakeStore:
        strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 5},
        }
        path = tmp_path / "gated.json"
        path.write_text(json.dumps(strategy))
        universe.strategy_path = str(path)
        universe._strategy_cache.clear()

        closes = [100.0 + i for i in range(30)]
        bars = {s: make_bars(s, closes) for s in universe.symbols}
        bars["SPY"] = make_bars("SPY", spy_closes)
        return FakeStore(bars)

    def test_risk_on_allows_entries(self, universe, tmp_path):
        store = self.regime_universe(universe, tmp_path, [100.0 + i for i in range(30)])
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert len([i for i in intents if i.side == "buy"]) == 3

    def test_risk_off_blocks_entries(self, universe, tmp_path):
        store = self.regime_universe(universe, tmp_path, [130.0 - i for i in range(30)])
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert [i for i in intents if i.side == "buy"] == []

    def test_missing_regime_data_blocks_entries(self, universe, tmp_path):
        store = self.regime_universe(universe, tmp_path, [100.0 + i for i in range(30)])
        del store.bars["SPY"]
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert [i for i in intents if i.side == "buy"] == []

    def test_risk_off_never_blocks_exits(self, universe, tmp_path):
        store = self.regime_universe(universe, tmp_path, [130.0 - i for i in range(30)])
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=200.0)  # stop breach

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert len([i for i in intents if i.side == "sell"]) == 1

    def test_refresh_includes_regime_symbol(self, universe, tmp_path):
        strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 200},
        }
        path = tmp_path / "gated.json"
        path.write_text(json.dumps(strategy))
        universe.strategy_path = str(path)
        universe._strategy_cache.clear()

        assert universe.regime_symbols() == {"SPY"}


class TestEntryAllowlist:
    def test_only_allowlisted_symbols_get_entries(self, universe):
        universe.entry_allowlist = ["BBB", "ddd"]  # case-insensitive
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)

        assert {i.symbol for i in intents if i.side == "buy"} == {"BBB", "DDD"}

    def test_none_allowlist_means_all_symbols(self, universe):
        assert universe.entry_allowlist is None
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)
        assert len([i for i in intents if i.side == "buy"]) == 3  # max_daily_buys

    def test_exits_never_gated_by_allowlist(self, universe):
        universe.entry_allowlist = []  # nothing may enter
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=200.0)  # stop breach

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)

        assert [i.symbol for i in intents if i.side == "sell"] == ["AAA"]
        assert not [i for i in intents if i.side == "buy"]


class TestEntryBlocklist:
    def test_benched_symbols_skip_entries(self, universe):
        universe.entry_blocklist = ["aaa", "BBB"]  # case-insensitive
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)

        bought = {i.symbol for i in intents if i.side == "buy"}
        assert "AAA" not in bought and "BBB" not in bought
        assert bought  # the rest of the universe still enters

    def test_exits_never_gated_by_blocklist(self, universe):
        universe.entry_blocklist = ["AAA"]
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=200.0)  # stop breach

        intents, _ = generate_intents(universe, store, ledger, as_of=AS_OF)

        assert [i.symbol for i in intents if i.side == "sell"] == ["AAA"]


class TestComputePositionAtrs:
    def test_atr_computed_for_atr_stop_positions_only(self, universe, tmp_path):
        from bonito.trading.live_runner import compute_position_atrs
        from bonito.trading.signals import latest_atr

        atr_strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "atr_stop",
            "stop_loss": {"type": "trailing_atr", "value": 2.0, "atr_period": 14},
        }
        path = tmp_path / "atr_stop.json"
        path.write_text(json.dumps(atr_strategy))
        universe.symbol_strategies = {"AAA": str(path)}

        store = uptrend_store(["AAA", "BBB"])
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)  # ATR stop
        _open_position(ledger, "BBB", quantity=1.0, entry_price=100.0)  # percent stop

        atrs = compute_position_atrs(universe, ledger, store, as_of=AS_OF)

        assert set(atrs) == {"AAA"}
        assert atrs["AAA"] == pytest.approx(latest_atr(store.bars["AAA"], 14))

    def test_missing_bars_omit_symbol(self, universe, tmp_path):
        from bonito.trading.live_runner import compute_position_atrs

        atr_strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "atr_stop",
            "stop_loss": {"type": "trailing_atr", "value": 2.0, "atr_period": 14},
        }
        path = tmp_path / "atr_stop.json"
        path.write_text(json.dumps(atr_strategy))
        universe.symbol_strategies = {"AAA": str(path)}

        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)

        assert compute_position_atrs(universe, ledger, FakeStore({}), as_of=AS_OF) == {}


class TestComputeStopLevels:
    def test_trailing_percent_and_take_profit(self, universe):
        from bonito.trading.live_runner import compute_stop_levels

        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=110.0)

        levels = compute_stop_levels(universe, ledger, FakeStore({}), as_of=AS_OF)

        assert levels["AAA"]["quantity"] == 0.5
        assert levels["AAA"]["stop_type"] == "trailing_percent"
        assert levels["AAA"]["stop_price"] == pytest.approx(110.0 * 0.95)
        assert levels["AAA"]["take_profit_price"] == pytest.approx(110.0)

    def test_ratchets_with_high_water_mark(self, universe):
        """Same position, higher hwm -> a higher (tighter) stop -- proves the
        level isn't just derived from entry_price, so the Routine actually
        needs to replace the broker order each cycle, not set-and-forget."""
        from bonito.trading.live_runner import compute_stop_levels

        low_hwm_ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(low_hwm_ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=100.0)
        high_hwm_ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(high_hwm_ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=120.0)

        low = compute_stop_levels(universe, low_hwm_ledger, FakeStore({}), as_of=AS_OF)
        high = compute_stop_levels(universe, high_hwm_ledger, FakeStore({}), as_of=AS_OF)

        assert high["AAA"]["stop_price"] > low["AAA"]["stop_price"]

    def test_atr_stop_omitted_without_bars(self, universe, tmp_path):
        """Mirrors compute_position_atrs: no bars -> can't compute a level,
        so the symbol is omitted rather than guessing a stop price."""
        from bonito.trading.live_runner import compute_stop_levels

        atr_strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "atr_stop",
            "stop_loss": {"type": "trailing_atr", "value": 2.0, "atr_period": 14},
            "take_profit": None,
        }
        path = tmp_path / "atr_stop.json"
        path.write_text(json.dumps(atr_strategy))
        universe.symbol_strategies = {"AAA": str(path)}

        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)

        assert compute_stop_levels(universe, ledger, FakeStore({}), as_of=AS_OF) == {}

    def test_atr_stop_omitted_without_bars_even_with_take_profit_configured(
        self, universe, tmp_path
    ):
        """Regression: deployed_strategy.json (and most live symbols) pair a
        trailing_atr stop with a percent take_profit -- the exact combination
        that must NOT fall through to a "stop_price: null" entry when bars
        are missing. A caller acting on stop_price alone for every listed
        symbol would otherwise cancel a good existing broker stop and then
        fail to replace it, during the very data-outage this guard exists
        for."""
        from bonito.trading.live_runner import compute_stop_levels

        atr_and_tp_strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "atr_stop_with_tp",
            "stop_loss": {"type": "trailing_atr", "value": 2.0, "atr_period": 14},
            "take_profit": {"type": "percent", "value": 0.10},
        }
        path = tmp_path / "atr_stop_with_tp.json"
        path.write_text(json.dumps(atr_and_tp_strategy))
        universe.symbol_strategies = {"AAA": str(path)}

        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)

        assert compute_stop_levels(universe, ledger, FakeStore({}), as_of=AS_OF) == {}

    def test_no_stop_or_take_profit_configured_is_omitted(self, universe, tmp_path):
        from bonito.trading.live_runner import compute_stop_levels

        no_exit_strategy = {**ALWAYS_ENTER_STRATEGY, "stop_loss": None, "take_profit": None}
        path = tmp_path / "no_exit.json"
        path.write_text(json.dumps(no_exit_strategy))
        universe.symbol_strategies = {"AAA": str(path)}

        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)

        assert compute_stop_levels(universe, ledger, FakeStore({}), as_of=AS_OF) == {}


class TestRefreshSubset:
    class RecordingStore(FakeStore):
        def __init__(self):
            super().__init__({})
            self.ingested: list[str] = []

        def ingest_from_yahoo(self, symbol, start, end, timeframe="1d"):
            self.ingested.append(symbol)
            return 1

    def test_symbols_subset_skips_rest_and_regime(self, universe, tmp_path):
        from bonito.trading.live_runner import refresh_data

        strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 200},
        }
        path = tmp_path / "gated.json"
        path.write_text(json.dumps(strategy))
        universe.strategy_path = str(path)
        universe._strategy_cache.clear()

        store = self.RecordingStore()
        refresh_data(universe, store, symbols=["AAA", "CCC"])
        assert store.ingested == ["AAA", "CCC"]

    def test_full_refresh_still_includes_regime(self, universe, tmp_path):
        from bonito.trading.live_runner import refresh_data

        strategy = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 200},
        }
        path = tmp_path / "gated.json"
        path.write_text(json.dumps(strategy))
        universe.strategy_path = str(path)
        universe._strategy_cache.clear()

        store = self.RecordingStore()
        refresh_data(universe, store)
        assert store.ingested == [*universe.symbols, "SPY"]


class TestPreflight:
    """The fail-closed gate for unattended cycles."""

    def fresh_store(self, symbols, regime=None):
        bars = {s: make_bars(s, [100.0 + i for i in range(30)]) for s in symbols}
        if regime:
            bars[regime] = make_bars(regime, [100.0 + i for i in range(250)])
        return FakeStore(bars)

    def test_clean_state_passes(self, universe):
        store = self.fresh_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        report = preflight(universe, ledger, store, as_of=AS_OF)

        assert report.ok
        assert report.reasons == []
        assert set(report.fresh_symbols) == set(universe.symbols)

    def test_latched_kill_switch_aborts(self, universe):
        store = self.fresh_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.halt("drawdown 25% >= 25% cap")

        report = preflight(universe, ledger, store, as_of=AS_OF)

        assert not report.ok
        assert any("kill switch" in r for r in report.reasons)

    def test_live_flag_inconsistency_aborts(self, universe):
        universe.mode = "live"
        universe.live_enabled = False
        store = self.fresh_store(universe.symbols)
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        report = preflight(universe, ledger, store, as_of=AS_OF)

        assert not report.ok
        assert any("live_enabled is false" in r for r in report.reasons)

    def test_total_data_outage_aborts(self, universe):
        stale = datetime(2026, 5, 1)  # >5 days before AS_OF
        store = FakeStore({s: make_bars(s, [100.0, 101.0], end=stale) for s in universe.symbols})
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        report = preflight(universe, ledger, store, as_of=AS_OF)

        assert not report.ok
        assert any("no fresh market data" in r for r in report.reasons)
        assert set(report.stale_symbols) == set(universe.symbols)

    def test_partial_staleness_is_a_warning_not_abort(self, universe):
        stale = datetime(2026, 5, 1)
        fresh = [100.0 + i for i in range(30)]
        bars = {s: make_bars(s, fresh) for s in universe.symbols[:2]}
        bars.update({s: make_bars(s, [100.0, 101.0], end=stale) for s in universe.symbols[2:]})
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        report = preflight(universe, ledger, FakeStore(bars), as_of=AS_OF)

        assert report.ok  # some fresh data → proceed (exits/stops still run)
        assert any("stale" in w for w in report.warnings)

    def test_stale_regime_warns_but_proceeds(self, universe, tmp_path):
        gated = {
            **ALWAYS_ENTER_STRATEGY,
            "name": "gated",
            "regime_filter": {"symbol": "SPY", "sma_period": 200},
        }
        path = tmp_path / "gated.json"
        path.write_text(json.dumps(gated))
        universe.strategy_path = str(path)
        universe._strategy_cache.clear()

        bars = {s: make_bars(s, [100.0 + i for i in range(30)]) for s in universe.symbols}
        bars["SPY"] = make_bars("SPY", [100.0, 101.0], end=datetime(2026, 5, 1))  # stale
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        report = preflight(universe, ledger, FakeStore(bars), as_of=AS_OF)

        assert report.ok  # exits must still process despite a risk-off regime
        assert report.stale_regime == ["SPY"]
        assert any("risk-off" in w for w in report.warnings)

    def test_exits_only_skips_data_outage_but_keeps_kill_switch(self, universe):
        """The intraday-Routine mode: an empty store must NOT abort (it acts on
        live quotes, not stored bars), but the kill switch and flag checks
        still gate."""
        universe.mode = "live"
        universe.live_enabled = True
        empty_store = FakeStore({})  # fresh ephemeral container: no data at all
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)

        # Without exits_only this would abort on total data outage...
        assert not preflight(universe, ledger, empty_store, as_of=AS_OF).ok
        # ...with exits_only it passes (data checks skipped entirely).
        report = preflight(universe, ledger, empty_store, as_of=AS_OF, exits_only=True)
        assert report.ok
        assert report.reasons == []
        assert report.missing_symbols == []  # data checks not even run

        # But a latched kill switch STILL aborts under exits_only.
        ledger.halt("drawdown 25% >= 25% cap")
        halted = preflight(universe, ledger, empty_store, as_of=AS_OF, exits_only=True)
        assert not halted.ok
        assert any("kill switch" in r for r in halted.reasons)

    def test_exits_only_keeps_live_flag_check(self, universe):
        universe.mode = "live"
        universe.live_enabled = False  # misconfigured
        report = preflight(universe, PaperLedger(cash=150.0, starting_cash=150.0),
                           FakeStore({}), as_of=AS_OF, exits_only=True)
        assert not report.ok
        assert any("live_enabled is false" in r for r in report.reasons)
