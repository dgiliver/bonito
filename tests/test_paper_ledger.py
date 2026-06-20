"""Tests for the paper trading ledger (bonito.trading.paper)."""

from datetime import UTC, datetime

import pytest

from bonito.trading.paper import PaperLedger
from bonito.trading.signals import TradeIntent


def buy_intent(symbol: str = "TSLA", dollars: float = 30.0) -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        side="buy",
        dollar_amount=dollars,
        reason="test entry",
        signal_price=100.0,
        signal_date=datetime.now(UTC),
        strategy_name="test",
    )


def sell_intent(symbol: str = "TSLA") -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        side="sell",
        reason="test exit",
        signal_price=100.0,
        signal_date=datetime.now(UTC),
        strategy_name="test",
    )


class TestBuy:
    def test_buy_opens_position_and_debits_cash(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        fill = ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)

        assert ledger.cash == pytest.approx(120.0)
        assert "TSLA" in ledger.positions
        pos = ledger.positions["TSLA"]
        assert pos.quantity == pytest.approx(0.3)
        assert pos.entry_price == 100.0
        assert pos.high_water_mark == 100.0
        assert fill.notional == 30.0

    def test_buy_rejects_insufficient_cash(self):
        ledger = PaperLedger(cash=10.0, starting_cash=150.0)
        with pytest.raises(ValueError, match="insufficient cash"):
            ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)

    def test_buy_rejects_duplicate_position(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        with pytest.raises(ValueError, match="already open"):
            ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)

    def test_buy_rejects_zero_price(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        with pytest.raises(ValueError, match="invalid fill price"):
            ledger.apply_buy(buy_intent(dollars=30.0), fill_price=0.0)

    def test_buy_rejects_missing_dollar_amount(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        intent = buy_intent()
        intent = intent.model_copy(update={"dollar_amount": None})
        with pytest.raises(ValueError, match="dollar_amount"):
            ledger.apply_buy(intent, fill_price=100.0)


class TestSell:
    def test_sell_closes_position_with_profit(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        fill = ledger.apply_sell(sell_intent(), fill_price=110.0)

        assert "TSLA" not in ledger.positions
        # 0.3 shares * 110 = 33 back
        assert ledger.cash == pytest.approx(153.0)
        assert ledger.realized_pnl == pytest.approx(3.0)
        assert fill.quantity == pytest.approx(0.3)

    def test_sell_records_loss(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        ledger.apply_sell(sell_intent(), fill_price=90.0)

        assert ledger.cash == pytest.approx(147.0)
        assert ledger.realized_pnl == pytest.approx(-3.0)

    def test_sell_rejects_unknown_position(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        with pytest.raises(ValueError, match="no open position"):
            ledger.apply_sell(sell_intent("NVDA"), fill_price=100.0)


class TestEquityAndSummary:
    def test_equity_marks_to_market(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        assert ledger.equity({"TSLA": 120.0}) == pytest.approx(120.0 + 0.3 * 120.0)

    def test_equity_falls_back_to_entry_price(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        assert ledger.equity({}) == pytest.approx(150.0)

    def test_summary_round_trip(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        s = ledger.summary({"TSLA": 110.0})
        assert s["cash"] == 120.0
        assert s["equity"] == pytest.approx(153.0)
        assert s["unrealized_pnl"] == pytest.approx(3.0)
        assert s["open_positions"][0]["symbol"] == "TSLA"


class TestHighWaterMark:
    def test_hwm_only_moves_up(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        ledger.update_high_water_mark("TSLA", 120.0)
        assert ledger.positions["TSLA"].high_water_mark == 120.0
        ledger.update_high_water_mark("TSLA", 110.0)
        assert ledger.positions["TSLA"].high_water_mark == 120.0

    def test_hwm_ignores_unknown_symbol(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.update_high_water_mark("NVDA", 120.0)  # no-op, no exception


class TestPersistence:
    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "ledger.json"
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        ledger.save(path)

        loaded = PaperLedger.load(path)
        assert loaded.cash == pytest.approx(120.0)
        assert loaded.positions["TSLA"].quantity == pytest.approx(0.3)
        assert len(loaded.fills) == 1
        assert loaded.updated_at is not None

    def test_load_or_create_fresh(self, tmp_path):
        path = tmp_path / "missing.json"
        ledger = PaperLedger.load_or_create(path, starting_cash=150.0)
        assert ledger.cash == 150.0
        assert ledger.positions == {}

    def test_load_or_create_existing(self, tmp_path):
        path = tmp_path / "ledger.json"
        ledger = PaperLedger(cash=99.0, starting_cash=150.0)
        ledger.save(path)
        loaded = PaperLedger.load_or_create(path, starting_cash=150.0)
        assert loaded.cash == 99.0


class TestAuditTrail:
    def test_position_and_fill_tagged_with_strategy(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        intent = buy_intent().model_copy(update={"strategy_name": "ema_cross"})
        ledger.apply_buy(intent, fill_price=100.0)

        assert ledger.positions["TSLA"].strategy_name == "ema_cross"
        assert ledger.fills[0].strategy_name == "ema_cross"

    def test_sell_inherits_strategy_from_position(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(
            buy_intent().model_copy(update={"strategy_name": "ema_cross"}), fill_price=100.0
        )
        intent = sell_intent().model_copy(update={"strategy_name": ""})
        ledger.apply_sell(intent, fill_price=110.0)

        assert ledger.fills[-1].strategy_name == "ema_cross"

    def test_fills_history_is_append_only_across_round_trips(self, tmp_path):
        path = tmp_path / "ledger.json"
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        ledger.apply_sell(sell_intent(), fill_price=110.0)
        ledger.save(path)

        loaded = PaperLedger.load(path)
        loaded.apply_buy(buy_intent("NVDA", dollars=30.0), fill_price=200.0)
        loaded.save()  # saves back to the same path it was loaded from

        final = PaperLedger.load(path)
        assert len(final.fills) == 3  # nothing pruned

    def test_save_remembers_load_path(self, tmp_path):
        path = tmp_path / "live_ledger.json"
        ledger = PaperLedger.load_or_create(path, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        ledger.save()  # no explicit path
        assert path.exists()
        assert PaperLedger.load(path).cash == pytest.approx(120.0)

    def test_ledger_path_for_mode(self):
        from bonito.trading.paper import ledger_path_for_mode

        assert str(ledger_path_for_mode("paper")).endswith("paper_ledger.json")
        assert str(ledger_path_for_mode("live")).endswith("live_ledger.json")


class TestStrategyPinning:
    def make_strategy(self):
        from bonito.backtest.strategy import StrategyConfig

        return StrategyConfig(
            name="pinned",
            symbols=["TSLA"],
            entry_rules=[
                {
                    "conditions": [{"left": "close", "comparison": "gt", "right": 1.0}],
                    "logic": "AND",
                    "side": "long",
                }
            ],
            take_profit={"type": "percent", "value": 0.01},
        )

    def test_buy_pins_strategy_to_position(self):
        from bonito.trading.validation import strategy_hash

        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        strategy = self.make_strategy()
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0, strategy=strategy)

        pos = ledger.positions["TSLA"]
        assert pos.strategy_hash == strategy_hash(strategy)
        pinned = pos.pinned_strategy()
        assert pinned is not None
        assert pinned.take_profit.value == 0.01

    def test_buy_without_strategy_leaves_no_pin(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        assert ledger.positions["TSLA"].pinned_strategy() is None

    def test_pin_survives_save_load(self, tmp_path):
        path = tmp_path / "ledger.json"
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0, strategy=self.make_strategy())
        ledger.save(path)

        loaded = PaperLedger.load(path)
        pinned = loaded.positions["TSLA"].pinned_strategy()
        assert pinned is not None
        assert pinned.name == "pinned"


class TestKillSwitchState:
    def test_note_equity_tracks_peak_and_drawdown(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        assert ledger.note_equity(150.0) == pytest.approx(0.0)
        assert ledger.note_equity(200.0) == pytest.approx(0.0)
        assert ledger.peak_equity == 200.0
        assert ledger.note_equity(150.0) == pytest.approx(0.25)
        assert ledger.peak_equity == 200.0  # peak never falls

    def test_halted_ledger_rejects_buys_allows_sells(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(buy_intent(dollars=30.0), fill_price=100.0)
        ledger.halt("test halt")

        with pytest.raises(ValueError, match="halted"):
            ledger.apply_buy(buy_intent(symbol="NVDA"), fill_price=50.0)
        ledger.apply_sell(sell_intent(), fill_price=110.0)  # exits always allowed
        assert "TSLA" not in ledger.positions

    def test_resume_clears_halt(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.halt("test")
        assert ledger.halted
        ledger.resume(confirm=True)
        assert not ledger.halted
        assert ledger.halt_reason == ""

    def test_resume_without_confirm_raises(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.halt("test")
        with pytest.raises(ValueError, match="confirm=True"):
            ledger.resume()
        assert ledger.halted  # halt state untouched by the rejected call

    def test_halt_state_survives_save_load(self, tmp_path):
        path = tmp_path / "ledger.json"
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.note_equity(180.0)
        ledger.halt("drawdown breach")
        ledger.save(path)

        loaded = PaperLedger.load(path)
        assert loaded.halted
        assert loaded.halt_reason == "drawdown breach"
        assert loaded.peak_equity == 180.0

    def test_summary_reports_halt(self):
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.halt("why")
        s = ledger.summary()
        assert s["halted"] is True
        assert s["halt_reason"] == "why"
