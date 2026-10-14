"""Core-holding mode: a buy-and-hold position (e.g. QQQ) the strategy never exits.

User decision 2026-10-14: the live bot holds QQQ as its core while research continues.
The strategy's stops / take-profit / signal exits were the #1 source of live losses,
so the core must be immune to all of them; it is topped up from cash toward
`target_pct` of equity; the kill switch still applies.
"""

import json
from datetime import datetime, timedelta

import pytest

from bonito.data.models import BarData
from bonito.trading.live_runner import (
    CoreHolding,
    PendingOrderOutcome,
    UniverseConfig,
    check_stops,
    compute_stop_levels,
    execute_paper,
    generate_intents,
    resolve_pending_fills,
)
from bonito.trading.paper import PaperFill, PaperLedger, PaperPosition
from bonito.trading.signals import TradeIntent

LAST_BAR = datetime(2026, 6, 5)
AS_OF = datetime(2026, 6, 8)

# Exits on EVERY bar (close > 0) with a tight trailing stop and a tiny take-profit:
# anything the strategy manages would be sold — the core must not be.
EXIT_HAPPY = {
    "name": "exit_happy",
    "symbols": ["X"],
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
            "conditions": [{"left": "close", "comparison": "gt", "right": 0.0}],
            "logic": "AND",
            "side": "long",
        }
    ],
    "position_size": {"type": "percent_equity", "value": 10},
    "stop_loss": {"type": "trailing_percent", "value": 0.01},
    "take_profit": {"type": "percent", "value": 0.01},
}


def bars(symbol: str, closes: list[float], end: datetime = LAST_BAR) -> BarData:
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
        volumes=[1e6] * n,
    )


class FakeStore:
    def __init__(self, data):
        self.data = data

    def get_bars(self, symbol, start, end, timeframe="1d"):
        return self.data.get(symbol)


def universe(tmp_path, *, core: dict | None = None, **over) -> UniverseConfig:
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(EXIT_HAPPY))
    cfg = {
        "name": "t",
        "symbols": ["AAA"],
        "strategy_path": str(sp),
        "mode": "paper",
        "data": {"timeframe": "1d", "start_date": "2026-01-01"},
        "risk": {
            "starting_cash_usd": 150.0,
            "max_position_usd": 30.0,
            "max_positions": 5,
            "max_daily_buys": 3,
            "min_cash_buffer_usd": 5.0,
        },
        "core_holding": core if core is not None else {"symbol": "qqq"},
    }
    cfg.update(over)
    return UniverseConfig(**cfg)


def store(qqq=100.0, aaa=50.0) -> FakeStore:
    return FakeStore({"QQQ": bars("QQQ", [qqq] * 30), "AAA": bars("AAA", [aaa] * 30)})


def core_position(qty=1.0, entry=100.0) -> PaperPosition:
    return PaperPosition(
        symbol="QQQ",
        quantity=qty,
        entry_price=entry,
        entry_date=AS_OF - timedelta(days=10),
        high_water_mark=entry,
    )


class TestConfig:
    def test_symbol_uppercased_and_target_bounds(self):
        assert CoreHolding(symbol="qqq").symbol == "QQQ"
        for bad in (0.0, 1.5):
            with pytest.raises(ValueError):
                CoreHolding(symbol="QQQ", target_pct=bad)

    def test_core_must_not_be_a_strategy_symbol(self, tmp_path):
        with pytest.raises(ValueError, match="must not also be in symbols"):
            universe(tmp_path, symbols=["AAA", "QQQ"])


class TestNeverExited:
    def test_signal_exits_skip_core_but_not_strategy_positions(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position()
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA", quantity=1.0, entry_price=50.0, entry_date=AS_OF, high_water_mark=50.0
        )
        intents, prices = generate_intents(u, store(), ledger, as_of=AS_OF)
        sold = {i.symbol for i in intents if i.side == "sell"}
        assert "AAA" in sold  # the strategy position exits on its rule
        assert "QQQ" not in sold  # the core never does
        assert prices["QQQ"] == 100.0  # but it is priced for equity

    def test_intraday_sweep_never_stops_the_core(self, tmp_path):
        u = universe(tmp_path)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position(entry=100.0)
        crash = check_stops(u, ledger, {"QQQ": 50.0})  # -50%: far through any stop
        moon = check_stops(u, ledger, {"QQQ": 200.0})  # +100%: far through any TP
        assert crash == [] and moon == []

    def test_no_stop_levels_reported_for_core(self, tmp_path):
        u = universe(tmp_path)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position()
        assert "QQQ" not in compute_stop_levels(u, ledger, store(), as_of=AS_OF)


