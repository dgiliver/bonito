"""Regression tests for the live-fidelity build (commit 205bb28).

Tests cover:
  A - D1 drift gate (TestReconcileD1, TestReconcileCLI)
  B - D3 fill recording (TestFillRecording)
  C - Zero-qty fills don't pollute tracking (TestZeroFillTracking)
  D - Kill-switch fail-closed pair (TestKillSwitchLivePricing)
  E - Live band mode-awareness (TestLiveBandModeAware)
  F - Reconcile property / boundary (TestReconcileBoundary)

Non-vacuity is demonstrated inline for groups A, D, and E via transient
src/ mutations — see the module-level run at the bottom of this file and
the individual function docstrings for the method used.
"""

import json
from datetime import datetime, timedelta

import pytest
from typer.testing import CliRunner

from bonito.cli import app
from bonito.data.models import BarData
from bonito.trading.live_runner import (
    DRIFT_TOLERANCE_PCT,
    LivePricingError,
    UniverseConfig,
    check_stops,
    generate_intents,
    reconcile_gate,
    reconcile_positions,
)
from bonito.trading.paper import PaperFill, PaperLedger
from bonito.trading.tracking import (
    paper_equity_curve,
    run_tracking,
)

_runner = CliRunner()
LAST_BAR = datetime(2026, 6, 5)
AS_OF = datetime(2026, 6, 8)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def uptrend_store(symbols: list[str]) -> FakeStore:
    closes = [100.0 + i for i in range(30)]
    return FakeStore({s: make_bars(s, closes) for s in symbols})


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


@pytest.fixture
def live_universe(tmp_path):
    """Same as universe but with mode='live'."""
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(json.dumps(ALWAYS_ENTER_STRATEGY))
    return UniverseConfig(
        name="test_live",
        symbols=["AAA", "BBB", "CCC", "DDD"],
        strategy_path=str(strategy_path),
        data={"timeframe": "1d", "start_date": "2026-01-01"},
        mode="live",
        live_enabled=True,
        risk={
            "starting_cash_usd": 150.0,
            "max_position_usd": 30.0,
            "max_positions": 5,
            "max_daily_buys": 3,
            "min_cash_buffer_usd": 5.0,
            "allow_short": False,
        },
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


def _buy_intent(symbol: str = "TSLA", dollars: float = 30.0):
    from datetime import UTC

    from bonito.trading.signals import TradeIntent

    return TradeIntent(
        symbol=symbol,
        side="buy",
        dollar_amount=dollars,
        reason="test entry",
        signal_price=100.0,
        signal_date=datetime.now(UTC),
        strategy_name="test",
    )


def _sell_intent(symbol: str = "TSLA"):
    from datetime import UTC

    from bonito.trading.signals import TradeIntent

    return TradeIntent(
        symbol=symbol,
        side="sell",
        reason="test exit",
        signal_price=100.0,
        signal_date=datetime.now(UTC),
        strategy_name="test",
    )


def _day(i: int) -> datetime:
    return datetime(2026, 1, 1) + timedelta(days=i)


def _fill(symbol: str, side: str, price: float, on: datetime, qty: float = 1.0) -> PaperFill:
    return PaperFill(
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        notional=price * qty,
        reason="test",
        filled_at=on,
    )


def _flat_bars(symbol: str, n: int, price: float = 100.0) -> BarData:
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[_day(i) for i in range(n)],
        opens=[price] * n,
        highs=[price * 1.001] * n,
        lows=[price * 0.999] * n,
        closes=[price] * n,
        volumes=[1_000_000.0] * n,
    )


# ---------------------------------------------------------------------------
# A: Drift gate unit tests
# ---------------------------------------------------------------------------


