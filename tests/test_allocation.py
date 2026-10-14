"""Tests for the target-weight allocation simulator and trend-leverage family."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from bonito.research.allocation import VARIANTS, run_allocation, trend_decider

DAYS = pd.bdate_range("2020-01-01", "2021-12-31")


def growth(rate: float) -> np.ndarray:
    return 100.0 * (1 + rate) ** np.arange(len(DAYS))


def frame(d: dict) -> pd.DataFrame:
    return pd.DataFrame(d, index=DAYS)


def const(w):
    return lambda day: dict(w)


def test_buys_at_next_open_and_marks_at_close():
    q = growth(0.001)
    o = q.copy()
    fri = DAYS.get_indexer([pd.Timestamp("2021-06-04")])[0]
    o[fri + 1] = q[fri] * 1.10
    q[fri + 1] = q[fri] * 1.20
    closes, opens = frame({"QQQ": q}), frame({"QQQ": o})
    r = run_allocation(
        "t",
        const({"QQQ": 1.0}),
        opens,
        closes,
        date(2021, 6, 4),
        date(2021, 6, 8),
        cost_bps=0,
        starting_cash=1000.0,
    )
    assert r.equity[0] == pytest.approx(1000.0)  # Friday: decided only
    assert r.equity[1] == pytest.approx(1000.0 * 1.20 / 1.10)  # filled at Monday OPEN


def test_weights_split_and_cash_remainder():
    closes = frame({"QQQ": growth(0.0), "QLD": growth(0.0)})
    r = run_allocation(
        "t",
        const({"QQQ": 0.5, "QLD": 0.25}),
        closes,
        closes,
        date(2021, 1, 4),
        date(2021, 2, 26),
        cost_bps=0,
        starting_cash=1000.0,
    )
    assert r.equity[-1] == pytest.approx(1000.0)  # flat prices, no costs
    closes2 = closes.copy()
    closes2["QLD"] = growth(0.002)  # only QLD moves
    r2 = run_allocation(
        "t",
        const({"QQQ": 0.5, "QLD": 0.25}),
        closes2,
        closes2,
        date(2021, 1, 4),
        date(2021, 1, 15),
        cost_bps=0,
        starting_cash=1000.0,
    )
    # P&L comes only from the 25% QLD sleeve
    assert 1000 < r2.equity[-1] < 1000 * (1 + 0.25 * 0.05)


def test_costs_charged_on_turnover():
    closes = frame({"QQQ": growth(0.001), "QLD": growth(0.002)})
    flip = lambda day: {"QLD": 1.0} if day.isocalendar()[1] % 2 else {"QQQ": 1.0}  # noqa: E731
    free = run_allocation(
        "t", flip, closes, closes, date(2021, 1, 4), date(2021, 12, 31), cost_bps=0
    )
    paid = run_allocation(
        "t", flip, closes, closes, date(2021, 1, 4), date(2021, 12, 31), cost_bps=50
    )
    assert paid.equity[-1] < free.equity[-1] and paid.turnover > 20


def test_weights_over_one_rejected():
    closes = frame({"QQQ": growth(0.0)})
    with pytest.raises(ValueError):
        run_allocation("t", const({"QQQ": 1.5}), closes, closes, date(2021, 1, 4), date(2021, 2, 1))


def test_new_symbol_without_open_is_not_filled_at_stale_price():
    """QLD held early, sold, re-bought later; its re-entry open is missing. Must not
    be filled at the old held price (the rotation engine's BLOCKER, mirrored)."""
    qld = np.concatenate([np.full(60, 100.0), np.linspace(100, 300, len(DAYS) - 60)])
    closes = frame({"QQQ": growth(0.0), "QLD": qld})

    def decide(day):
        return (
            {"QLD": 1.0}
            if day < pd.Timestamp("2020-02-15") or day > pd.Timestamp("2021-06-01")
            else {}
        )

    control = run_allocation(
        "t", decide, closes, closes, date(2020, 1, 3), date(2021, 12, 31), cost_bps=0
    )
    reentry = min(d for d, w in control.targets.items() if w and d > date(2021, 6, 1))
    ex = DAYS[DAYS.get_loc(pd.Timestamp(reentry)) + 1]
    gapped = closes.copy()
    gapped.loc[ex, "QLD"] = np.nan
    r = run_allocation(
        "t", decide, gapped, gapped, date(2020, 1, 3), date(2021, 12, 31), cost_bps=0
    )
    assert r.equity[-1] <= control.equity[-1] * 1.02


class TestTrendDecider:
    def test_switches_on_sma_and_uses_only_past_data(self):
        q = growth(0.002)
        q[pd.Timestamp("2021-06-01") <= DAYS] = 50.0  # crash below SMA
        closes = frame({"QQQ": q})
        d = trend_decider(closes, "L2-CASH", sma_period=50)
        assert d(pd.Timestamp("2021-05-28")) == {"QLD": 1.0}
        assert d(pd.Timestamp("2021-06-04")) == {}
        # appending a wildly different future can't change a past decision
        fut = closes.copy()
        fut.loc[fut.index > pd.Timestamp("2021-05-28"), "QQQ"] = 1e6
        assert trend_decider(fut, "L2-CASH", sma_period=50)(pd.Timestamp("2021-05-28")) == {
            "QLD": 1.0
        }

    def test_undefined_sma_is_defensive(self):
        closes = frame({"QQQ": growth(0.002)})
        assert trend_decider(closes, "L2-QQQ", sma_period=10_000)(DAYS[-1]) == {"QQQ": 1.0}

    def test_variants_are_the_preregistered_four(self):
        assert VARIANTS == {
            "L2-QQQ": ({"QLD": 1.0}, {"QQQ": 1.0}),
            "L2-CASH": ({"QLD": 1.0}, {}),
            "L15-CASH": ({"QLD": 0.5, "QQQ": 0.5}, {}),
            "L3-CASH": ({"TQQQ": 1.0}, {}),
        }


def test_end_to_end_l2_cash_goes_flat_in_downtrend():
    q = growth(0.002)
    q[pd.Timestamp("2021-03-01") <= DAYS] = q[pd.Timestamp("2021-03-01") <= DAYS][0] * 0.6
    closes = frame({"QQQ": q, "QLD": growth(0.004)})
    r = run_allocation(
        "L2-CASH",
        trend_decider(closes, "L2-CASH", sma_period=20),
        closes,
        closes,
        date(2020, 6, 1),
        date(2021, 12, 31),
        cost_bps=0,
    )
    i = r.dates.index(date(2021, 3, 15))
    assert np.allclose(r.equity[i:], r.equity[i])  # in cash once the trend broke


# --- exact-arithmetic pins (added after the pre-run review) ---


def test_fee_is_exactly_cost_bps_of_traded_notional():
    """Flat prices, one 100% buy at 10 bps: equity = 1000 × (1 − 0.001)."""
    closes = frame({"QQQ": np.full(len(DAYS), 100.0)})
    r = run_allocation(
        "t",
        const({"QQQ": 1.0}),
        closes,
        closes,
        date(2021, 1, 4),
        date(2021, 1, 12),
        cost_bps=10,
        starting_cash=1000.0,
    )
    # Fri 01-08 decides, Mon 01-11 buys; a second identical target re-trades nothing.
    assert r.equity[-1] == pytest.approx(1000.0 * (1 - 0.001))


def test_fee_counts_both_legs_of_a_switch():
    closes = frame({"QQQ": np.full(len(DAYS), 100.0), "QLD": np.full(len(DAYS), 100.0)})

    def flip(day):
        return {"QQQ": 1.0} if day < pd.Timestamp("2021-01-11") else {"QLD": 1.0}

    r = run_allocation(
        "t",
        flip,
        closes,
        closes,
        date(2021, 1, 4),
        date(2021, 1, 19),
        cost_bps=10,
        starting_cash=1000.0,
    )
    # buy 1000 (fee 1.0) → 999; switch: sell 1000 + buy 999 → fee 1.999 → 997.001
    assert r.equity[-1] == pytest.approx(997.001)


def test_default_cost_is_the_preregistered_10bps():
    import inspect

    assert inspect.signature(run_allocation).parameters["cost_bps"].default == 10.0


def test_weights_apply_exactly_per_leg():
    q = np.full(len(DAYS), 100.0)
    l2 = np.full(len(DAYS), 100.0)
    i = DAYS.get_indexer([pd.Timestamp("2021-01-12")])[0]
    q[i:] = 101.0  # QQQ +1% on 01-12
    l2[i:] = 102.0  # QLD +2% on 01-12
    closes = frame({"QQQ": q, "QLD": l2})
    r = run_allocation(
        "t",
        const({"QQQ": 0.5, "QLD": 0.25}),
        closes,
        closes,
        date(2021, 1, 4),
        date(2021, 1, 12),
        cost_bps=0,
        starting_cash=1000.0,
    )
    assert r.equity[-1] == pytest.approx(1000.0 * (1 + 0.5 * 0.01 + 0.25 * 0.02))
