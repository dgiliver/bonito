"""The trend-leverage runner must judge strategy and QQQ on identical footing."""

import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bonito.research.allocation import run_allocation

SPEC = importlib.util.spec_from_file_location(
    "tl", Path("scripts/experiments/2026-10-14b_trend_leverage_search.py")
)
tl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tl)

DAYS = pd.bdate_range("2020-01-01", "2021-12-31")


def market_with_early_drop() -> pd.DataFrame:
    q = 100 * 1.001 ** np.arange(len(DAYS))
    early = (pd.Timestamp("2021-01-04") <= DAYS) & (pd.Timestamp("2021-01-08") >= DAYS)
    q[early] *= 0.9  # a first-week drop: the old benchmark took it, the strategy didn't
    return pd.DataFrame({"QQQ": q}, index=DAYS)


def test_benchmark_has_same_entry_as_strategy():
    """A strategy that just holds QQQ must tie the benchmark exactly — no head start."""
    c = market_with_early_drop()
    window = (date(2021, 1, 4), date(2021, 12, 31))
    hold = run_allocation("hold", lambda d: {"QQQ": 1.0}, c, c, *window, cost_bps=tl.COST_BPS)
    ev = tl.evaluate(hold, tl.benchmark(window, c, c))
    assert ev["strategy"] == ev["QQQ"]
    assert ev["checks"]["cagr"] is False and ev["checks"]["sharpe"] is False  # a tie never passes


def test_mismatched_sessions_refused():
    c = market_with_early_drop()
    a = tl.benchmark((date(2021, 1, 4), date(2021, 12, 31)), c, c)
    b = tl.benchmark((date(2021, 2, 1), date(2021, 12, 31)), c, c)
    with pytest.raises(ValueError):
        tl.evaluate(a, b)


def test_runner_passes_costs_explicitly():
    assert tl.COST_BPS == 10.0
    src = Path("scripts/experiments/2026-10-14b_trend_leverage_search.py").read_text()
    assert src.count("cost_bps=COST_BPS") == 2  # variants AND benchmark
