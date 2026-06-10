"""Tests for the daily live runner (bonito.trading.live_runner)."""

import json
from datetime import datetime, timedelta

import pytest

from bonito.data.models import BarData
from bonito.trading.live_runner import (
    UniverseConfig,
    check_stops,
    execute_paper,
    generate_intents,
    save_intents,
)
from bonito.trading.paper import PaperLedger
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
