"""Tests for paper-vs-replay tracking (bonito.trading.tracking)."""

import json
from datetime import datetime, timedelta

from bonito.data.models import BarData
from bonito.trading.live_runner import UniverseConfig
from bonito.trading.paper import PaperFill, PaperLedger
from bonito.trading.tracking import (
    FillComparison,
    match_fills,
    paper_equity_curve,
    run_tracking,
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


class TestMatchFills:
    def test_exact_match_measures_bps(self):
        paper = [fill("AAA", "buy", 100.10, day(1))]
        replay = [("AAA", "buy", day(1), 100.00)]
        out = match_fills(paper, replay)
        assert out[0].matched
        assert out[0].delta_bps == 10.0  # 0.10 on 100 = 10bps

    def test_match_within_tolerance_day(self):
        paper = [fill("AAA", "buy", 100.0, day(2))]
        replay = [("AAA", "buy", day(1), 100.0)]
        assert match_fills(paper, replay)[0].matched

    def test_no_match_beyond_tolerance(self):
        paper = [fill("AAA", "buy", 100.0, day(5))]
        replay = [("AAA", "buy", day(1), 100.0)]
        out = match_fills(paper, replay)
        assert not out[0].matched and out[0].replay_price is None

    def test_side_and_symbol_must_agree(self):
        paper = [fill("AAA", "sell", 100.0, day(1)), fill("BBB", "buy", 100.0, day(1))]
        replay = [("AAA", "buy", day(1), 100.0)]
        assert all(not c.matched for c in match_fills(paper, replay))

    def test_each_replay_event_consumed_once(self):
        # Two paper buys, one replay buy → exactly one match.
        paper = [fill("AAA", "buy", 100.0, day(1)), fill("AAA", "buy", 101.0, day(1))]
        replay = [("AAA", "buy", day(1), 100.0)]
        out = match_fills(paper, replay)
        assert sum(c.matched for c in out) == 1

    def test_round_trips_pair_in_date_order(self):
        paper = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("AAA", "buy", 110.0, day(5)),
        ]
        replay = [("AAA", "buy", day(5), 110.5), ("AAA", "buy", day(1), 100.2)]
        out = match_fills(paper, replay)
        assert [c.replay_price for c in out] == [100.2, 110.5]


class TestPaperEquityCurve:
    def universe(self, tmp_path) -> UniverseConfig:
        strategy = {
            "name": "s",
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
        path = tmp_path / "s.json"
        path.write_text(json.dumps(strategy))
        return UniverseConfig(
            name="t",
            symbols=["AAA"],
            strategy_path=str(path),
            data={"timeframe": "1d", "start_date": "2026-01-01"},
            risk={"starting_cash_usd": 1000.0},
        )

    def test_flat_round_trip_returns_to_cash(self, tmp_path):
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [
            fill("AAA", "buy", 100.0, day(1)),
            fill("AAA", "sell", 100.0, day(3)),
        ]
        store = FakeStore({"AAA": flat_bars("AAA", 6)})

        dates, equity = paper_equity_curve(ledger, store, self.universe(tmp_path), day(5))

        assert dates[0] == day(1)
        # Holding at flat prices: equity stays at starting cash throughout.
        assert all(abs(e - 1000.0) < 1e-6 for e in equity)

    def test_mark_to_market_uses_stored_closes(self, tmp_path):
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [fill("AAA", "buy", 100.0, day(1))]
        rising = flat_bars("AAA", 4)
        rising.closes = [100.0, 100.0, 120.0, 120.0]
        store = FakeStore({"AAA": rising})

        _, equity = paper_equity_curve(ledger, store, self.universe(tmp_path), day(3))

        assert equity[-1] == 1020.0  # 900 cash + 1 share at 120

    def test_empty_ledger(self, tmp_path):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        dates, equity = paper_equity_curve(
            ledger, FakeStore({}), self.universe(tmp_path), day(3)
        )
        assert dates == [] and equity == []


class TestRunTracking:
    def universe(self, tmp_path) -> UniverseConfig:
        # Strategy that never enters in the replay — paper fills then become
        # decision divergences, exercising the unmatched path end to end.
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

    def test_no_fills_is_insufficient(self, tmp_path):
        ledger = PaperLedger(cash=1000.0, starting_cash=1000.0)
        report = run_tracking(self.universe(tmp_path), ledger, FakeStore({}), end=day(5))
        assert report.status == "INSUFFICIENT"
        assert report.paper_fills == 0

    def test_divergent_fills_reported(self, tmp_path):
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [fill("AAA", "buy", 100.0, day(2))]
        store = FakeStore({"AAA": flat_bars("AAA", 6)})

        report = run_tracking(self.universe(tmp_path), ledger, store, end=day(5))

        # 1 paper fill, replay never trades → 100% divergence, too few
        # matches to judge — INSUFFICIENT, not WARN.
        assert report.status == "INSUFFICIENT"
        assert report.paper_fills == 1 and report.matched_fills == 0
        assert report.decision_divergence == 1.0
        assert not report.fills[0].matched

    def test_report_serializes(self, tmp_path):
        ledger = PaperLedger(cash=900.0, starting_cash=1000.0)
        ledger.fills = [fill("AAA", "buy", 100.0, day(2))]
        store = FakeStore({"AAA": flat_bars("AAA", 6)})
        report = run_tracking(self.universe(tmp_path), ledger, store, end=day(5))
        parsed = json.loads(report.model_dump_json())
        assert parsed["status"] == "INSUFFICIENT"
        assert isinstance(parsed["fills"], list)


class TestThresholds:
    def test_fill_comparison_model_roundtrip(self):
        c = FillComparison(
            symbol="AAA",
            side="buy",
            paper_date=day(1),
            paper_price=100.0,
            replay_price=99.9,
            delta_bps=10.0,
            matched=True,
        )
        assert FillComparison(**json.loads(c.model_dump_json())) == c