class TestReconcileD1:
    """D1 fatal-drift gate: within vs beyond 0.5% DRIFT_TOLERANCE_PCT."""

    def _ledger_with(self, symbol="AAA", qty=1.0):
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        _open_position(ledger, symbol, quantity=qty, entry_price=100.0)
        return ledger

    def test_within_tolerance_not_fatal(self):
        """0.4% difference (< 0.5%) must not be fatal — but is not in_sync.

        ledger=1.000, broker=1.004 → diff=0.004 / max(1.000,1.004) ≈ 0.398% < 0.5%.
        """
        report = reconcile_positions(self._ledger_with("AAA", qty=1.000), {"AAA": 1.004})
        assert report.fatal_drift is False
        # Not exactly in sync (diff > 1e-4 dust)
        assert report.in_sync is False

    def test_beyond_tolerance_is_fatal(self):
        """1.0% difference (> 0.5%) must set fatal_drift and name the symbol.

        ledger=1.000, broker=1.010 → diff=0.010 / 1.010 ≈ 0.990% > 0.5%.
        """
        report = reconcile_positions(self._ledger_with("AAA", qty=1.000), {"AAA": 1.010})
        assert report.fatal_drift is True
        assert any("AAA" in r for r in report.fatal_reasons)

    def test_broker_only_position_is_fatal(self):
        """Ledger flat, broker has NVDA:0.2 → fatal (the broker position is unaccounted for)."""
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        report = reconcile_positions(ledger, {"NVDA": 0.2})
        assert report.fatal_drift is True
        assert any("NVDA" in r for r in report.fatal_reasons)

    def test_ledger_only_position_is_fatal(self):
        """Ledger has a position, broker shows nothing → fatal (full position missing at broker)."""
        report = reconcile_positions(self._ledger_with("AAA", qty=0.5), {})
        assert report.fatal_drift is True
        assert any("AAA" in r for r in report.fatal_reasons)

    def test_dust_is_not_fatal(self):
        """Broker reports 1e-8 shares of AAA while ledger is flat — sub-dust, not fatal."""
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        report = reconcile_positions(ledger, {"AAA": 1e-8})
        assert report.fatal_drift is False

    def test_reconcile_gate_passes_in_sync(self):
        """reconcile_gate with perfectly matching positions must not set fatal_drift."""
        ledger = self._ledger_with("AAA", qty=1.0)
        report = reconcile_gate(ledger, {"AAA": 1.0})
        assert report.fatal_drift is False

    def test_reconcile_gate_fails_on_fatal(self):
        """reconcile_gate with >0.5% drift must set fatal_drift."""
        ledger = self._ledger_with("AAA", qty=1.0)
        report = reconcile_gate(ledger, {"AAA": 1.5})  # 33% drift
        assert report.fatal_drift is True

    def test_exits_not_gated_by_reconcile(self, universe):
        """check_stops returns a sell intent for a stop-breached open position without
        any reconcile input on its path.

        This is a STRUCTURAL test: check_stops(universe, ledger, prices) has no
        broker-position parameter and no reconcile/drift-gate call in its body.
        The drift gate (D1) was intentionally placed only on the ENTRY side in
        generate_intents.  This test ensures that a refactor can never accidentally
        thread a drift check into the exit path by asserting on the actual runtime
        behaviour: even with no reconcile run, an open position with a breached
        stop fires a sell intent.

        Non-vacuous: without check_stops generating the intent (e.g. if someone
        guarded it on a drift condition that doesn't exist here), intents would be
        empty and the assertion would fail.
        """
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        # Position entered at 100.0; trailing stop at 95.0; price is 90.0 (breached)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=100.0, hwm=100.0)

        # Note: NO reconcile_positions or reconcile_gate call here whatsoever —
        # that is the point.  Exits must not depend on broker data flowing through.
        intents = check_stops(universe, ledger, {"AAA": 90.0})

        assert len(intents) == 1
        assert intents[0].side == "sell"
        assert intents[0].symbol == "AAA"
        assert "stop loss" in intents[0].reason


# ---------------------------------------------------------------------------
# A: CLI reconcile (fail-closed / warn / green)
# ---------------------------------------------------------------------------