class TestTopUp:
    def test_buys_core_with_available_cash_despite_entry_pause(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])  # strategy entries paused
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
        buys = [i for i in intents if i.side == "buy"]
        assert len(buys) == 1 and buys[0].symbol == "QQQ"
        assert buys[0].dollar_amount == pytest.approx(140.0 - 5.0)  # all cash minus buffer
        assert buys[0].strategy_name == "core_holding"

    def test_ignores_max_position_usd_but_respects_settled_cash(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF, settled_buying_power=40.0)
        (buy,) = [i for i in intents if i.side == "buy"]
        assert buy.dollar_amount == pytest.approx(40.0 - 5.0)  # > $30 cap, ≤ settled cash

    def test_no_topup_within_tolerance(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=2.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position(qty=1.4)  # 140 of 142 equity
        intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
        assert not [i for i in intents if i.side == "buy"]

    def test_partial_target_pct(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[], core={"symbol": "QQQ", "target_pct": 0.5})
        ledger = PaperLedger(cash=100.0, starting_cash=100.0)
        (buy,) = [
            i for i in generate_intents(u, store(), ledger, as_of=AS_OF)[0] if i.side == "buy"
        ]
        assert buy.dollar_amount == pytest.approx(50.0)

    def test_no_topup_while_a_core_buy_is_pending(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        ledger.fills.append(
            PaperFill(
                symbol="QQQ",
                side="buy",
                quantity=0.0,
                price=100.0,
                notional=0.0,
                reason="no_fill: queued",
                filled_at=AS_OF,
                broker_order_id="o-1",
            )
        )
        intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
        assert not [i for i in intents if i.side == "buy"]

    def test_kill_switch_blocks_core_buys(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        ledger.halt("test halt")
        intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
        assert not [i for i in intents if i.side == "buy"]

    def test_core_does_not_use_a_strategy_slot(self, tmp_path):
        u = universe(
            tmp_path,
            core={"symbol": "QQQ", "target_pct": 0.1},
            risk={
                "starting_cash_usd": 150.0,
                "max_position_usd": 30.0,
                "max_positions": 1,
                "max_daily_buys": 3,
                "min_cash_buffer_usd": 5.0,
            },
        )
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position(qty=0.1)  # ~7% of equity: below target
        intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
        assert "AAA" in {i.symbol for i in intents if i.side == "buy"}  # slot still free


class TestAddToCore:
    def intent(self, dollars, order_id=None, symbol="QQQ"):
        return TradeIntent(
            symbol=symbol,
            side="buy",
            dollar_amount=dollars,
            reason="t",
            signal_price=100.0,
            signal_date=AS_OF,
            strategy_name="t",
            broker_order_id=order_id,
        )

    def test_weighted_average_entry_and_quantity(self):
        ledger = PaperLedger(cash=200.0, starting_cash=300.0)
        ledger.positions["QQQ"] = core_position(qty=1.0, entry=100.0)
        ledger.apply_buy(self.intent(120.0), 120.0, add_to_existing=True)  # +1 sh @ 120
        pos = ledger.positions["QQQ"]
        assert pos.quantity == pytest.approx(2.0)
        assert pos.entry_price == pytest.approx(110.0)
        assert ledger.cash == pytest.approx(80.0)

    def test_duplicate_broker_order_refused(self):
        ledger = PaperLedger(cash=300.0, starting_cash=300.0)
        ledger.apply_buy(self.intent(100.0, "o-1"), 100.0, add_to_existing=True)
        with pytest.raises(ValueError, match="already recorded"):
            ledger.apply_buy(self.intent(100.0, "o-1"), 100.0, add_to_existing=True)

    def test_non_core_still_one_position_per_symbol(self):
        ledger = PaperLedger(cash=300.0, starting_cash=300.0)
        ledger.apply_buy(self.intent(50.0, symbol="AAA"), 50.0)
        with pytest.raises(ValueError, match="already open"):
            ledger.apply_buy(self.intent(50.0, symbol="AAA"), 50.0)

    def test_execute_paper_adds_only_for_core(self):
        ledger = PaperLedger(cash=300.0, starting_cash=300.0)
        ledger.positions["QQQ"] = core_position()
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA", quantity=1.0, entry_price=50.0, entry_date=AS_OF, high_water_mark=50.0
        )
        fills, errors = execute_paper(
            ledger,
            [self.intent(100.0), self.intent(50.0, symbol="AAA")],
            {"QQQ": 100.0, "AAA": 50.0},
            core_symbol="QQQ",
        )
        assert ledger.positions["QQQ"].quantity == pytest.approx(2.0)
        assert len(fills) == 1 and any("AAA" in e for e in errors)

    def test_pending_core_buy_resolves_into_held_core(self, tmp_path):
        u = universe(tmp_path)
        ledger = PaperLedger(cash=100.0, starting_cash=200.0)
        ledger.positions["QQQ"] = core_position()
        ledger.fills.append(
            PaperFill(
                symbol="QQQ",
                side="buy",
                quantity=0.0,
                price=100.0,
                notional=0.0,
                reason="no_fill: queued",
                filled_at=AS_OF,
                broker_order_id="o-9",
            )
        )
        report = resolve_pending_fills(
            u,
            ledger,
            {"o-9": PendingOrderOutcome(state="filled", filled_quantity=0.5, average_price=100.0)},
        )
        assert not report.errors, report.errors
        assert ledger.positions["QQQ"].quantity == pytest.approx(1.5)


class TestEndToEnd:
    def test_kill_switch_still_flattens_the_core(self, tmp_path):
        """The kill switch keeps its meaning: a tripped halt sells EVERYTHING, core
        included. (With a 100% QQQ core, a QQQ bear market deeper than
        max_drawdown_halt WILL trip it — a human-only setting to revisit at cutover.)"""
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position(qty=1.5, entry=100.0)
        ledger.peak_equity = 150.0
        intents, _ = generate_intents(u, store(qqq=60.0), ledger, as_of=AS_OF)  # equity 90: -40%
        assert ledger.halted
        assert any(i.symbol == "QQQ" and i.side == "sell" for i in intents)

    def test_full_refresh_includes_core(self, tmp_path):
        from bonito.trading.live_runner import refresh_data

        class Rec:
            def __init__(self):
                self.got = []

            def ingest_from_yahoo(self, symbol, start, end, timeframe):
                self.got.append(symbol)
                return 1

        rec = Rec()
        refresh_data(universe(tmp_path), rec)
        assert "QQQ" in rec.got

    def test_replay_holds_core_through_a_crash(self, tmp_path):
        """Account replay: a never-entering strategy + 100% core. A -30% intraday
        crash day must not sell the core (no stops), equity tracks QQQ."""
        from bonito.trading.portfolio_backtest import ReplayStore, backtest_account

        never = dict(EXIT_HAPPY)
        never["entry_rules"] = [
            {
                "conditions": [{"left": "close", "comparison": "lt", "right": 0.0}],
                "logic": "AND",
                "side": "long",
            }
        ]
        sp = tmp_path / "never.json"
        sp.write_text(json.dumps(never))
        u = UniverseConfig(
            name="t",
            symbols=["AAA"],
            strategy_path=str(sp),
            mode="paper",
            data={"timeframe": "1d", "start_date": "2026-01-01"},
            risk={
                "starting_cash_usd": 1000.0,
                "min_cash_buffer_usd": 0.0,
                "max_drawdown_halt": None,
            },
            core_holding={"symbol": "QQQ"},
        )
        start = datetime(2026, 1, 1)
        q = [100.0] * 10 + [70.0] + [100.0] * 9
        days = [start + timedelta(days=i) for i in range(20)]
        qqq = BarData(
            symbol="QQQ",
            timeframe="1d",
            timestamps=days,
            opens=q,
            highs=[c * 1.001 for c in q],
            lows=[c * 0.999 for c in q],
            closes=q,
            volumes=[1e6] * 20,
        )
        aaa = BarData(
            symbol="AAA",
            timeframe="1d",
            timestamps=days,
            opens=[50.0] * 20,
            highs=[50.0] * 20,
            lows=[50.0] * 20,
            closes=[50.0] * 20,
            volumes=[1e6] * 20,
        )
        r = backtest_account(u, ReplayStore({"QQQ": qqq, "AAA": aaa}), days[0], days[-1])
        assert not [t for t in r.trades if t.symbol == "QQQ"]  # never sold
        assert r.open_position_entries["QQQ"].quantity == pytest.approx(10.0)  # 1000 / 100
        assert r.final_equity == pytest.approx(1000.0, rel=0.01)  # round trip of the crash


def test_record_fill_cli_adds_to_core(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import bonito.cli as cli
    from bonito.cli import app

    u = universe(tmp_path, mode="live")
    ledger = PaperLedger(cash=100.0, starting_cash=200.0)
    ledger.positions["QQQ"] = core_position()
    saved = {}
    monkeypatch.setattr(cli, "_load_universe", lambda path: u)
    monkeypatch.setattr(cli, "_load_ledger", lambda universe: ledger)
    monkeypatch.setattr(PaperLedger, "save", lambda self, *a, **k: saved.setdefault("ok", True))
    result = CliRunner().invoke(
        app,
        [
            "live",
            "record-fill",
            "QQQ",
            "buy",
            "100",
            "--shares",
            "0.5",
            "--dollars",
            "50",
            "--broker-order-id",
            "o-77",
        ],
    )
    assert result.exit_code == 0, result.output
    assert ledger.positions["QQQ"].quantity == pytest.approx(1.5)


def test_tolerance_blocks_tiny_topups_even_with_ample_cash(tmp_path):
    """Gap of $1.50 on $100 equity (< 2% tolerance) with $51 cash: no churn order."""
    u = universe(tmp_path, entry_allowlist=[], core={"symbol": "QQQ", "target_pct": 0.5})
    ledger = PaperLedger(cash=51.5, starting_cash=100.0)
    ledger.positions["QQQ"] = core_position(qty=0.485)  # 48.5 held → equity 100, target 50
    intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
    assert not [i for i in intents if i.side == "buy"]
    ledger.positions["QQQ"] = core_position(qty=0.40)  # gap 9.75 > tolerance → tops up
    ledger.cash = 51.5 + 8.5
    intents, _ = generate_intents(u, store(), ledger, as_of=AS_OF)
    assert [i for i in intents if i.side == "buy" and i.symbol == "QQQ"]


# --- after the core-hold review (NEEDS_WORK) ------------------------------------


def sentinel(symbol="QQQ", price=100.0, order_id="o-q", side="buy"):
    return PaperFill(
        symbol=symbol,
        side=side,
        quantity=0.0,
        price=price,
        notional=0.0,
        reason="no_fill: queued",
        filled_at=AS_OF,
        broker_order_id=order_id,
    )


class TestReconcileQueuedCoreTopUp:
    """Review MAJOR: a top-up queued overnight fills onto the HELD core; the broker
    then shows ledger + X shares before resolve-pending runs (the intraday sweep
    reconciles first) — that must be pending-explained, not FATAL all day."""

    def gate(self, ledger, broker):
        from bonito.trading.live_runner import reconcile_gate

        return reconcile_gate(ledger, broker, max_position_usd=30.0, core_symbol="QQQ")

    def held_core(self, cash=60.0, qty=2.0):
        ledger = PaperLedger(cash=cash, starting_cash=300.0)
        ledger.positions["QQQ"] = core_position(qty=qty)
        return ledger

    def test_excess_from_a_queued_topup_is_explained(self):
        ledger = self.held_core()
        ledger.fills.append(sentinel())
        r = self.gate(ledger, {"QQQ": 2.5})  # +0.5 sh ≈ $50 ≤ 1.25 × $60 cash
        assert not r.fatal_drift and r.pending_explained == ["QQQ"]

    def test_excess_without_a_sentinel_stays_fatal(self):
        r = self.gate(self.held_core(), {"QQQ": 2.5})
        assert r.fatal_drift

    def test_excess_beyond_cash_bound_stays_fatal(self):
        ledger = self.held_core(cash=60.0)
        ledger.fills.append(sentinel())
        r = self.gate(ledger, {"QQQ": 3.0})  # +1 sh = $100 > 1.25 × $60
        assert r.fatal_drift

    def test_first_core_buy_bounded_by_cash_not_max_position_usd(self):
        """$135 first core buy > 4 × $30 cap, but within cash → explained."""
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        ledger.fills.append(sentinel())
        r = self.gate(ledger, {"QQQ": 1.35})
        assert not r.fatal_drift and r.pending_explained == ["QQQ"]

    def test_non_core_held_symbol_excess_still_fatal(self):
        ledger = PaperLedger(cash=60.0, starting_cash=300.0)
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA", quantity=2.0, entry_price=50.0, entry_date=AS_OF, high_water_mark=50.0
        )
        ledger.fills.append(sentinel(symbol="AAA", price=50.0))
        r = self.gate(ledger, {"AAA": 2.2})
        assert r.fatal_drift  # only the core may grow overnight

    def test_reconcile_cli_passes_core(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        import bonito.cli as cli
        from bonito.cli import app

        u = universe(tmp_path, mode="live")
        ledger = self.held_core()
        ledger.fills.append(sentinel())
        monkeypatch.setattr(cli, "_load_universe", lambda path: u)
        monkeypatch.setattr(cli, "_load_ledger", lambda universe: ledger)
        r = CliRunner().invoke(app, ["live", "reconcile", '{"QQQ": 2.5}'])
        assert r.exit_code == 0, r.output


class TestGuardsPinnedAfterReview:
    def test_forming_or_stale_core_bar_blocks_topup(self, tmp_path):
        u = universe(tmp_path, entry_allowlist=[])
        ledger = PaperLedger(cash=140.0, starting_cash=150.0)
        stale = FakeStore(
            {
                "QQQ": bars("QQQ", [100.0] * 30, end=AS_OF - timedelta(days=30)),
                "AAA": bars("AAA", [50.0] * 30),
            }
        )
        assert not [
            i for i in generate_intents(u, stale, ledger, as_of=AS_OF)[0] if i.side == "buy"
        ]
        forming_day = datetime(2026, 6, 8, 15, 0)  # 11:00 ET on 06-08: today's bar not settled
        forming = FakeStore(
            {
                "QQQ": bars("QQQ", [100.0] * 30, end=datetime(2026, 6, 8, 4)),
                "AAA": bars("AAA", [50.0] * 30, end=datetime(2026, 6, 8, 4)),
            }
        )
        out = generate_intents(u, forming, ledger, as_of=forming_day)[0]
        assert not [i for i in out if i.side == "buy"]

    def test_replay_store_loads_core_and_counts_its_days(self, tmp_path):
        from bonito.trading.portfolio_backtest import ReplayStore

        u = universe(tmp_path)
        s = FakeStore({"QQQ": bars("QQQ", [100.0] * 5), "AAA": bars("AAA", [50.0] * 5)})
        rp = ReplayStore.from_store(s, u, LAST_BAR)
        assert "QQQ" in rp.bars

    def test_resolving_a_core_add_keeps_the_original_entry_date(self, tmp_path):
        u = universe(tmp_path)
        ledger = PaperLedger(cash=100.0, starting_cash=200.0)
        ledger.positions["QQQ"] = core_position()
        original = ledger.positions["QQQ"].entry_date
        ledger.fills.append(sentinel(order_id="o-9"))
        later = AS_OF + timedelta(days=3)
        resolve_pending_fills(
            u,
            ledger,
            {
                "o-9": PendingOrderOutcome(
                    state="filled", filled_quantity=0.5, average_price=100.0, executed_at=later
                )
            },
        )
        assert ledger.positions["QQQ"].entry_date == original

    def test_position_atrs_skip_core(self, tmp_path):
        from bonito.trading.live_runner import compute_position_atrs

        atr_strategy = dict(
            EXIT_HAPPY, stop_loss={"type": "trailing_atr", "value": 2.0, "atr_period": 14}
        )
        sp = tmp_path / "atr.json"
        sp.write_text(json.dumps(atr_strategy))
        u = universe(tmp_path, strategy_path=str(sp))
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        ledger.positions["QQQ"] = core_position()
        ledger.positions["AAA"] = PaperPosition(
            symbol="AAA", quantity=1.0, entry_price=50.0, entry_date=AS_OF, high_water_mark=50.0
        )
        atrs = compute_position_atrs(u, ledger, store(), as_of=AS_OF)
        assert "QQQ" not in atrs and "AAA" in atrs

    def test_replay_merges_core_lots_and_keeps_entry_date(self):
        from bonito.trading.portfolio_backtest import _closed_trades

        ledger = PaperLedger(cash=0.0, starting_cash=300.0)
        d0, d1, d2 = AS_OF, AS_OF + timedelta(days=5), AS_OF + timedelta(days=9)
        for q, px, d in ((1.0, 100.0, d0), (1.0, 120.0, d1)):
            ledger.fills.append(
                PaperFill(
                    symbol="QQQ",
                    side="buy",
                    quantity=q,
                    price=px,
                    notional=q * px,
                    reason="t",
                    filled_at=d,
                )
            )
        ledger.fills.append(
            PaperFill(
                symbol="QQQ",
                side="sell",
                quantity=2.0,
                price=130.0,
                notional=260.0,
                reason="kill switch",
                filled_at=d2,
            )
        )
        (trade,) = _closed_trades(ledger)
        assert trade.entry_price == pytest.approx(110.0)
        assert trade.pnl == pytest.approx(40.0)  # (130 − 110) × 2, not (130 − 120) × 2
        assert trade.entry_date == d0

    def test_tracking_does_not_count_core_topups_as_divergence(self, tmp_path):
        from bonito.trading.tracking import run_tracking

        u = universe(
            tmp_path,
            entry_allowlist=[],
            core={"symbol": "QQQ"},
            risk={"starting_cash_usd": 300.0, "min_cash_buffer_usd": 0.0},
        )
        start = datetime(2026, 5, 1)
        days = [start + timedelta(days=i) for i in range(30)]
        q = BarData(
            symbol="QQQ",
            timeframe="1d",
            timestamps=days,
            opens=[100.0] * 30,
            highs=[100.0] * 30,
            lows=[100.0] * 30,
            closes=[100.0] * 30,
            volumes=[1.0] * 30,
        )
        ledger = PaperLedger(cash=100.0, starting_cash=300.0)
        for _i, d in enumerate((days[2], days[5], days[9])):
            ledger.fills.append(
                PaperFill(
                    symbol="QQQ",
                    side="buy",
                    quantity=0.66,
                    price=100.0,
                    notional=66.0,
                    reason="core",
                    filled_at=d,
                )
            )
        report = run_tracking(
            u,
            ledger,
            FakeStore({"QQQ": q, "AAA": bars("AAA", [50.0] * 30, end=days[-1])}),
            end=days[-1],
        )
        assert report.paper_fills == 0 and report.decision_divergence == 0.0


def test_replay_restamp_keeps_entry_date_on_core_add_but_stamps_new_positions():
    from bonito.trading.portfolio_backtest import _restamp

    ledger = PaperLedger(cash=0.0, starting_cash=300.0)
    ledger.positions["QQQ"] = core_position(qty=1.5)  # 1.0 held + 0.5 just added
    original = ledger.positions["QQQ"].entry_date
    ledger.positions["AAA"] = PaperPosition(
        symbol="AAA", quantity=2.0, entry_price=50.0, entry_date=AS_OF, high_water_mark=50.0
    )
    n = len(ledger.fills)
    for sym, q in (("QQQ", 0.5), ("AAA", 2.0)):
        ledger.fills.append(
            PaperFill(
                symbol=sym,
                side="buy",
                quantity=q,
                price=100.0,
                notional=q * 100.0,
                reason="t",
                filled_at=AS_OF,
            )
        )
    day = AS_OF + timedelta(days=4)
    _restamp(ledger, n, day)
    assert ledger.positions["QQQ"].entry_date == original  # add: keep
    assert ledger.positions["AAA"].entry_date == day  # opened by this fill: stamp


def test_core_shortfall_stays_fatal_even_with_a_buy_sentinel():
    """Broker holds LESS core than the ledger (sold/missing shares): a pending BUY
    can't explain a shortfall — it must stay FATAL (review re-check)."""
    from bonito.trading.live_runner import reconcile_gate

    ledger = PaperLedger(cash=98.0, starting_cash=300.0)
    ledger.positions["QQQ"] = core_position(qty=0.3, entry=500.0)
    ledger.fills.append(sentinel(price=500.0))
    r = reconcile_gate(ledger, {"QQQ": 0.2}, max_position_usd=30.0, core_symbol="QQQ")
    assert r.fatal_drift and r.pending_explained == []
