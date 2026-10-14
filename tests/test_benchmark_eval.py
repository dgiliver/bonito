"""Tests for the market-relative research harness (bonito.research.benchmark_eval)."""

import json
from datetime import date, datetime, timedelta

import pytest

from bonito.data.models import BarData
from bonito.research.benchmark_eval import (
    CurveStats,
    WindowEval,
    curve_stats,
    evaluate_vs_benchmarks,
    judge,
)
from bonito.trading.live_runner import UniverseConfig

START = datetime(2024, 1, 1, 5)


def day(i: int) -> datetime:
    return START + timedelta(days=i)


class TestCurveStats:
    def test_doubling_over_one_year(self):
        d0 = date(2024, 1, 1)
        dates = [d0, date(2024, 7, 1), date(2025, 1, 1)]
        st = curve_stats(dates, [100.0, 150.0, 200.0])
        assert st.total_return_pct == pytest.approx(100.0)
        assert st.cagr_pct == pytest.approx(100.0, abs=0.3)  # 366-day year
        assert st.max_drawdown_pct == 0.0

    def test_max_drawdown_from_running_peak(self):
        dates = [date(2024, 1, d) for d in range(1, 6)]
        st = curve_stats(dates, [100.0, 120.0, 90.0, 110.0, 130.0])
        assert st.max_drawdown_pct == pytest.approx(25.0)  # 120 → 90

    def test_too_short_is_none(self):
        assert curve_stats([date(2024, 1, 1)], [1.0]) is None


def stats(cagr, sharpe=1.0, dd=20.0) -> CurveStats:
    return CurveStats(total_return_pct=0.0, cagr_pct=cagr, sharpe=sharpe, max_drawdown_pct=dd)


def window(strat: CurveStats | None, qqq: CurveStats | None, label="full") -> WindowEval:
    return WindowEval(
        label=label,
        start=date(2024, 1, 1),
        end=date(2025, 1, 1),
        strategy=strat,
        benchmarks={"QQQ": qqq},
    )


class TestJudge:
    def test_beats_only_when_every_check_passes(self):
        good = window(stats(25, 1.2, 20), stats(20, 1.0, 30))
        checks, verdict = judge(
            good, window(stats(15, 0.9), stats(10, 0.7)), window(stats(21), stats(20)), "QQQ"
        )
        assert verdict == "BEATS" and all(checks.values())

    @pytest.mark.parametrize(
        "full, sub, ex_top, failing",
        [
            (window(stats(19, 1.2, 20), stats(20, 1.0, 30)), None, None, "full_cagr"),
            (window(stats(25, 0.9, 20), stats(20, 1.0, 30)), None, None, "full_sharpe"),
            # 38 > 1.25 × 30 = 37.5 → fails the drawdown allowance
            (window(stats(25, 1.2, 38), stats(20, 1.0, 30)), None, None, "full_dd"),
            (
                window(stats(25, 1.2, 20), stats(20, 1.0, 30)),
                window(stats(9, 0.9), stats(10, 0.7)),
                None,
                "sub_cagr",
            ),
            (
                window(stats(25, 1.2, 20), stats(20, 1.0, 30)),
                None,
                window(stats(19), stats(20)),
                "ex_top_cagr",
            ),
        ],
    )
    def test_each_failed_check_blocks(self, full, sub, ex_top, failing):
        checks, verdict = judge(full, sub, ex_top, "QQQ")
        assert verdict == "DOES_NOT_BEAT"
        assert checks[failing] is False

    def test_a_partial_run_can_never_pass(self):
        """Review finding: with the sub-window skipped (default --start after
        --sub-start) the verdict printed BEATS on 4 of 6 checks."""
        full = window(stats(25, 1.2, 20), stats(20, 1.0, 30))
        ex = window(stats(21), stats(20))
        checks, verdict = judge(full, None, ex, "QQQ")
        assert verdict == "INCONCLUSIVE"
        assert checks["sub_cagr"] is None and checks["sub_sharpe"] is None
        checks, verdict = judge(full, window(stats(15, 0.9), stats(10, 0.7)), None, "QQQ")
        assert verdict == "INCONCLUSIVE" and checks["ex_top_cagr"] is None

    def test_a_definite_failure_beats_missing_data(self):
        checks, verdict = judge(window(stats(19, 1.2, 20), stats(20, 1.0, 30)), None, None, "QQQ")
        assert verdict == "DOES_NOT_BEAT"

    def test_missing_benchmark_is_inconclusive_not_a_pass(self):
        checks, verdict = judge(window(stats(25), None), None, None, "QQQ")
        assert verdict == "INCONCLUSIVE" and checks["full_cagr"] is None