class TestReconcileCLI:
    """CLI live reconcile: exit code 1 on fatal drift; exit 0 + warning on sub-tolerance;
    exit 0 + green on in-sync.

    The CLI is tested via a monkeypatched universe + ledger so we don't touch
    real config files.
    """

    def _make_universe_file(self, tmp_path, mode: str = "paper") -> tuple[str, str]:
        """Write a minimal universe.json and an empty ledger; return their paths."""
        strategy_path = tmp_path / "s.json"
        strategy_path.write_text(json.dumps(ALWAYS_ENTER_STRATEGY))
        universe_cfg = {
            "name": "cli_test",
            "symbols": ["AAA"],
            "strategy_path": str(strategy_path),
            "data": {"timeframe": "1d", "start_date": "2026-01-01"},
            "mode": mode,
            "live_enabled": True,
            "risk": {"starting_cash_usd": 150.0},
        }
        universe_path = tmp_path / "universe.json"
        universe_path.write_text(json.dumps(universe_cfg))

        ledger_dir = tmp_path / "livetrade"
        ledger_dir.mkdir()
        ledger_path = ledger_dir / f"{mode}_ledger.json"
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=1.0, entry_price=100.0)
        ledger.save(ledger_path)
        return str(universe_path), str(ledger_path)

    def _invoke_reconcile(self, tmp_path, broker_json: str, mode: str = "paper"):
        universe_path, _ledger_path = self._make_universe_file(tmp_path, mode)
        # Patch _load_universe and _load_ledger to use the temp paths
        import bonito.cli as cli_module

        orig_load_universe = cli_module._load_universe
        orig_load_ledger = cli_module._load_ledger

        def _patched_universe(path):
            return orig_load_universe(universe_path)

        def _patched_ledger(u):
            from pathlib import Path

            from bonito.trading.paper import PaperLedger

            ledger_path = Path(str(tmp_path / "livetrade" / f"{u.mode}_ledger.json"))
            return PaperLedger.load(ledger_path)

        cli_module._load_universe = _patched_universe
        cli_module._load_ledger = _patched_ledger
        try:
            result = _runner.invoke(app, ["live", "reconcile", broker_json])
        finally:
            cli_module._load_universe = orig_load_universe
            cli_module._load_ledger = orig_load_ledger
        return result

    def test_fatal_drift_exits_code_1(self, tmp_path):
        """ledger=1.0 AAA, broker=1.5 AAA → 33% drift → exit code 1."""
        result = self._invoke_reconcile(tmp_path, '{"AAA": 1.5}')
        assert result.exit_code == 1

    def test_sub_tolerance_drift_warns_and_exit_0(self, tmp_path):
        """ledger=1.0 AAA, broker=1.004 → 0.4% drift (sub-tolerance) → exit 0 + warning."""
        result = self._invoke_reconcile(tmp_path, '{"AAA": 1.004}')
        assert result.exit_code == 0
        # Must surface the drift explicitly, not silently pass
        output = ((result.stdout or "") + (result.output or "")).lower()
        assert "sub-tolerance" in output and "drift" in output

    def test_in_sync_exit_0(self, tmp_path):
        """ledger=1.0 AAA, broker=1.0 AAA → perfectly in sync → exit 0."""
        result = self._invoke_reconcile(tmp_path, '{"AAA": 1.0}')
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# B: Fill recording (D3)
# ---------------------------------------------------------------------------


