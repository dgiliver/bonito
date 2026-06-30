"""Permanent regression tests proving the backtest engine has no look-ahead.

Lifted from the Q2 audit-followup scratch probe
(`scratchpad/q2/lookahead_probe.py`, Builder-verified 0-divergence pass) into
a deterministic, synthetic-only suite that runs under `make test-fast`.

Four invariants, each targeting a distinct leak surface:

  A. Future-truncation invariance — re-running on a series truncated right
     after a decision-execution bar reproduces that exact trade.
  B. Future-scramble invariance — replacing all bars after a split point
     with unrelated noise never changes any ENTRY decided at-or-before that
     point, nor any (non-end-of-data) EXIT decided at-or-before that point.
     Entries and exits are independent decision points, each checked only
     against the fields its own decision determines — see the docstring on
     `test_b_future_scramble_invariance` for why.
  B-regime. Gated-regime scramble — targets the regime-mask `searchsorted`
     direction specifically: scrambling regime bars after split point m must
     not flip any entry signal at-or-before m.
  C. Stop/TP same-bar honesty — a stop that fires on bar i's own close is
     unaffected by anything that happens on bar i+1.
  D. Indicator forward-window check — SMA/EMA/RSI/ATR/MACD at index i is
     identical whether computed on the full series or on series[:i+1]
     (restricted to indices that are non-NaN in both runs).

A price/return shuffle is explicitly NOT used as a leak proof (it destroys
indicator semantics — shuffled prices produce garbage SMA/EMA/RSI values, so
"no divergence" would prove nothing about look-ahead). Tests A/B/B-regime/C
exercise the SIMULATION timing (signal-then-fill ordering); they do not by
themselves catch a forward-looking INDICATOR — that failure class is covered
separately by Test D.

All series here are small, hand-built, or `numpy.random.default_rng(seed)`
synthetic data. No DuckDB, no network, no `MarketDataStore` — safe for
`pytest -m "not slow"`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.indicators import compute_indicators
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    IndicatorType,
    PositionSizeConfig,
    PositionSizeType,
    RegimeFilterConfig,
    Rule,
    RuleCondition,
    StopLossConfig,
    StopLossType,
    StrategyConfig,
    TakeProfitConfig,
    TakeProfitType,
)
from bonito.data.models import BarData

RTOL = 1e-12
ATOL = 1e-9
INDICATOR_RTOL = 1e-9

# ---------------------------------------------------------------------------
# Synthetic series + strategy fixtures
# ---------------------------------------------------------------------------


def make_synthetic_series(n: int, seed: int = 0, start_price: float = 100.0) -> BarData:
    """Deterministic OHLCV series with enough structure to trigger many
    EMA-cross entries, RSI gating, ATR trailing stops, and TP exits."""
    rng = np.random.default_rng(seed)
    base_date = datetime(2020, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]

    t = np.arange(n, dtype=float)
    trend = 0.05 * t
    cycle = 8.0 * np.sin(t / 9.0) + 4.0 * np.sin(t / 23.0 + 1.0)
    noise = rng.normal(0, 1.0, n)
    close = start_price + trend + cycle + noise
    close = np.maximum(close, 1.0)  # keep strictly positive

    daily_range = np.abs(rng.normal(0, 0.6, n)) + 0.3
    high = close + daily_range
    low = close - daily_range
    open_ = close - rng.normal(0, 0.4, n)
    open_ = np.clip(open_, low, high)
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)

    return BarData(
        symbol="SYN",
        timeframe="1d",
        timestamps=timestamps,
        opens=open_.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=volume.tolist(),
    )


def make_noise_tail(n: int, seed: int, start_price: float) -> BarData:
    """A standalone noise series used to overwrite a tail — same generator
    family as make_synthetic_series so OHLC relationships stay sane, but an
    UNCORRELATED seed so the resulting prices are unrelated to the original
    tail (this is what makes it a stress test, not a no-op)."""
    return make_synthetic_series(n, seed=seed, start_price=start_price)


def ema_cross_strategy(
    symbol: str = "SYN", regime_filter: RegimeFilterConfig | None = None
) -> StrategyConfig:
    """The deployed-strategy shape (EMA10/26 cross, RSI<68 gate, trailing-ATR
    stop, 10% TP) on a configurable symbol/regime."""
    return StrategyConfig(
        name="probe_ema_cross",
        symbols=[symbol],
        indicators=[
            IndicatorConfig(type=IndicatorType.EMA, name="ema_fast", params={"period": 10}),
            IndicatorConfig(type=IndicatorType.EMA, name="ema_slow", params={"period": 26}),
            IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14}),
        ],
        entry_rules=[
            Rule(
                conditions=[
                    RuleCondition(left="ema_fast", comparison=Comparison.GT, right="ema_slow"),
                    RuleCondition(left="close", comparison=Comparison.GT, right="ema_slow"),
                    RuleCondition(left="rsi_14", comparison=Comparison.LT, right=68.0),
                ],
                logic="AND",
                side="long",
            )
        ],
        exit_rules=[
            Rule(
                conditions=[
                    RuleCondition(
                        left="ema_fast", comparison=Comparison.CROSSES_BELOW, right="ema_slow"
                    )
                ],
                logic="AND",
                side="long",
            )
        ],
        position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=98.0),
        max_positions=1,
        stop_loss=StopLossConfig(type=StopLossType.TRAILING_ATR, value=2.0, atr_period=14),
        take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.1),
        regime_filter=regime_filter,
    )


def simple_cross_strategy(symbol: str = "SYN") -> StrategyConfig:
    """A lighter-weight strategy (no stop/TP) for decision-point tests."""
    return StrategyConfig(
        name="probe_simple_cross",
        symbols=[symbol],
        indicators=[
            IndicatorConfig(type=IndicatorType.SMA, name="sma_fast", params={"period": 5}),
            IndicatorConfig(type=IndicatorType.SMA, name="sma_slow", params={"period": 20}),
        ],
        entry_rules=[
            Rule(
                conditions=[
                    RuleCondition(
                        left="sma_fast", comparison=Comparison.CROSSES_ABOVE, right="sma_slow"
                    )
                ],
                logic="AND",
                side="long",
            )
        ],
        exit_rules=[
            Rule(
                conditions=[
                    RuleCondition(
                        left="sma_fast", comparison=Comparison.CROSSES_BELOW, right="sma_slow"
                    )
                ],
                logic="AND",
                side="long",
            )
        ],
        position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=98.0),
        max_positions=1,
    )


def make_engine() -> BacktestEngine:
    return BacktestEngine(
        BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2030, 1, 1),
            initial_capital=100_000.0,
            commission=0.001,
            slippage=0.0005,
        )
    )


def ts_index_map(data: BarData) -> dict[datetime, int]:
    return {ts: idx for idx, ts in enumerate(data.timestamps)}


# Strategies exercised by the parametrized decision-point tests (A and B).
STRATEGIES = [
    pytest.param(ema_cross_strategy, id="ema_cross"),
    pytest.param(simple_cross_strategy, id="simple_cross"),
]


# ---------------------------------------------------------------------------
# Test A0 — absolute fill-price contract (own-bar open, not a neighbor's)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy_factory", STRATEGIES)
def test_a0_fill_price_matches_own_bar_open_exactly(strategy_factory) -> None:
    """Pins the timing contract directly, independent of any future
    perturbation: entry_price must equal opens[ts_index[entry_time]] * (1 +
    slippage) and exit_price must equal opens[ts_index[exit_time]] * (1 -
    slippage) (inverted for shorts) — i.e. the fill uses ITS OWN bar's open,
    not bar+1's or bar-1's.

    This closes a real gap that Test A/B (future-truncation/-scramble
    invariance) do NOT cover on their own: a systematic off-by-one fill
    (e.g. always filling at opens[i+1] instead of opens[i]) shifts every
    fill by one bar but does so *consistently*, so as long as the shifted
    bar is still at-or-before the truncation/scramble split point, the
    trade is "invariant" under that perturbation despite being filled at
    the WRONG bar's open. Only an absolute check against the bar data
    itself catches this class of leak.
    """
    data = make_synthetic_series(800, seed=42, start_price=150.0)
    strategy = strategy_factory()
    engine = make_engine()
    ts_index = ts_index_map(data)

    result = engine.run(strategy, data)
    assert result.trades, "fixture produced 0 trades — strengthen the fixture, not the test"

    slip = engine.config.slippage
    checked = 0
    for trade in result.trades:
        is_short = trade.position_side == "short"

        entry_i = ts_index[trade.entry_time]
        expected_entry = data.opens[entry_i] * (1 - slip if is_short else 1 + slip)
        assert np.isclose(trade.entry_price, expected_entry, rtol=RTOL, atol=ATOL), (
            f"entry@{trade.entry_time} (bar {entry_i}): entry_price={trade.entry_price} != "
            f"opens[{entry_i}]-based fill {expected_entry} — fill used the wrong bar's open"
        )
        checked += 1

        if trade.exit_reason == "end_of_data":
            continue  # end-of-data closes at closes[-1], not an open-fill — different contract
        exit_i = ts_index[trade.exit_time]
        expected_exit = data.opens[exit_i] * (1 + slip if is_short else 1 - slip)
        assert np.isclose(trade.exit_price, expected_exit, rtol=RTOL, atol=ATOL), (
            f"exit@{trade.exit_time} (bar {exit_i}): exit_price={trade.exit_price} != "
            f"opens[{exit_i}]-based fill {expected_exit} — fill used the wrong bar's open"
        )
        checked += 1

    assert checked > 0


# ---------------------------------------------------------------------------
# Test A1 — entry signal-read timing contract (signal at i-1, fill at i)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy_factory", STRATEGIES)
def test_a1_entry_fires_on_prior_bar_signal_not_current_bar(strategy_factory) -> None:
    """Independently recomputes the entry-signal arrays via the engine's own
    signal-generation path (`_evaluate_rules_by_side`, used in `run()`
    BEFORE `_simulate()`) and asserts: whenever a position is not held and
    an entry actually fires at bar i, the signal that justified it was true
    at i-1 — and was NOT solely true at i. This closes a gap that Test A0/
    A/B do not cover: a signal-read off-by-one (reading
    `long_entry_signals[i]` instead of `[i-1]`) shifts WHICH bar's
    indicator state triggers the entry by one bar, but the fill formula
    itself (opens[i] * (1 +/- slippage)) is untouched, so A0's absolute
    fill-price check stays green, and the shift is often invisible to A/B's
    invariance checks too (the entry still satisfies signal[i] in the
    perturbed run for any i <= m). Only re-deriving the signal array
    out-of-band and checking it against the ACTUAL bar a position opened on
    catches this surface directly.
    """
    data = make_synthetic_series(800, seed=42, start_price=150.0)
    strategy = strategy_factory()
    engine = make_engine()
    ts_index = ts_index_map(data)

    indicators = compute_indicators(data, strategy.indicators)
    long_signals = engine._evaluate_rules_by_side(strategy.entry_rules, indicators, "long")
    short_signals = engine._evaluate_rules_by_side(strategy.entry_rules, indicators, "short")

    result = engine.run(strategy, data)
    assert result.trades, "fixture produced 0 trades — strengthen the fixture, not the test"

    checked = 0
    for trade in result.trades:
        entry_i = ts_index[trade.entry_time]
        if entry_i == 0:
            continue  # bar 0 can never be an entry (loop starts at i=1; no prior bar to read)
        is_short = trade.position_side == "short"
        signal_for_side = short_signals if is_short else long_signals
        assert signal_for_side[entry_i - 1], (
            f"entry@{trade.entry_time} (bar {entry_i}, side={trade.position_side}): the "
            f"signal that should have authorized this entry, evaluated at bar {entry_i - 1} "
            f"(the bar BEFORE the fill bar, per the bar-N-1-signal/bar-N-execution "
            f"convention), was False — entry fired on a signal read from the wrong bar"
        )
        checked += 1

    assert checked > 0


# ---------------------------------------------------------------------------
# Test A — future-truncation invariance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy_factory", STRATEGIES)
def test_a_future_truncation_invariance(strategy_factory) -> None:
    """For each non-end-of-data trade's exit bar j, re-running the engine on
    the series truncated to [0:j+1] must reproduce that EXACT trade (side,
    entry/exit prices, quantity) — truncating the future must not change
    what already happened at-or-before bar j."""
    data = make_synthetic_series(800, seed=42, start_price=150.0)
    strategy = strategy_factory()
    engine = make_engine()
    ts_index = ts_index_map(data)

    reference = engine.run(strategy, data)
    real_trades = [t for t in reference.trades if t.exit_reason != "end_of_data"]
    assert real_trades, "fixture produced 0 non-EOD trades — strengthen the fixture, not the test"

    checked = 0
    for trade in real_trades:
        j = ts_index[trade.exit_time]
        truncated = data.slice(0, j + 1)
        if len(truncated) < 30:
            continue  # too short for a meaningful re-run (warm-up not satisfied)

        trunc_result = engine.run(strategy, truncated)
        trunc_real_trades = [t for t in trunc_result.trades if t.exit_reason != "end_of_data"]

        match = next(
            (
                tt
                for tt in trunc_real_trades
                if tt.entry_time == trade.entry_time and tt.exit_time == trade.exit_time
            ),
            None,
        )
        assert match is not None, (
            f"trade exit@{trade.exit_time} (bar {j}) not reproduced when truncated to "
            f"[0:{j + 1}]; truncated run had {len(trunc_real_trades)} non-EOD trades"
        )
        assert match.side == trade.side
        assert match.exit_reason == trade.exit_reason
        assert np.isclose(match.entry_price, trade.entry_price, rtol=RTOL, atol=ATOL)
        assert np.isclose(match.exit_price, trade.exit_price, rtol=RTOL, atol=ATOL)
        assert np.isclose(match.quantity, trade.quantity, rtol=RTOL, atol=ATOL)
        checked += 1

    assert checked > 0, "no trade had a long-enough truncation to check — strengthen the fixture"


# ---------------------------------------------------------------------------
# Test B — future-scramble invariance
# ---------------------------------------------------------------------------


def _scrambled_tail(data: BarData, m: int, seed: int) -> BarData:
    """Bars [0:m] unchanged, bars [m+1:] replaced by unrelated noise."""
    n = len(data)
    noise_tail = make_noise_tail(n - m - 1, seed=seed + 1000, start_price=float(data.closes[m]))
    scrambled = BarData(
        symbol=data.symbol,
        timeframe=data.timeframe,
        timestamps=data.timestamps,
        opens=data.opens[: m + 1] + noise_tail.opens,
        highs=data.highs[: m + 1] + noise_tail.highs,
        lows=data.lows[: m + 1] + noise_tail.lows,
        closes=data.closes[: m + 1] + noise_tail.closes,
        volumes=data.volumes[: m + 1] + noise_tail.volumes,
    )
    assert len(scrambled) == n
    return scrambled


@pytest.mark.parametrize("strategy_factory", STRATEGIES)
@pytest.mark.parametrize("frac", [0.3, 0.5, 0.7])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_b_future_scramble_invariance(strategy_factory, frac: float, seed: int) -> None:
    """Each trade contributes TWO independent decision points: its entry
    (decided at entry_idx-1, filled at entry_idx) and, if not an
    end-of-data force-close, its exit (decided at exit_idx-1, filled at
    exit_idx). They are compared SEPARATELY, each only against the field(s)
    that decision point actually determines.

    A trade whose entry_idx<=m but exit_idx>m is *expected* to exit
    differently after scrambling (the exit genuinely depends on post-m bars
    via the stop/TP/signal check on bar exit_idx — that's a trailing stop
    or TP doing its job, not a leak). Comparing such a trade's exit fields
    would conflate a legitimate downstream reaction to new data with a
    look-ahead leak, so only its entry is checked here; its exit is checked
    under its own (separate) exec_idx, and only if that index is itself
    <= m.

    Fixed seeds (1, 2, 3) across >=2 split fractions (0.3, 0.5, 0.7) for
    reproducibility — no unseeded randomness anywhere in this test.
    """
    data = make_synthetic_series(800, seed=42, start_price=150.0)
    strategy = strategy_factory()
    engine = make_engine()
    n = len(data)
    m = int(n * frac)
    if m < 30 or n - m < 5:
        pytest.skip("split point too close to either edge for a meaningful check")

    reference = engine.run(strategy, data)
    ts_index = ts_index_map(data)
    ref_entries = {ts_index[t.entry_time]: t for t in reference.trades}
    ref_exits = {
        ts_index[t.exit_time]: t for t in reference.trades if t.exit_reason != "end_of_data"
    }
    assert ref_entries, "fixture produced 0 trades — strengthen the fixture, not the test"

    scrambled = _scrambled_tail(data, m, seed)
    scrambled_result = engine.run(strategy, scrambled)
    scr_entries = {ts_index[t.entry_time]: t for t in scrambled_result.trades}
    scr_exits = {
        ts_index[t.exit_time]: t
        for t in scrambled_result.trades
        if t.exit_reason != "end_of_data"
    }

    checked = 0
    for exec_idx, ref_trade in ref_entries.items():
        if exec_idx > m:
            continue  # decided strictly after the scramble point — out of scope
        scr_trade = scr_entries.get(exec_idx)
        assert scr_trade is not None, (
            f"entry@{exec_idx}<=m={m} (seed={seed}): entry missing after scramble"
        )
        assert scr_trade.side == ref_trade.side
        assert np.isclose(scr_trade.entry_price, ref_trade.entry_price, rtol=RTOL, atol=ATOL), (
            f"entry@{exec_idx}<=m={m} (seed={seed}): entry_price diverged after scrambling "
            f"future bars"
        )
        assert np.isclose(scr_trade.quantity, ref_trade.quantity, rtol=RTOL, atol=ATOL)
        checked += 1

    for exec_idx, ref_trade in ref_exits.items():
        if exec_idx > m:
            continue  # exit genuinely decided using post-m data — out of scope
        scr_trade = scr_exits.get(exec_idx)
        assert scr_trade is not None, (
            f"exit@{exec_idx}<=m={m} (seed={seed}): exit missing after scramble"
        )
        assert scr_trade.exit_reason == ref_trade.exit_reason, (
            f"exit@{exec_idx}<=m={m} (seed={seed}): exit_reason "
            f"{scr_trade.exit_reason}!={ref_trade.exit_reason} after scrambling future bars"
        )
        assert np.isclose(scr_trade.exit_price, ref_trade.exit_price, rtol=RTOL, atol=ATOL), (
            f"exit@{exec_idx}<=m={m} (seed={seed}): exit_price diverged after scrambling "
            f"future bars"
        )
        checked += 1

    assert checked > 0, (
        f"(frac={frac}, seed={seed}) no entry/exit at or before split m={m} to check"
    )


# ---------------------------------------------------------------------------
# Test B-regime-0 — absolute regime-mask alignment contract
# ---------------------------------------------------------------------------


def test_b_regime_0_mask_uses_regime_bar_at_or_before_each_data_bar() -> None:
    """Directly unit-tests `BacktestEngine._compute_regime_mask`'s alignment
    against a hand-computed reference: for each data bar i, the regime mask
    MUST reflect the regime symbol's risk-on/off state as of the LATEST
    regime bar at-or-before data bar i's own timestamp — never a regime bar
    strictly after it.

    This closes a real gap discovered while proving non-vacuity: the
    scramble-invariance check (`test_b_regime_gated_scramble_invariance`,
    below) does NOT catch a `searchsorted(..., side="right")` ->
    `side="left"` mutation, because `np.searchsorted` guarantees
    `idx_left <= idx_right` for any sorted, duplicate-free array — so
    `side="left"` can only point at the SAME or an EARLIER regime bar than
    `side="right"`, never a LATER one. That mutation is a staleness bug
    (more conservative), not a forward leak, and is mathematically
    incapable of producing one — so no leak-detection test should be
    expected to go red for it; this test documents that boundary directly.

    What IS a genuine, exploitable forward leak on this exact code path is
    dropping the trailing `-1` (using `searchsorted(side="right")` without
    subtracting 1): that shifts every alignment one regime bar INTO THE
    FUTURE relative to each data bar. This test's hand-built fixture pins
    the exact-match boundary (data bar timestamps equal to regime bar
    timestamps) where the off-by-one is most visible, and is independently
    checked again under `test_b_regime_1_dropped_offset_is_real_forward_leak`.
    """
    # 6 data bars at days 0..5; regime bars at the SAME 6 timestamps so the
    # exact-match boundary (the case side="left"/"right" treat differently)
    # is exercised on every single bar.
    n = 6
    base = datetime(2024, 1, 1)
    regime_closes = [100.0, 90.0, 110.0, 95.0, 120.0, 80.0]  # alternating risk-on/off
    regime_data = BarData(
        symbol="REG",
        timeframe="1d",
        timestamps=[base + timedelta(days=i) for i in range(n)],
        opens=regime_closes,
        highs=[c * 1.01 for c in regime_closes],
        lows=[c * 0.99 for c in regime_closes],
        closes=regime_closes,
        volumes=[1_000_000.0] * n,
    )
    data = BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=[base + timedelta(days=i) for i in range(n)],
        opens=[100.0] * n,
        highs=[101.0] * n,
        lows=[99.0] * n,
        closes=[100.0] * n,
        volumes=[1_000_000.0] * n,
    )
    regime_filter_config = RegimeFilterConfig(symbol="REG", sma_period=2)
    engine = make_engine()

    mask = engine._compute_regime_mask(regime_filter_config, data, regime_data)

    # Hand-computed reference: SMA(2) of regime_closes, risk_on = close > sma.
    # sma[0] undefined (period not satisfied yet); sma[i] = mean(closes[i-1:i+1]) for i>=1.
    expected_risk_on = [
        False,  # bar 0: SMA undefined -> risk-off by construction
        np.mean([100.0, 90.0]) < 90.0,  # bar 1: sma=95 -> 90>95 False
        np.mean([90.0, 110.0]) < 110.0,  # bar 2: sma=100 -> 110>100 True
        np.mean([110.0, 95.0]) < 95.0,  # bar 3: sma=102.5 -> 95>102.5 False
        np.mean([95.0, 120.0]) < 120.0,  # bar 4: sma=107.5 -> 120>107.5 True
        np.mean([120.0, 80.0]) < 80.0,  # bar 5: sma=100 -> 80>100 False
    ]
    # Because data and regime_data share IDENTICAL timestamps, the correct
    # alignment for data bar i is regime bar i itself (its own latest
    # at-or-before bar) — so mask[i] must equal expected_risk_on[i] exactly,
    # bar for bar, with no shift in either direction.
    for i in range(n):
        assert bool(mask[i]) == expected_risk_on[i], (
            f"bar {i}: mask={bool(mask[i])} but the regime bar at-or-before bar {i}'s own "
            f"timestamp (itself, since timestamps are identical) is risk_on={expected_risk_on[i]} "
            f"— alignment picked the wrong regime bar"
        )


def test_b_regime_1_dropped_offset_forward_leak_is_real_and_detectable() -> None:
    """Pins, in a single hand-checkable assertion, that the `-1` in
    `searchsorted(regime_ts, bar_ts, side="right") - 1` is load-bearing: a
    version of the alignment that DROPS the `-1` would, for data bar i,
    select regime bar i+1 — whose SMA is computed from regime closes
    THROUGH i+1, i.e. one bar later than what data bar i should ever see.
    This test computes the mask manually with and without the `-1` on a
    fixture engineered so the two diverge, and confirms only the
    `-1`-included version matches the engine's actual output — i.e. the
    engine is on the non-leaking side of this specific boundary, checked
    directly rather than inferred from trade-level invariance.
    """
    n = 6
    base = datetime(2024, 1, 1)
    # A single regime flip from risk-off to risk-on, positioned so the
    # forward-shifted (no -1) alignment would see the flip one bar EARLY
    # relative to a data bar that has not yet reached the flip's regime bar.
    regime_closes = [100.0, 100.0, 100.0, 50.0, 200.0, 200.0]
    regime_data = BarData(
        symbol="REG",
        timeframe="1d",
        timestamps=[base + timedelta(days=i) for i in range(n)],
        opens=regime_closes,
        highs=[c * 1.01 for c in regime_closes],
        lows=[c * 0.99 for c in regime_closes],
        closes=regime_closes,
        volumes=[1_000_000.0] * n,
    )
    data = BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=[base + timedelta(days=i) for i in range(n)],
        opens=[100.0] * n,
        highs=[101.0] * n,
        lows=[99.0] * n,
        closes=[100.0] * n,
        volumes=[1_000_000.0] * n,
    )
    regime_filter_config = RegimeFilterConfig(symbol="REG", sma_period=2)
    engine = make_engine()

    mask = engine._compute_regime_mask(regime_filter_config, data, regime_data)

    period = regime_filter_config.sma_period
    closes = regime_data.close
    sma = np.full(len(closes), np.nan)
    sma[period - 1 :] = np.convolve(closes, np.ones(period) / period, mode="valid")
    risk_on = ~np.isnan(sma) & (closes > sma)

    regime_ts = np.array([t.timestamp() for t in regime_data.timestamps])
    bar_ts = np.array([t.timestamp() for t in data.timestamps])

    correct_idx = np.searchsorted(regime_ts, bar_ts, side="right") - 1
    leaked_idx = np.searchsorted(regime_ts, bar_ts, side="right")  # the -1 dropped

    assert not np.array_equal(correct_idx, leaked_idx), (
        "fixture failed to construct a case where dropping -1 changes the "
        "alignment — strengthen the fixture, not the test"
    )

    correct_mask = np.zeros(len(bar_ts), dtype=bool)
    valid = correct_idx >= 0
    correct_mask[valid] = risk_on[correct_idx[valid]]

    leaked_mask = np.zeros(len(bar_ts), dtype=bool)
    valid_leak = (leaked_idx >= 0) & (leaked_idx < len(risk_on))
    leaked_mask[valid_leak] = risk_on[leaked_idx[valid_leak]]

    assert not np.array_equal(correct_mask, leaked_mask), (
        "fixture failed to construct a case where the dropped-offset leak "
        "changes the resulting risk-on/off mask — strengthen the fixture"
    )
    np.testing.assert_array_equal(
        mask,
        correct_mask,
        err_msg="engine._compute_regime_mask diverged from the -1-included (non-leaking) "
        "reference — it is using the forward-leaking (dropped-offset) alignment",
    )


# ---------------------------------------------------------------------------
# Test B-regime — gated-regime scramble (searchsorted direction)
# ---------------------------------------------------------------------------


def engine_data_index(data: BarData, ts: datetime) -> int:
    return next(i for i, t in enumerate(data.timestamps) if t == ts)


@pytest.mark.parametrize("frac", [0.3, 0.5, 0.7])
@pytest.mark.parametrize("seed_offset", [0, 1, 2])
def test_b_regime_gated_scramble_invariance(frac: float, seed_offset: int) -> None:
    """A regime-gated strategy (SPY-as-its-own-regime, SMA-style on a
    synthetic series long enough to define the SMA): scrambling regime bars
    after split point m must not flip any entry signal at-or-before m.

    Targets the `searchsorted(side="right")-1` direction used by
    `BacktestEngine._compute_regime_mask` (engine.py) specifically — a
    `side="left"` or missing `-1` would look one regime bar into the
    future when aligning the regime mask onto the data timeline.
    """
    seed_base = 7
    n = 600
    data = make_synthetic_series(n, seed=seed_base, start_price=420.0)
    strategy = ema_cross_strategy(
        symbol="SYN", regime_filter=RegimeFilterConfig(symbol="SYN", sma_period=50)
    )
    engine = make_engine()

    reference = engine.run(strategy, data, regime_data=data)
    ref_entry_bars = {engine_data_index(data, t.entry_time) for t in reference.trades}
    assert ref_entry_bars, "fixture produced 0 trades — strengthen the fixture, not the test"

    m = int(n * frac)
    seed = seed_base + 100 + seed_offset
    noise_tail = make_noise_tail(n - m - 1, seed=seed, start_price=float(data.closes[m]))
    scrambled = BarData(
        symbol=data.symbol,
        timeframe=data.timeframe,
        timestamps=data.timestamps,
        opens=data.opens[: m + 1] + noise_tail.opens,
        highs=data.highs[: m + 1] + noise_tail.highs,
        lows=data.lows[: m + 1] + noise_tail.lows,
        closes=data.closes[: m + 1] + noise_tail.closes,
        volumes=data.volumes[: m + 1] + noise_tail.volumes,
    )
    scrambled_result = engine.run(strategy, scrambled, regime_data=scrambled)
    scr_entry_bars = {engine_data_index(scrambled, t.entry_time) for t in scrambled_result.trades}

    ref_le_m = {b for b in ref_entry_bars if b <= m}
    scr_le_m = {b for b in scr_entry_bars if b <= m}
    assert ref_le_m == scr_le_m, (
        f"(m={m}, seed={seed}): entries<=m flipped — ref={sorted(ref_le_m)} "
        f"scrambled={sorted(scr_le_m)}"
    )


# ---------------------------------------------------------------------------
# Test C — stop/TP same-bar honesty
# ---------------------------------------------------------------------------


def _build_handbuilt_stop_series(
    bar_i_plus_1_close: float, bar_i_plus_1_high: float, bar_i_plus_1_low: float
) -> tuple[BarData, int]:
    """Hand-built OHLC: unconditional entry on bar 1 (close>open), flat
    bars, then bar `stop_bar`'s LOW pierces a fixed 10% stop AND its close
    also breaches the stop level (so the engine's close-based check fires
    exactly there). Bar stop_bar+1 is parameterized so callers can swing it
    from a violent reversal to a flat no-op and confirm bar stop_bar's exit
    never moves."""
    base_date = datetime(2021, 1, 1)
    n = 10

    opens = [100.0] * n
    highs = [101.0] * n
    lows = [99.0] * n
    closes = [100.0] * n

    # Entry bar (index 1): close>open only here, by construction.
    closes[1] = 105.0
    opens[1] = 100.5
    highs[1] = 106.0
    lows[1] = 100.0

    for k in range(2, n):
        opens[k] = 105.0
        closes[k] = 105.0
        highs[k] = 106.0
        lows[k] = 104.0

    # stop_bar: low pierces a 10%-below-entry stop; close also breaches it.
    stop_bar = 5
    opens[stop_bar] = 105.0
    highs[stop_bar] = 105.2
    lows[stop_bar] = 90.0
    closes[stop_bar] = 91.0

    # stop_bar+1: parameterized reversal/flat — must NOT change stop_bar's exit.
    opens[stop_bar + 1] = 91.5
    highs[stop_bar + 1] = bar_i_plus_1_high
    lows[stop_bar + 1] = bar_i_plus_1_low
    closes[stop_bar + 1] = bar_i_plus_1_close

    for k in range(stop_bar + 2, n):
        opens[k] = closes[stop_bar + 1]
        closes[k] = closes[stop_bar + 1]
        highs[k] = closes[stop_bar + 1] + 1
        lows[k] = closes[stop_bar + 1] - 1

    timestamps = [base_date + timedelta(days=i) for i in range(n)]
    data = BarData(
        symbol="HANDBUILT",
        timeframe="1d",
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=[1_000_000.0] * n,
    )
    return data, stop_bar


def _handbuilt_stop_strategy() -> StrategyConfig:
    return StrategyConfig(
        name="probe_handbuilt_stop",
        symbols=["HANDBUILT"],
        indicators=[],
        entry_rules=[
            Rule(
                conditions=[RuleCondition(left="close", comparison=Comparison.GT, right="open")],
                side="long",
            )
        ],
        exit_rules=[],
        position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=98.0),
        max_positions=1,
        stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.10),
    )


def test_c_stop_fires_on_its_own_bar_not_neighbors() -> None:
    """A stop pierced by bar i's low (and close) must fire exactly at bar
    i — not bar i-1, not bar i+1 — even when bar i+1 reverses violently."""
    strategy = _handbuilt_stop_strategy()
    engine = make_engine()

    data, stop_bar = _build_handbuilt_stop_series(
        bar_i_plus_1_close=200.0, bar_i_plus_1_high=205.0, bar_i_plus_1_low=91.0
    )
    result = engine.run(strategy, data)
    exits = [t for t in result.trades if t.exit_reason == "stop_loss"]
    assert len(exits) == 1, (
        f"expected exactly 1 stop_loss exit, got {len(exits)}: "
        f"{[(t.exit_time, t.exit_reason) for t in result.trades]}"
    )

    exit_trade = exits[0]
    expected_exit_time = data.timestamps[stop_bar]
    assert exit_trade.exit_time == expected_exit_time, (
        f"stop fired at {exit_trade.exit_time}, expected bar {stop_bar} ({expected_exit_time})"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param((50.0, 55.0, 45.0), id="mild_reversal"),
        pytest.param((500.0, 510.0, 91.0), id="extreme_spike_up"),
        pytest.param((10.0, 91.5, 5.0), id="extreme_crash"),
        pytest.param((91.0, 91.1, 90.9), id="flat"),
    ],
)
def test_c_next_bar_mutation_does_not_change_stop_exit(mutation: tuple[float, float, float]) -> None:
    """Mutating ONLY bar stop_bar+1 (close/high/low) across a wide range —
    from a violent upside reversal to an extreme downside crash that would
    itself trip a stop if look-ahead leaked backward — must never change
    bar stop_bar's already-decided exit (time, exit_price, entry_price, pnl)."""
    strategy = _handbuilt_stop_strategy()
    engine = make_engine()

    baseline, stop_bar = _build_handbuilt_stop_series(
        bar_i_plus_1_close=200.0, bar_i_plus_1_high=205.0, bar_i_plus_1_low=91.0
    )
    baseline_result = engine.run(strategy, baseline)
    baseline_exit = next(t for t in baseline_result.trades if t.exit_reason == "stop_loss")

    c, h, lo = mutation
    mutated, stop_bar_mut = _build_handbuilt_stop_series(
        bar_i_plus_1_close=c, bar_i_plus_1_high=h, bar_i_plus_1_low=lo
    )
    assert stop_bar_mut == stop_bar
    mutated_result = engine.run(strategy, mutated)
    mutated_exits = [t for t in mutated_result.trades if t.exit_reason == "stop_loss"]
    assert len(mutated_exits) == 1, (
        f"mutation {mutation}: expected 1 stop_loss exit, got {len(mutated_exits)}"
    )

    mutated_exit = mutated_exits[0]
    assert mutated_exit.exit_time == baseline_exit.exit_time, (
        f"mutation {mutation} on bar {stop_bar + 1} changed bar {stop_bar}'s exit time: "
        f"{mutated_exit.exit_time} vs {baseline_exit.exit_time}"
    )
    assert np.isclose(mutated_exit.exit_price, baseline_exit.exit_price, rtol=RTOL, atol=ATOL)
    assert np.isclose(mutated_exit.entry_price, baseline_exit.entry_price, rtol=RTOL, atol=ATOL)
    assert np.isclose(mutated_exit.pnl, baseline_exit.pnl, rtol=RTOL, atol=ATOL)


