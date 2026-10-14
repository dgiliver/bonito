"""Tests for the weekly momentum rotation (bonito.research.rotation)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from bonito.research.rotation import (
    PointInTimePool,
    RotationConfig,
    momentum_scores,
    run_rotation,
)

DAYS = pd.bdate_range("2020-01-01", "2021-12-31")  # weekdays; ISO weeks end on Friday


def frame(series: dict[str, np.ndarray]) -> pd.DataFrame:
    return pd.DataFrame(series, index=DAYS)


def growth(rate: float, n: int = len(DAYS), base: float = 100.0) -> np.ndarray:
    return base * (1 + rate) ** np.arange(n)


def cfg(**kw) -> RotationConfig:
    base = {
        "name": "t",
        "lookback_months": 6,
        "skip_months": 1,
        "top_n": 1,
        "trend_sma": 20,
        "cost_bps": 0.0,
        "min_history_days": 60,
    }
    base.update(kw)
    return RotationConfig(**base)


def market(trend_rate: float = 0.001) -> dict[str, np.ndarray]:
    return {"QQQ": growth(trend_rate)}


class TestPointInTimePool:
    def test_snapshot_and_additions_by_date(self):
        pool = PointInTimePool(
            {date(2020, 1, 1): {"A", "B"}, date(2021, 1, 1): {"A", "C"}},
            additions={"X": date(2020, 6, 1)},
        )
        assert pool.members(date(2019, 12, 31)) == set()  # before any snapshot, before X
        assert pool.members(date(2020, 3, 1)) == {"A", "B"}
        assert pool.members(date(2020, 6, 1)) == {"A", "B", "X"}
        assert pool.members(date(2021, 2, 1)) == {"A", "C", "X"}  # B left, C joined
        assert pool.all_symbols() == {"A", "B", "C", "X"}


class TestMomentumScores:
    def test_ranks_by_lookback_to_skip_return(self):
        closes = frame({"FAST": growth(0.003), "SLOW": growth(0.001), **market()})
        on = DAYS[-1]
        s = momentum_scores(closes, on, {"FAST", "SLOW"}, cfg())
        assert s["FAST"] > s["SLOW"] > 0

    def test_skip_month_ignores_the_latest_move(self):
        c = growth(0.0)
        c[-15:] = 1000.0  # huge jump inside the skipped last month
        closes = frame({"JUMP": c, **market()})
        assert momentum_scores(closes, DAYS[-1], {"JUMP"}, cfg())["JUMP"] == pytest.approx(0.0)

    def test_insufficient_history_excluded(self):
        c = growth(0.002)
        c[:-40] = np.nan  # only 40 sessions of history
        closes = frame({"NEW": c, **market()})
        assert momentum_scores(closes, DAYS[-1], {"NEW"}, cfg()) == {}


class TestRunRotation:
    def test_executes_next_open_no_lookahead(self):
        """A stock that gaps up at Monday's open must be BOUGHT at that open,
        never credited with the gap it was selected before."""
        a = growth(0.002)
        o = a.copy()
        fri = DAYS.get_indexer([pd.Timestamp("2021-06-04")])[0]  # a Friday
        o[fri + 1] = a[fri] * 1.5  # Monday open gaps +50%...
        a[fri + 1 :] = a[fri] * 1.5  # ...and stays there
        closes = frame({"A": a, **market()})
        opens = frame({"A": o, **market()})
        start = pd.Timestamp("2021-06-04").date()  # first signal is this Friday
        r = run_rotation(
            cfg(),
            PointInTimePool({date(2019, 1, 1): {"A"}}),
            opens,
            closes,
            start,
            pd.Timestamp("2021-06-08").date(),
            starting_cash=1000.0,
        )
        # Bought at Monday's gapped open → no gain from the gap itself.
        assert r.equity[1] == pytest.approx(1000.0, rel=1e-9)

    def test_only_pool_members_are_held(self):
        closes = frame({"IN": growth(0.001), "OUT": growth(0.004), **market()})
        pool = PointInTimePool({date(2019, 1, 1): {"IN"}})
        r = run_rotation(cfg(), pool, closes, closes, date(2021, 1, 4), date(2021, 12, 31))
        held = {s for v in r.holdings.values() for s in v}
        assert held == {"IN"}

    def test_addition_date_is_respected(self):
        closes = frame({"OLD": growth(0.001), "ADD": growth(0.004), **market()})
        pool = PointInTimePool({date(2019, 1, 1): {"OLD"}}, additions={"ADD": date(2021, 6, 1)})
        r = run_rotation(cfg(), pool, closes, closes, date(2021, 1, 4), date(2021, 12, 31))
        for d, held in r.holdings.items():
            if d < date(2021, 6, 1):
                assert "ADD" not in held
        assert any("ADD" in h for h in r.holdings.values())

    def test_trend_exit_goes_to_cash(self):
        q = growth(0.002)
        q[pd.Timestamp("2021-06-01") <= DAYS] = 50.0  # QQQ collapses below its SMA
        closes = frame({"A": growth(0.002), "QQQ": q})
        r = run_rotation(
            cfg(),
            PointInTimePool({date(2019, 1, 1): {"A"}}),
            closes,
            closes,
            date(2021, 1, 4),
            date(2021, 12, 31),
        )
        after = [d for d in r.holdings if d >= date(2021, 6, 8)]
        assert after and all(r.holdings[d] == [] for d in after)
        i = r.dates.index(date(2021, 6, 15))
        assert np.allclose(r.equity[i:], r.equity[i])  # flat in cash
        assert r.weeks_in_cash > 0

    def test_costs_are_charged(self):
        closes = frame({"A": growth(0.002), "B": growth(0.0021), **market()})
        pool = PointInTimePool({date(2019, 1, 1): {"A", "B"}})
        free = run_rotation(
            cfg(top_n=2), pool, closes, closes, date(2021, 1, 4), date(2021, 12, 31)
        )
        paid = run_rotation(
            cfg(top_n=2, cost_bps=50), pool, closes, closes, date(2021, 1, 4), date(2021, 12, 31)
        )
        assert paid.equity[-1] < free.equity[-1]
        assert paid.turnover > 0

    def test_attribution_sums_to_pnl(self):
        rng = np.random.default_rng(0)
        cols = {s: 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, len(DAYS))) for s in "ABCDE"}
        closes = frame({**cols, **market()})
        opens = closes * (1 + rng.normal(0, 0.003, closes.shape))
        pool = PointInTimePool({date(2019, 1, 1): set("ABCDE")})
        r = run_rotation(
            cfg(top_n=2, cost_bps=10),
            pool,
            opens,
            closes,
            date(2020, 9, 1),
            date(2021, 12, 31),
            starting_cash=10_000.0,
        )
        assert sum(r.per_symbol_pnl.values()) == pytest.approx(r.equity[-1] - 10_000.0, abs=0.5)

    def test_exclude_removes_symbols(self):
        closes = frame({"TOP": growth(0.004), "NEXT": growth(0.002), **market()})
        pool = PointInTimePool({date(2019, 1, 1): {"TOP", "NEXT"}})
        r = run_rotation(
            cfg(),
            pool,
            closes,
            closes,
            date(2021, 1, 4),
            date(2021, 12, 31),
            exclude=frozenset({"TOP"}),
        )
        assert {s for v in r.holdings.values() for s in v} == {"NEXT"}