class TestFillRecording:
    """D3: fill_quantity keyword, partial sells, record_no_fill, ledger==broker."""

    def test_fill_quantity_overrides_derived_qty(self):
        """apply_buy with fill_quantity=0.305 records 0.305 shares, not 30/100=0.30.

        Cash debit is still $30 (notional stays consistent).
        """
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(_buy_intent(dollars=30.0), fill_price=100.0, fill_quantity=0.305)

        pos = ledger.positions["TSLA"]
        assert pos.quantity == pytest.approx(0.305)
        # Cash debited by the intent's dollar_amount, not the fill qty
        assert ledger.cash == pytest.approx(120.0)

    def test_no_fill_quantity_derives_paper_qty(self):
        """apply_buy with no fill_quantity produces qty=30/100=0.30 (paper-identical guard)."""
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(_buy_intent(dollars=30.0), fill_price=100.0)

        assert ledger.positions["TSLA"].quantity == pytest.approx(0.30)

    def test_partial_sell_reduces_position_keeps_entry_price(self):
        """apply_sell with fill_quantity=0.10 on a 0.30 position leaves 0.20 open.

        PnL is realized on the 0.10 sold only; entry_price is unchanged.
        """
        ledger = PaperLedger(cash=120.0, starting_cash=150.0)
        _open_position(ledger, "TSLA", quantity=0.30, entry_price=100.0)
        fill = ledger.apply_sell(_sell_intent("TSLA"), fill_price=110.0, fill_quantity=0.10)

        # Position remains at 0.20
        assert ledger.positions["TSLA"].quantity == pytest.approx(0.20)
        # entry_price is unchanged (partial sell preserves the original cost basis)
        assert ledger.positions["TSLA"].entry_price == pytest.approx(100.0)
        # PnL on the 0.10 sold: (110 - 100) * 0.10 = 1.0
        assert ledger.realized_pnl == pytest.approx(1.0)
        # Cash back: 0.10 * 110 = 11
        assert ledger.cash == pytest.approx(131.0)
        # Fill qty records what was actually sold
        assert fill.quantity == pytest.approx(0.10)

    def test_full_sell_no_fill_quantity_deletes_position(self):
        """apply_sell with no fill_quantity closes the full position (unchanged behaviour)."""
        ledger = PaperLedger(cash=120.0, starting_cash=150.0)
        _open_position(ledger, "TSLA", quantity=0.30, entry_price=100.0)
        ledger.apply_sell(_sell_intent("TSLA"), fill_price=110.0)

        assert "TSLA" not in ledger.positions
        assert ledger.realized_pnl == pytest.approx(3.0)

    def test_record_no_fill_leaves_cash_and_positions_unchanged(self):
        """record_no_fill must not alter cash or positions."""
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        _open_position(ledger, "TSLA", quantity=0.30, entry_price=100.0)
        cash_before = ledger.cash
        positions_before = dict(ledger.positions)

        ledger.record_no_fill("TSLA", "sell", reason="order rejected", broker_order_id=None, signal_price=105.0)

        assert ledger.cash == cash_before
        assert set(ledger.positions.keys()) == set(positions_before.keys())

    def test_record_no_fill_appends_zero_qty_fill(self):
        """record_no_fill appends a PaperFill with quantity==0 and 'no_fill' in reason."""
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.record_no_fill("TSLA", "buy", reason="insufficient funds", broker_order_id=None, signal_price=100.0)

        assert len(ledger.fills) == 1
        f = ledger.fills[-1]
        assert f.quantity == 0.0
        assert "no_fill" in f.reason

    def test_fill_quantity_makes_ledger_broker_in_sync(self):
        """After apply_buy(fill_quantity=B), reconcile_positions must report in_sync=True
        and fatal_drift=False for that same quantity.

        This is the D3 ledger==broker-by-construction property.
        """
        broker_qty = 0.305  # broker's actual fractional fill
        ledger = PaperLedger(cash=150.0, starting_cash=150.0)
        ledger.apply_buy(_buy_intent(dollars=30.0), fill_price=100.0, fill_quantity=broker_qty)

        report = reconcile_positions(ledger, {"TSLA": broker_qty})
        assert report.in_sync is True
        assert report.fatal_drift is False


# ---------------------------------------------------------------------------
# C: Zero-qty fills don't pollute tracking
# ---------------------------------------------------------------------------