# ---------------------------------------------------------------------------
# Test D — indicator forward-window check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "series_label,data_factory",
    [
        ("synthetic_800", lambda: make_synthetic_series(800, seed=42, start_price=150.0)),
        ("synthetic_300", lambda: make_synthetic_series(300, seed=99, start_price=55.0)),
    ],
)
def test_d_indicator_forward_window_invariance(series_label: str, data_factory) -> None:
    """SMA/EMA/RSI/ATR/MACD at index i must be identical whether computed on
    the full series or on series[:i+1] — an indicator that peeks at
    data[i+1:] while computing data[i] would diverge here. Both-NaN indices
    are skipped (first-valid-window seeding shifts leading NaNs — benign);
    a one-sided NaN (one run NaN, the other not) is itself a failure."""
    data = data_factory()
    n = len(data)

    configs = [
        IndicatorConfig(type=IndicatorType.SMA, name="sma", params={"period": 20}),
        IndicatorConfig(type=IndicatorType.EMA, name="ema", params={"period": 12}),
        IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
        IndicatorConfig(type=IndicatorType.ATR, name="atr", params={"period": 14}),
        IndicatorConfig(type=IndicatorType.MACD, name="macd", params={}),
    ]
    full = compute_indicators(data, configs)

    macd_keys = ["macd_line", "macd_signal", "macd_hist"]
    series_names = ["sma", "ema", "rsi", "atr", *macd_keys]

    sample_indices = sorted(set(range(0, n, max(1, n // 60))) | {n - 1})

    checked = 0
    for i in sample_indices:
        if i < 5:
            continue
        truncated = data.slice(0, i + 1)
        trunc_indicators = compute_indicators(truncated, configs)
        for name in series_names:
            full_val = full[name][i]
            trunc_val = trunc_indicators[name][-1]
            full_nan = np.isnan(full_val)
            trunc_nan = np.isnan(trunc_val)
            if full_nan and trunc_nan:
                continue  # both NaN — first-valid-window seeding difference, benign
            assert full_nan == trunc_nan, (
                f"[{series_label}] {name}[{i}]: NaN-status mismatch full={full_val} "
                f"truncated={trunc_val} (one is NaN, the other isn't — forward leak or bug)"
            )
            assert np.isclose(full_val, trunc_val, rtol=INDICATOR_RTOL), (
                f"[{series_label}] {name}[{i}]: full={full_val!r} truncated={trunc_val!r} differ"
            )
            checked += 1

    assert checked > 0, f"[{series_label}] no comparable (non-NaN-in-both) samples found"
