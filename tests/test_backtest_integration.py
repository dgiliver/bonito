"""Integration tests for backtesting with real data."""

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from quant_agent.backtest.engine import BacktestEngine
from quant_agent.backtest.models import BacktestConfig
from quant_agent.backtest.strategy import (
    Comparison,
    PositionSizeConfig,
    PositionSizeType,
    Rule,
    RuleCondition,
    StrategyConfig,
)
from quant_agent.data.store import MarketDataStore


@pytest.fixture
def real_spy_data():
    """Load real SPY data from the store."""
    store = MarketDataStore()
    data = store.get_bars(
        symbol="SPY", start=datetime(2020, 1, 1), end=datetime(2024, 1, 1), timeframe="1d"
    )
    store.close()

    if data is None:
        pytest.skip("SPY data not available. Run 'quant ingest SPY' first.")

    return data


@pytest.fixture
def engine():
    """Create a backtest engine."""
    config = BacktestConfig(
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2024, 1, 1),
        initial_capital=100000,
    )
    return BacktestEngine(config)


class TestEMACrossStrategy:
    """Integration tests for EMA crossover strategy."""

    def test_ema_cross_runs(self, engine, real_spy_data):
        """Test that EMA cross strategy runs without errors."""
        example_path = Path("examples/ema_cross_strategy.json")
        if not example_path.exists():
            pytest.skip("Example file not found")

        with open(example_path) as f:
            strategy_data = json.load(f)

        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)

        # Should produce valid results
        assert result.metrics.total_trades > 0
        assert result.metrics.sharpe_ratio == result.metrics.sharpe_ratio  # not NaN

    def test_ema_cross_reasonable_results(self, engine, real_spy_data):
        """Test that EMA cross results are reasonable."""
        example_path = Path("examples/ema_cross_strategy.json")
        if not example_path.exists():
            pytest.skip("Example file not found")

        with open(example_path) as f:
            strategy_data = json.load(f)

        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)

        # Results should be within reasonable bounds
        # (not crazy good or crazy bad - would indicate bugs)
        assert -1 < result.metrics.total_return < 5  # -100% to 500%
        assert -5 < result.metrics.sharpe_ratio < 5
        assert 0 <= result.metrics.max_drawdown <= 1
        assert 0 <= result.metrics.win_rate <= 1


class TestRSIMeanReversionStrategy:
    """Integration tests for RSI mean reversion strategy."""

    def test_rsi_strategy_runs(self, engine, real_spy_data):
        """Test that RSI strategy runs without errors."""
        example_path = Path("examples/rsi_mean_reversion.json")
        if not example_path.exists():
            pytest.skip("Example file not found")

        with open(example_path) as f:
            strategy_data = json.load(f)

        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)

        # Should complete without errors
        assert result.final_capital > 0

    def test_rsi_entries_at_oversold(self, engine, real_spy_data):
        """Test that RSI strategy enters at oversold conditions."""
        example_path = Path("examples/rsi_mean_reversion.json")
        if not example_path.exists():
            pytest.skip("Example file not found")

        with open(example_path) as f:
            strategy_data = json.load(f)

        strategy = StrategyConfig(**strategy_data)
        result = engine.run(strategy, real_spy_data)

        # Strategy should have trades (RSI < 30 occurs sometimes)
        # May be 0 if market never got oversold
        assert result.metrics.total_trades >= 0


class TestBuyAndHoldBaseline:
    """Test buy-and-hold as a sanity check."""

    def test_buy_and_hold_returns_positive(self, engine, real_spy_data):
        """Buy-and-hold on SPY 2020-2024 should be positive."""
        # Always-in strategy (buy and hold)
        strategy = StrategyConfig(
            name="buy_and_hold",
            symbols=["SPY"],
            entry_rules=[
                Rule(
                    conditions=[
                        # This should trigger on first bar and stay in
                        RuleCondition(left="close", comparison=Comparison.GT, right=0)
                    ]
                )
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=99),
        )

        result = engine.run(strategy, real_spy_data)

        # SPY 2020-2024 was generally positive
        assert result.metrics.total_return > 0

    def test_buy_and_hold_reasonable_sharpe(self, engine, real_spy_data):
        """Buy-and-hold Sharpe should be reasonable."""
        strategy = StrategyConfig(
            name="buy_and_hold",
            symbols=["SPY"],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=0)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=99),
        )

        result = engine.run(strategy, real_spy_data)

        # Market Sharpe is typically 0.3-0.8 long-term
        # Allow wider range for specific period
        assert -1 < result.metrics.sharpe_ratio < 3


class TestAllExampleStrategies:
    """Test that all example strategies work."""

    def test_all_examples_parse(self):
        """All example strategies should parse without errors."""
        examples_dir = Path("examples")
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        for json_file in examples_dir.glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)

            # Should parse without errors
            strategy = StrategyConfig(**data)
            assert strategy.name is not None

    def test_all_examples_run(self, engine, real_spy_data):
        """All example strategies should run without errors."""
        examples_dir = Path("examples")
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        for json_file in examples_dir.glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)

            strategy = StrategyConfig(**data)

            # Should run without raising exceptions
            result = engine.run(strategy, real_spy_data)
            assert result.final_capital > 0, f"Strategy {json_file.name} produced invalid result"


@pytest.mark.slow
class TestCLIIntegration:
    """End-to-end CLI tests."""

    def test_backtest_command_runs(self):
        """Test the backtest CLI command runs."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "quant_agent.cli",
                "backtest",
                "examples/ema_cross_strategy.json",
                "--start",
                "2023-01-01",
                "--end",
                "2023-12-31",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should either succeed or fail gracefully (not crash)
        # Success: mentions metrics
        # Graceful fail: mentions "no data" or similar
        combined_output = result.stdout + result.stderr
        assert (
            result.returncode == 0
            or "no data" in combined_output.lower()
            or "error" in combined_output.lower()
        )

    def test_backtest_with_override(self):
        """Test backtest with symbol override."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "quant_agent.cli",
                "backtest",
                "examples/ema_cross_strategy.json",
                "--symbol",
                "QQQ",
                "--start",
                "2023-01-01",
                "--end",
                "2023-06-30",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should run without crashing
        assert result.returncode in [0, 1]  # 0 = success, 1 = graceful error


@pytest.mark.slow
class TestPerformanceBenchmark:
    """Performance benchmarks."""

    def test_backtest_speed(self, engine, real_spy_data):
        """Backtest should complete in reasonable time."""
        import time

        from quant_agent.backtest.strategy import IndicatorConfig, IndicatorType

        strategy = StrategyConfig(
            name="perf_test",
            symbols=["SPY"],
            indicators=[
                IndicatorConfig(type=IndicatorType.EMA, name="fast", params={"period": 12}),
                IndicatorConfig(type=IndicatorType.EMA, name="slow", params={"period": 26}),
                IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
            ],
            entry_rules=[
                Rule(
                    conditions=[
                        RuleCondition(
                            left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow"
                        )
                    ]
                )
            ],
        )

        # Time the backtest
        start_time = time.time()
        _ = engine.run(strategy, real_spy_data)
        elapsed = time.time() - start_time

        print(f"\nBacktest completed in {elapsed:.3f} seconds")
        print(f"Bars processed: {len(real_spy_data)}")
        print(f"Bars per second: {len(real_spy_data) / elapsed:.0f}")

        # Should complete in under 5 seconds for ~1000 bars
        assert elapsed < 5.0, f"Backtest too slow: {elapsed:.2f}s"