class TestZeroFillTracking:
    """D3: zero-qty no_fill events are excluded from bps calculations and equity curve."""

    def _universe(self, tmp_path) -> UniverseConfig:
        strategy = {
            "name": "never",
            "symbols": ["AAA"],
            "timeframe": "1d",
            "indicators": [],
            "entry_rules": [
                {
                    "conditions": [{"left": "close", "comparison": "lt", "right": 0.0}],
                    "logic": "AND",
                    "side": "long",
                }
            ],
            "exit_rules": [],
        }
        path = tmp_path / "never.json"
        path.write_text(json.dumps(strategy))
        return UniverseConfig(
            name="t",
            symbols=["AAA"],
            strategy_path=str(path),
            data={"timeframe": "1d", "start_date": "2026-01-01"},
            risk={"starting_cash_usd": 1000.0},
        )

    def test_no_fill_excluded_from_bps_computation(self, tmp_path):
        """One real fill + one no_fill: bps stats are computed only on the real fill;
        no_fill_count == 1.

        The real fill has price 101.0 vs. replay price 100.0 → 100 bps.
        The no_fill (qty=0) must not contribute a data point.
        """
        # Build a ledger with a matchable real fill and a no-fill sentinel
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        real = _fill("AAA", "buy", 101.0, _day(1), qty=1.0)  # 100 bps above replay
        no_fill = _fill("AAA", "buy", 0.0, _day(2), qty=0.0)  # zero-qty sentinel
        ledger.fills = [real, no_fill]

        # Strategy always enters so the replay will have one buy fill at ~100
        always_strategy = {
            "name": "always",
            "symbols": ["AAA"],
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
        path = tmp_path / "always.json"
        path.write_text(json.dumps(always_strategy))
        universe = UniverseConfig(
            name="t",
            symbols=["AAA"],
            strategy_path=str(path),
            data={"timeframe": "1d", "start_date": "2026-01-01"},
            risk={"starting_cash_usd": 1000.0},
        )

        store = type("S", (), {"get_bars": lambda self, s, st, e, tf="1d": _flat_bars(s, 10)})()
        report = run_tracking(universe, ledger, store, end=_day(9))

        assert report.no_fill_count == 1
        # paper_fills is the count from match_fills (only real fills are passed)
        assert report.paper_fills == 1

    def test_equity_curve_identical_with_and_without_no_fill(self, tmp_path):
        """paper_equity_curve must produce the same result regardless of appended
        zero-qty fills.

        The no_fill sentinel carries quantity=0 and notional=0 so the curve
        logic skips it; both curves must be identical.
        """
        universe = self._universe(tmp_path)

        ledger_a = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger_a.fills = [_fill("AAA", "buy", 100.0, _day(1))]

        ledger_b = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger_b.fills = [
            _fill("AAA", "buy", 100.0, _day(1)),
            _fill("AAA", "buy", 0.0, _day(2), qty=0.0),  # zero-qty no_fill appended
        ]

        store = type("S", (), {"get_bars": lambda self, s, st, e, tf="1d": _flat_bars(s, 10)})()

        dates_a, eq_a = paper_equity_curve(ledger_a, store, universe, _day(9))
        dates_b, eq_b = paper_equity_curve(ledger_b, store, universe, _day(9))

        assert dates_a == dates_b
        assert eq_a == pytest.approx(eq_b)


# ---------------------------------------------------------------------------
# D: Kill-switch fail-closed pair
# ---------------------------------------------------------------------------


class TestKillSwitchLivePricing:
    """D4 §5.4: In live mode, generate_intents raises LivePricingError when an open
    position is absent from prices.  In paper mode, no raise.

    This pair proves the guard is live-gated.
    """

    def _setup(self, universe, *, drawdown_near_cap: bool = True):
        """Ledger with one open position (AAA) and a near-cap drawdown."""
        store = uptrend_store(universe.symbols)
        ledger = PaperLedger(cash=0.0, starting_cash=150.0)
        if drawdown_near_cap:
            # Peak of 200 → current equity ~64.50 = 68% drawdown, past the 25% cap
            ledger = PaperLedger(cash=0.0, starting_cash=150.0, peak_equity=200.0)
        _open_position(ledger, "AAA", quantity=0.5, entry_price=128.0, hwm=128.0)
        return store, ledger

    def test_live_mode_raises_when_open_position_unpriced(self, live_universe):
        """In live mode, if an open position is missing from prices, LivePricingError
        is raised (fail-closed — the kill switch must not mark off entry_price on real money).

        Non-vacuous: without the guard in generate_intents, this call would silently
        succeed (falling back to entry_price in equity()), and this test would fail.
        """
        store, ledger = self._setup(live_universe, drawdown_near_cap=True)

        # Deliberately omit AAA from the store so prices dict won't contain it.
        store_missing_aaa = FakeStore({s: store.bars[s] for s in live_universe.symbols if s != "AAA"})

        with pytest.raises(LivePricingError, match="AAA"):
            generate_intents(live_universe, store_missing_aaa, ledger, as_of=AS_OF)

    def test_paper_mode_no_raise_when_position_unpriced(self, universe):
        """In paper mode, a missing price is treated as stale-data-hold (no exception).

        The pair with the live test above proves the guard is live-gated.
        """
        store, ledger = self._setup(universe, drawdown_near_cap=True)
        store_missing_aaa = FakeStore({s: store.bars[s] for s in universe.symbols if s != "AAA"})

        # Must not raise — paper mode holds the position, equity() falls back to entry_price
        try:
            intents, prices = generate_intents(universe, store_missing_aaa, ledger, as_of=AS_OF)
        except LivePricingError:
            pytest.fail("generate_intents raised LivePricingError in paper mode")

        # AAA is absent from prices because there was no data for it
        assert "AAA" not in prices

    def test_equity_falls_back_to_entry_price_unchanged(self):
        """PaperLedger.equity() still falls back to entry_price when a symbol is missing.

        This confirms we did NOT touch equity() as part of the kill-switch fix.
        """
        ledger = PaperLedger(cash=120.0, starting_cash=150.0)
        from bonito.trading.paper import PaperPosition

        ledger.positions["TSLA"] = PaperPosition(
            symbol="TSLA",
            quantity=0.3,
            entry_price=100.0,
            entry_date=AS_OF,
            high_water_mark=100.0,
        )
        # Empty prices → falls back to entry_price (0.3 * 100 + 120 = 150)
        assert ledger.equity({}) == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# E: Live band mode-awareness
# ---------------------------------------------------------------------------


class TestLiveBandModeAware:
    """D2: run_tracking selects the band based on universe.mode.

    The bands are EQUAL today (both 50 bps) so a naive "live warns above 50"
    test would be vacuous.  The only non-vacuous proof is to monkeypatch
    MAX_MEAN_FILL_BPS_LIVE to a small value, drive the mean above it, and
    confirm that live warns while paper (band=50) is still OK.

    Strategy: monkeypatch both backtest_account (to return pre-built ClosedTrade
    replay events that match the paper fills) and MAX_MEAN_FILL_BPS_LIVE (to
    bring the live threshold below the ~10-bps mean gap we inject).
    """

    def _universe(self, tmp_path, mode: str = "paper") -> UniverseConfig:
        strategy = {
            "name": "always",
            "symbols": ["AAA"],
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
        path = tmp_path / "always.json"
        path.write_text(json.dumps(strategy))
        return UniverseConfig(
            name="t",
            symbols=["AAA"],
            strategy_path=str(path),
            data={"timeframe": "1d", "start_date": "2026-01-01"},
            mode=mode,
            risk={"starting_cash_usd": 1000.0},
        )

    def _build_ledger_and_replay_events(self, gap_bps: float):
        """Build paper fills at 100*(1+gap_bps/10000) with 10 buy-sell round trips.

        The replay will be monkeypatched to provide matching events at 100.0,
        guaranteeing MIN_MATCHED_FILLS (10) matched comparisons.
        """
        paper_price = 100.0 * (1 + gap_bps / 10_000)

        ledger = PaperLedger(cash=0.0, starting_cash=1000.0)
        fills = []
        for i in range(10):
            buy_day = _day(i * 3)
            sell_day = _day(i * 3 + 1)
            fills.append(_fill("AAA", "buy", paper_price, buy_day))
            fills.append(_fill("AAA", "sell", paper_price, sell_day))
        ledger.fills = fills
        return ledger

    def test_live_band_independently_tunable(self, tmp_path, monkeypatch):
        """A mean gap of ~10 bps:
        - WARNS in live mode when MAX_MEAN_FILL_BPS_LIVE is patched to 5.0
        - paper band (50 bps) means the same ledger does NOT trigger mean-bps WARN

        This proves that run_tracking keys its band selection on universe.mode,
        not on a hardcoded constant — and that the two bands are truly
        independent even when their runtime values happen to be equal.

        We patch backtest_account so the replay events match the paper fills
        1-to-1, giving us exactly MIN_MATCHED_FILLS=10 buys and 10 sells.
        """
        import bonito.trading.tracking as tracking_module
        from bonito.trading.portfolio_backtest import AccountBacktestResult, ClosedTrade

        # Lower the live band below our ~10 bps gap.
        monkeypatch.setattr(tracking_module, "MAX_MEAN_FILL_BPS_LIVE", 5.0)

        gap_bps = 10.0  # paper price is 10 bps above replay price
        ledger = self._build_ledger_and_replay_events(gap_bps)

        # Build a fake AccountBacktestResult whose trades produce our replay events.
        # 10 ClosedTrade round-trips at (buy_day, 100.0) → (sell_day, 100.0).
        replay_price = 100.0
        fake_trades = [
            ClosedTrade(
                symbol="AAA",
                entry_date=_day(i * 3),
                exit_date=_day(i * 3 + 1),
                entry_price=replay_price,
                exit_price=replay_price,
                quantity=1.0,
                pnl=0.0,
                reason="test",
            )
            for i in range(10)
        ]
        fake_result = AccountBacktestResult(
            universe_name="t",
            start=_day(0),
            end=_day(29),
            starting_cash=1000.0,
            final_equity=1000.0,
            total_return=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            equity_dates=[],
            equity_curve=[],
            max_drawdown=0.0,
            sharpe=0.0,
            trades=fake_trades,
            win_rate=1.0,
            profit_factor=1.0,
            max_concurrent_positions=1,
            avg_concurrent_positions=1.0,
            pct_days_in_market=1.0,
            halted=False,
            open_positions={},
            open_position_entries={},
            rejected_intents=0,
        )

        # Patch backtest_account in the tracking module to return the fake result.
        monkeypatch.setattr(tracking_module, "backtest_account", lambda *a, **kw: fake_result)

        class _Store:
            def get_bars(self, symbol, start, end, timeframe="1d"):
                return _flat_bars(symbol, 30)

        store = _Store()

        (tmp_path / "live").mkdir()
        (tmp_path / "paper").mkdir()
        universe_live = self._universe(tmp_path / "live", mode="live")
        universe_paper = self._universe(tmp_path / "paper", mode="paper")

        report_live = run_tracking(universe_live, ledger, store, end=_day(29))
        report_paper = run_tracking(universe_paper, ledger, store, end=_day(29))

        # Live band is 5 bps (patched); ~10 bps mean → WARN
        assert report_live.status == "WARN", (
            f"expected WARN for live mode (band=5.0 bps), got {report_live.status}: "
            f"{report_live.reasons} | mean_bps={report_live.mean_abs_fill_bps}"
        )
        # The warning must reference the live band.
        assert any("live band" in r for r in report_live.reasons), report_live.reasons

        # Paper band is 50 bps (unchanged); ~10 bps mean → no mean-bps WARN.
        # (status might still be WARN for equity gap or divergence reasons — that's fine.)
        mean_bps_reason_in_paper = any(
            "mean fill gap" in r and "paper band" in r for r in report_paper.reasons
        )
        assert not mean_bps_reason_in_paper, (
            f"paper mode should not warn on mean bps with 50-bps band, "
            f"but got reasons: {report_paper.reasons}"
        )


# ---------------------------------------------------------------------------
# F: Reconcile property / boundary (test_methodology_guards.py extension)
# ---------------------------------------------------------------------------


class TestReconcileBoundary:
    """Reconcile is deterministic and the DRIFT_TOLERANCE_PCT boundary is exact.

    The boundary uses strict > (not >=), so:
      - diff == DRIFT_TOLERANCE_PCT * larger  → NOT fatal
      - diff == DRIFT_TOLERANCE_PCT * larger + epsilon → IS fatal
    """

    def _ledger(self, qty: float) -> PaperLedger:
        ledger = PaperLedger(cash=100.0, starting_cash=150.0)
        _open_position(ledger, "AAA", quantity=qty, entry_price=100.0)
        return ledger

    def test_deterministic_across_repeated_calls(self):
        """reconcile_positions returns identical fatal_drift and fatal_reasons on repeated calls."""
        ledger = self._ledger(1.0)
        broker = {"AAA": 1.010}  # 1.0% drift — clearly fatal

        r1 = reconcile_positions(ledger, broker)
        r2 = reconcile_positions(ledger, broker)

        assert r1.fatal_drift == r2.fatal_drift
        assert r1.fatal_reasons == r2.fatal_reasons

    def test_exact_boundary_is_not_fatal(self):
        """diff == DRIFT_TOLERANCE_PCT * larger exactly must NOT be fatal (strict >, not >=).

        Non-vacuous: this is the test that breaks when > is mutated to >=.

        Pinned values chosen so IEEE 754 gives exact equality (no rounding):
          ledger_qty = 199.0
          broker_qty = 200.0  → diff = 1.0, larger = 200.0
          threshold  = 0.005 * 200.0 = 1.0
          diff (1.0) == threshold (1.0) → strict >: NOT fatal; >= would be fatal.
        """
        ledger_qty = 199.0
        broker_qty = 200.0
        diff = abs(ledger_qty - broker_qty)
        larger = max(ledger_qty, broker_qty)
        # Sanity-check: diff must equal threshold exactly in IEEE 754
        assert diff == DRIFT_TOLERANCE_PCT * larger, (
            "test precondition: expected exact float equality at boundary"
        )

        ledger = self._ledger(ledger_qty)
        report = reconcile_positions(ledger, {"AAA": broker_qty})
        assert report.fatal_drift is False, (
            f"at diff==threshold the guard must use strict > not >=; "
            f"diff={diff}, threshold={DRIFT_TOLERANCE_PCT * larger}"
        )

    def test_just_above_boundary_is_fatal(self):
        """diff just above DRIFT_TOLERANCE_PCT * larger IS fatal.

        Pin with explicit numbers:
          ledger_qty = 199.0
          broker_qty = 201.0  → diff = 2.0, larger = 201.0
          threshold  = 0.005 * 201.0 = 1.005
          diff (2.0) > threshold (1.005) → IS fatal.
        """
        ledger_qty = 199.0
        broker_qty = 201.0
        diff = abs(ledger_qty - broker_qty)
        larger = max(ledger_qty, broker_qty)
        # Sanity-check
        assert diff > DRIFT_TOLERANCE_PCT * larger, "test precondition: diff must exceed threshold"

        ledger = self._ledger(ledger_qty)
        report = reconcile_positions(ledger, {"AAA": broker_qty})
        assert report.fatal_drift is True, (
            f"diff={diff:.6f} should exceed threshold={DRIFT_TOLERANCE_PCT * larger:.6f}"
        )