# --- integration: a tiny universe through the real account replay -------------------


def ohlc(symbol: str, closes: list[float]) -> BarData:
    n = len(closes)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[day(i) for i in range(n)],
        opens=closes,
        highs=[c * 1.001 for c in closes],
        lows=[c * 0.999 for c in closes],
        closes=closes,
        volumes=[1e6] * n,
    )


class FakeStore:
    def __init__(self, data):
        self.data = data

    def get_bars(self, symbol, start, end, timeframe="1d"):
        b = self.data.get(symbol)
        if b is None:
            return None
        keep = [i for i, t in enumerate(b.timestamps) if start <= t <= end]
        if not keep:
            return None
        return BarData(
            symbol=symbol,
            timeframe="1d",
            timestamps=[b.timestamps[i] for i in keep],
            opens=[b.opens[i] for i in keep],
            highs=[b.highs[i] for i in keep],
            lows=[b.lows[i] for i in keep],
            closes=[b.closes[i] for i in keep],
            volumes=[b.volumes[i] for i in keep],
        )


@pytest.fixture
def universe(tmp_path):
    strategy = {
        "name": "always",
        "symbols": ["AAA"],
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
    }
    p = tmp_path / "s.json"
    p.write_text(json.dumps(strategy))
    return UniverseConfig(
        name="tiny",
        symbols=["AAA", "BBB", "CCC"],
        strategy_path=str(p),
        data={"timeframe": "1d", "start_date": "2024-01-01"},
        risk={"starting_cash_usd": 1000.0, "max_positions": 3, "max_drawdown_halt": 0.01},
    )


def test_end_to_end_report_with_kill_switch_off_by_default(universe):
    n = 60
    store = FakeStore(
        {
            "AAA": ohlc("AAA", [100 * 1.01**i for i in range(n)]),  # big winner
            "BBB": ohlc("BBB", [100 * 1.002**i for i in range(n)]),
            "CCC": ohlc(
                "CCC", [100 * (0.97 if 10 < i < 20 else 1.0) ** min(i, 20) for i in range(n)]
            ),
            "SPY": ohlc("SPY", [100 * 1.001**i for i in range(n)]),
            "QQQ": ohlc("QQQ", [100 * 1.0015**i for i in range(n)]),
        }
    )
    report = evaluate_vs_benchmarks(
        universe, store, day(5), day(n - 1), sub_start=day(30), exclude_top=1
    )
    assert report.kill_switch is False
    assert [w.label for w in report.windows] == ["full", "sub"]
    assert report.excluded_top == ["AAA"]  # the top P&L contributor
    assert report.ex_top is not None and "AAA" not in report.ex_top.per_symbol_pnl
    assert set(report.windows[0].benchmarks) >= {"SPY", "QQQ", "hold-universe"}
    assert report.verdict in {"BEATS", "DOES_NOT_BEAT"}
    assert report.yearly  # calendar-year table populated


def test_kill_switch_override_is_what_keeps_the_replay_trading(universe):
    """Every symbol drops 20% mid-window: with the universe's 1% halt honoured the
    replay latches; the default (kill switch off) must not."""
    n = 40
    path = [100.0] * 15 + [80.0] * 5 + [100.0 + i for i in range(n - 20)]
    store = FakeStore({s: ohlc(s, path) for s in ("AAA", "BBB", "CCC", "SPY", "QQQ")})
    off = evaluate_vs_benchmarks(universe, store, day(5), day(n - 1), sub_start=None, exclude_top=0)
    on = evaluate_vs_benchmarks(
        universe, store, day(5), day(n - 1), sub_start=None, exclude_top=0, kill_switch=True
    )
    assert on.windows[0].halted is True
    assert off.windows[0].halted is False


def test_drawdown_allowance_is_1_25x_the_benchmark():
    """User decision 2026-10-14: 'higher return, similar risk' = DD ≤ 1.25× QQQ."""
    ok = window(stats(25, 1.2, 37.5), stats(20, 1.0, 30))
    bad = window(stats(25, 1.2, 37.6), stats(20, 1.0, 30))
    assert judge(ok, None, None, "QQQ")[0]["full_dd"] is True
    assert judge(bad, None, None, "QQQ")[0]["full_dd"] is False
