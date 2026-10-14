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


# --- regression + guard tests added after the pre-run review (see commit message) ---


def seg(points, n=None):
    n = len(DAYS) if n is None else n
    x = np.arange(n)
    return np.interp(x, [p[0] for p in points], [p[1] for p in points])


def test_missing_bar_on_reentry_never_fills_at_a_stale_price():
    """BLOCKER regression: A is held early (~130), sold, then drifts to 250 unheld
    and is re-selected. With A's execution-day bar missing, the engine used to "buy"
    A at its OLD last price and book the jump as profit (79.6k → 180.3k in the probe).
    Now A is skipped that week; the result stays close to the control run."""
    a = seg([(0, 100), (60, 130), (80, 100), (300, 250), (len(DAYS), 260)])
    c = seg([(0, 100), (80, 100), (300, 1000), (340, 300), (len(DAYS), 300)])
    closes = frame({"A": a, "C": c, "QQQ": seg([(0, 100), (len(DAYS), 300)])})
    k = cfg(lookback_months=2, skip_months=0, min_history_days=30)
    pool = PointInTimePool({date(2019, 1, 1): {"A", "C"}})
    span = (date(2020, 3, 2), date(2021, 12, 31))
    control = run_rotation(k, pool, closes, closes, *span)
    reentry = [d for d, h in control.holdings.items() if h == ["A"] and d > DAYS[300].date()]
    ex = DAYS[DAYS.get_loc(pd.Timestamp(reentry[0])) + 1]
    gapped = closes.copy()
    gapped.loc[ex, "A"] = np.nan
    r = run_rotation(k, pool, gapped, gapped, *span)
    assert r.equity[-1] <= control.equity[-1] * 1.02


def test_signal_buys_at_next_open_and_marks_from_there():
    """Pins next-OPEN execution: Monday's open and close differ, so filling at the
    close (or not trading at all) gives a different equity path."""
    a = growth(0.002)
    o = a.copy()
    fri = DAYS.get_indexer([pd.Timestamp("2021-06-04")])[0]
    o[fri + 1] = a[fri] * 1.10  # Monday opens +10%...
    a[fri + 1] = a[fri] * 1.20  # ...and closes +20%
    closes, opens = frame({"A": a, **market()}), frame({"A": o, **market()})
    start = pd.Timestamp("2021-06-04").date()
    r = run_rotation(
        cfg(),
        PointInTimePool({date(2019, 1, 1): {"A"}}),
        opens,
        closes,
        start,
        pd.Timestamp("2021-06-09").date(),
        starting_cash=1000.0,
    )
    assert r.holdings[start] == ["A"]
    assert r.equity[0] == pytest.approx(1000.0)  # Friday: decided, not yet traded
    assert r.equity[1] == pytest.approx(1000.0 * 1.20 / 1.10)  # bought at open, marked at close


def test_scores_are_invariant_to_future_data():
    """No look-ahead: appending a wildly different future must not change scores."""
    rng = np.random.default_rng(1)
    cols = {s: 100 * np.cumprod(1 + rng.normal(0, 0.02, len(DAYS))) for s in "ABCD"}
    closes = frame({**cols, **market()})
    on = DAYS[300]
    future = closes.copy()
    future.loc[on < DAYS, list("ABCD")] *= rng.uniform(0.1, 10, size=(int((on < DAYS).sum()), 4))
    k = cfg()
    assert momentum_scores(closes.loc[:on], on, set("ABCD"), k) == momentum_scores(
        future, on, set("ABCD"), k
    )


def test_stale_far_anchor_excludes_symbol():
    """A symbol whose last price before the lookback anchor is weeks old (a long
    data gap) is not scored on that stale price."""
    c = growth(0.002)
    on = DAYS[-1]
    anchor = on - pd.DateOffset(months=6)
    c[(anchor - pd.Timedelta(days=40) < DAYS) & (anchor + pd.Timedelta(days=5) >= DAYS)] = np.nan
    closes = frame({"GAP": c, "OK": growth(0.001), **market()})
    s = momentum_scores(closes, on, {"GAP", "OK"}, cfg())
    assert "GAP" not in s and "OK" in s


def test_trend_exit_executes_next_open_and_reenters():
    q = growth(0.002)
    down = (pd.Timestamp("2021-03-01") <= DAYS) & (pd.Timestamp("2021-06-01") > DAYS)
    q[down] = q[down][0] * 0.5  # QQQ well below its SMA for three months
    closes = frame({"A": growth(0.002), "QQQ": q})
    r = run_rotation(
        cfg(),
        PointInTimePool({date(2019, 1, 1): {"A"}}),
        closes,
        closes,
        date(2021, 1, 4),
        date(2021, 12, 31),
    )
    cash_weeks = [d for d, h in r.holdings.items() if h == []]
    assert cash_weeks and min(cash_weeks) >= date(2021, 3, 1)
    assert any(h == ["A"] for d, h in r.holdings.items() if d > max(cash_weeks))  # re-entered


def test_config_rejects_lookback_not_exceeding_skip():
    with pytest.raises(ValueError):
        RotationConfig(name="bad", lookback_months=1, skip_months=1)


def test_sessions_come_from_trend_symbol_not_stray_rows():
    """A stray Saturday row for one symbol (QQQ NaN) must not become a session /
    signal day that forces a spurious cash week."""
    closes = frame({"A": growth(0.002), **market()})
    sat = pd.Timestamp("2021-06-05")  # a Saturday
    stray = pd.DataFrame({"A": [closes["A"].iloc[-1]], "QQQ": [np.nan]}, index=[sat])
    closes2 = pd.concat([closes, stray]).sort_index()
    pool = PointInTimePool({date(2019, 1, 1): {"A"}})
    r = run_rotation(cfg(), pool, closes2, closes2, date(2021, 1, 4), date(2021, 12, 31))
    assert sat.date() not in r.dates
    assert r.weeks_in_cash == 0


def test_symbol_without_signal_day_close_is_not_scored_from_future_rows():
    """NaN on the signal date (but bars later) must be excluded, not read ahead."""
    c = growth(0.003)
    on = DAYS[300]
    c[300] = np.nan
    closes = frame({"HALT": c, "OK": growth(0.001), **market()})
    s = momentum_scores(closes, on, {"HALT", "OK"}, cfg())
    assert "HALT" not in s and "OK" in s
