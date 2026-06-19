"""CLI-level smoke test for `bonito backtest`.

Regression guard for the bug fixed in commit f77d428: `bonito backtest`
never fetched/passed `regime_data`, so any strategy with a `regime_filter`
crashed inside the engine (`BacktestEngine.run()` raises `ValueError` when
`regime_filter` is set but `regime_data` is None - see
`src/bonito/backtest/engine.py`). This test is hermetic - no real DuckDB, no
network - and exercises the full CLI path end-to-end via `typer.testing.
CliRunner`, with `bonito.cli._get_store` monkeypatched to a fake in-memory
store that serves synthetic OHLCV bars for both the strategy's primary
symbol (IREN) and its regime-filter symbol (SPY). The regime symbol's data
fetch is exactly the code path that used to be skipped entirely.
"""

import json
from datetime import datetime, timedelta

import numpy as np
import pytest
from typer.testing import CliRunner

from bonito.cli import app
from bonito.data.models import BarData

runner = CliRunner()


def _make_bar_data(symbol: str, start: datetime, end: datetime, timeframe: str) -> BarData:
    """Generate deterministic, gap-free synthetic daily OHLCV bars.

    One bar per calendar day from `start` to `end` inclusive (matching
    `MarketDataStore.get_bars`'s `timestamp >= ? AND timestamp <= ?`
    semantics), with enough length to clear any indicator warmup
    (EMA/RSI/ATR on the primary symbol; SMA(200) regime filter on the
    regime symbol) regardless of which symbol is requested.
    """
    n_days = (end - start).days + 1
    timestamps = [start + timedelta(days=i) for i in range(n_days)]

    rng = np.random.default_rng(abs(hash(symbol)) % (2**32))
    returns = rng.normal(loc=0.0003, scale=0.015, size=n_days)
    close = 100.0 * np.cumprod(1 + returns)
    high = close * 1.01
    low = close * 0.99
    open_ = close * 0.999
    volume = np.full(n_days, 1_000_000.0)

    return BarData(
        symbol=symbol,
        timeframe=timeframe,
        timestamps=timestamps,
        opens=open_.tolist(),
        highs=high.tolist(),
        lows=low.tolist(),
        closes=close.tolist(),
        volumes=volume.tolist(),
    )


class FakeMarketDataStore:
    """In-memory stand-in for `MarketDataStore` - no DuckDB, no network.

    Serves synthetic bars for any symbol/date-range it's asked for, so the
    same fake handles both the `get_bars(target_symbol, ...)` call and the
    `get_bars(regime_symbol, ...)` call the CLI makes when
    `strategy.regime_filter` is set.
    """

    def __init__(self) -> None:
        self.requested_symbols: list[str] = []

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str = "1d"
    ) -> BarData | None:
        self.requested_symbols.append(symbol)
        return _make_bar_data(symbol, start, end, timeframe)

    def close(self) -> None:
        pass


@pytest.fixture
def regime_strategy_path(tmp_path):
    """A strategy config with a `regime_filter` on a symbol different from

    the traded symbol - shaped like `strategies/iren_ema8-21_rsi68_atr1.5_
    tpnone.json` (IREN traded, SPY regime gate), the realistic deployed
    example of this field. Using two distinct symbols is the strongest
    regression guard: it fails if the regime symbol's fetch is skipped
    entirely (the original bug), not just if it happens to crash on
    overlapping data.
    """
    config = {
        "name": "test_ema_cross_regime",
        "description": "EMA cross + RSI filter, SPY regime gate (CLI smoke test fixture)",
        "version": "1.0",
        "symbols": ["IREN"],
        "timeframe": "1d",
        "indicators": [
            {"type": "ema", "name": "ema_fast", "params": {"period": 8}},
            {"type": "ema", "name": "ema_slow", "params": {"period": 21}},
            {"type": "rsi", "name": "rsi_14", "params": {"period": 14}},
        ],
        "entry_rules": [
            {
                "conditions": [
                    {"left": "ema_fast", "comparison": "gt", "right": "ema_slow"},
                    {"left": "close", "comparison": "gt", "right": "ema_slow"},
                    {"left": "rsi_14", "comparison": "lt", "right": 68.0},
                ],
                "logic": "AND",
                "side": "long",
            }
        ],
        "exit_rules": [
            {
                "conditions": [
                    {"left": "ema_fast", "comparison": "crosses_below", "right": "ema_slow"}
                ],
                "logic": "AND",
                "side": "long",
            }
        ],
        "position_size": {"type": "percent_equity", "value": 98.0},
        "max_positions": 1,
        "stop_loss": {"type": "trailing_atr", "value": 1.5, "atr_period": 14},
        "take_profit": None,
        "regime_filter": {"symbol": "SPY", "sma_period": 200},
    }
    path = tmp_path / "test_regime_strategy.json"
    path.write_text(json.dumps(config))
    return path


def test_backtest_with_regime_filter_runs_to_completion(monkeypatch, regime_strategy_path):
    """`bonito backtest` on a regime-filtered strategy must exit 0 and print

    results, not crash. Before the fix, the CLI's `backtest` command never
    fetched regime data, so `BacktestEngine.run()` raised `ValueError`
    ("has a regime_filter ... but no regime_data was provided") for any
    strategy with `regime_filter` set - this reproduces that path end-to-end
    through the real CLI command, not just the engine directly.
    """
    fake_store = FakeMarketDataStore()
    monkeypatch.setattr("bonito.cli._get_store", lambda: fake_store)

    result = runner.invoke(
        app,
        [
            "backtest",
            str(regime_strategy_path),
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
        ],
    )

    assert result.exit_code == 0, (
        f"bonito backtest crashed (exit {result.exit_code}):\n{result.output}"
    )
    # The regime symbol's data must actually have been fetched - this is the
    # exact call the original bug skipped.
    assert "SPY" in fake_store.requested_symbols
    assert "IREN" in fake_store.requested_symbols
    # Real backtest output, not just a clean exit - distinguishes "ran the
    # backtest" from "silently did nothing."
    assert "Performance Metrics" in result.output
    assert "Sharpe Ratio" in result.output
    assert "Total Trades" in result.output


def test_backtest_without_regime_filter_does_not_request_regime_symbol(monkeypatch, tmp_path):
    """Sanity check / non-regression: a strategy with no `regime_filter`

    must not trigger any second `get_bars` call for a regime symbol - the
    regime-data fetch is conditional on `strategy.regime_filter is not
    None`, not unconditional.
    """
    config = {
        "name": "test_ema_cross_no_regime",
        "symbols": ["IREN"],
        "timeframe": "1d",
        "indicators": [
            {"type": "ema", "name": "ema_fast", "params": {"period": 8}},
            {"type": "ema", "name": "ema_slow", "params": {"period": 21}},
        ],
        "entry_rules": [
            {
                "conditions": [{"left": "ema_fast", "comparison": "gt", "right": "ema_slow"}],
                "logic": "AND",
                "side": "long",
            }
        ],
        "exit_rules": [],
        "position_size": {"type": "percent_equity", "value": 98.0},
        "max_positions": 1,
    }
    path = tmp_path / "test_no_regime_strategy.json"
    path.write_text(json.dumps(config))

    fake_store = FakeMarketDataStore()
    monkeypatch.setattr("bonito.cli._get_store", lambda: fake_store)

    result = runner.invoke(
        app, ["backtest", str(path), "--start", "2023-01-01", "--end", "2023-12-31"]
    )

    assert result.exit_code == 0, (
        f"bonito backtest crashed (exit {result.exit_code}):\n{result.output}"
    )
    assert fake_store.requested_symbols == ["IREN"]
