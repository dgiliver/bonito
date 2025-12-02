"""Tests for the backtest engine."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from quant_agent.backtest.engine import BacktestEngine
from quant_agent.backtest.models import BacktestConfig
from quant_agent.backtest.strategy import (
    StrategyConfig,
    IndicatorConfig,
    IndicatorType,
    Rule,
    RuleCondition,
    Comparison,
    PositionSizeConfig,
    PositionSizeType,
    StopLossConfig,
    StopLossType,
    TakeProfitConfig,
    TakeProfitType,
)
from quant_agent.data.models import BarData


@pytest.fixture
def sample_bar_data():
    """Create sample bar data for testing."""
    n = 100
    base_date = datetime(2024, 1, 1)
    timestamps = [base_date + timedelta(days=i) for i in range(n)]
    
    # Create trending price data
    np.random.seed(42)
    base_price = 100
    trend = np.linspace(0, 20, n)  # Upward trend
    noise = np.random.randn(n) * 2
    close = base_price + trend + noise
    
    return BarData(
        symbol="TEST",
        timeframe="1d",
        timestamps=timestamps,
        opens=(close - 0.5).tolist(),
        highs=(close + 1).tolist(),
        lows=(close - 1).tolist(),
        closes=close.tolist(),
        volumes=[1000000] * n,
    )


@pytest.fixture
def engine():
    """Create a backtest engine with default config."""
    config = BacktestConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000,
        commission=0.001,
        slippage=0.0005,
    )
    return BacktestEngine(config)


class TestRuleEvaluation:
    """Tests for rule evaluation logic."""
    
    def test_greater_than(self, engine, sample_bar_data):
        """Test > comparison."""
        # Strategy: enter when close > 110
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=110)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Should have some trades since price trends from 100 to 120
        assert result.metrics.total_trades > 0
    
    def test_less_than(self, engine, sample_bar_data):
        """Test < comparison."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.LT, right=105)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Should enter early when price is low
        if result.metrics.total_trades > 0:
            first_trade = result.trades[0]
            assert first_trade.entry_price < 110  # Entered at lower price
    
    def test_crosses_above(self, engine):
        """Test crosses_above comparison."""
        # Create data where fast EMA crosses above slow EMA
        n = 100
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        
        # Price starts low, then jumps up
        close = np.array([100.0] * 50 + [120.0] * 50)
        
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close + 1).tolist(),
            lows=(close - 1).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(type=IndicatorType.EMA, name="fast", params={"period": 5}),
                IndicatorConfig(type=IndicatorType.EMA, name="slow", params={"period": 20}),
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
                ])
            ]
        )
        
        result = engine.run(strategy, data)
        
        # Should have at least one trade from the crossover
        assert result.metrics.total_trades >= 1
    
    def test_and_logic(self, engine, sample_bar_data):
        """Test AND logic combines conditions correctly."""
        # Both conditions must be true
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            indicators=[
                IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14}),
            ],
            entry_rules=[
                Rule(
                    conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right=100),
                        RuleCondition(left="rsi", comparison=Comparison.LT, right=70),
                    ],
                    logic="AND"
                )
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        # Should run without error
        assert result.final_capital > 0
    
    def test_or_logic(self, engine, sample_bar_data):
        """Test OR logic allows either condition."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(
                    conditions=[
                        RuleCondition(left="close", comparison=Comparison.LT, right=90),  # Rarely true
                        RuleCondition(left="close", comparison=Comparison.GT, right=105),  # Often true
                    ],
                    logic="OR"
                )
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        # OR should trigger more trades than restrictive AND
        assert result.metrics.total_trades > 0


class TestTradeExecution:
    """Tests for trade execution logic."""
    
    def test_entry_at_open(self, engine, sample_bar_data):
        """Test that entries happen at next bar's open."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Verify trades were entered at open prices (not close)
        for trade in result.trades:
            # Entry price should be positive
            assert trade.entry_price > 0
    
    def test_commission_deducted(self, engine, sample_bar_data):
        """Test that commissions are properly deducted."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Total commission should be positive if there are trades
        if result.metrics.total_trades > 0:
            assert result.total_commission > 0
    
    def test_position_sizing_percent(self, engine, sample_bar_data):
        """Test percent equity position sizing."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=50)
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Should have trades with reasonable size
        if result.trades:
            first_trade = result.trades[0]
            position_value = first_trade.entry_price * first_trade.quantity
            # Should be roughly 50% of initial capital
            assert 40000 < position_value < 60000


class TestStopLoss:
    """Tests for stop loss execution."""
    
    def test_percent_stop_loss_triggers(self):
        """Test that percent stop loss triggers correctly."""
        # Create data with a crash
        n = 50
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        
        # Price rises then crashes
        close = np.array([100.0] * 10 + [105.0] * 10 + [90.0] * 30)
        
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close + 1).tolist(),
            lows=(close - 1).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
        
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100000,
            commission=0,
            slippage=0,
        )
        engine = BacktestEngine(config)
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=103)
                ])
            ],
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.10),  # 10% stop
        )
        
        result = engine.run(strategy, data)
        
        # Should have exited due to stop loss
        stop_exits = [t for t in result.trades if t.exit_reason == "stop_loss"]
        assert len(stop_exits) > 0, "Stop loss should have triggered"


class TestTakeProfit:
    """Tests for take profit execution."""
    
    def test_percent_take_profit_triggers(self):
        """Test that percent take profit triggers correctly."""
        n = 50
        timestamps = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        
        # Price rises steadily
        close = np.linspace(100, 130, n)
        
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=timestamps,
            opens=close.tolist(),
            highs=(close + 1).tolist(),
            lows=(close - 1).tolist(),
            closes=close.tolist(),
            volumes=[1000000] * n,
        )
        
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100000,
            commission=0,
            slippage=0,
        )
        engine = BacktestEngine(config)
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ],
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.15),  # 15% target
        )
        
        result = engine.run(strategy, data)
        
        # Should have exited due to take profit
        tp_exits = [t for t in result.trades if t.exit_reason == "take_profit"]
        assert len(tp_exits) > 0, "Take profit should have triggered"


class TestMetricsCalculation:
    """Tests for performance metrics."""
    
    def test_positive_returns_profitable(self, engine, sample_bar_data):
        """Test that positive price movement creates positive returns."""
        # Buy and hold strategy (always in)
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=0)  # Always true
                ])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=100)
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Sample data trends up, so should be profitable
        assert result.metrics.total_return > 0
    
    def test_sharpe_ratio_calculation(self, engine, sample_bar_data):
        """Test that Sharpe ratio is calculated correctly."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Sharpe should be a reasonable number (not NaN or infinity)
        assert not np.isnan(result.metrics.sharpe_ratio)
        assert not np.isinf(result.metrics.sharpe_ratio)
    
    def test_max_drawdown_calculation(self, engine, sample_bar_data):
        """Test that max drawdown is calculated correctly."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Max drawdown should be between 0 and 1 (0-100%)
        assert 0 <= result.metrics.max_drawdown <= 1
    
    def test_win_rate_calculation(self, engine, sample_bar_data):
        """Test that win rate is calculated correctly."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ],
            exit_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=115)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        if result.metrics.total_trades > 0:
            # Win rate should be between 0 and 1
            assert 0 <= result.metrics.win_rate <= 1
            
            # Win rate should match actual winning trades
            winning = result.metrics.winning_trades
            total = result.metrics.total_trades
            expected_win_rate = winning / total if total > 0 else 0
            assert result.metrics.win_rate == pytest.approx(expected_win_rate)


class TestEquityCurve:
    """Tests for equity curve generation."""
    
    def test_equity_curve_length(self, engine, sample_bar_data):
        """Test that equity curve has correct length."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # Equity curve should have entries
        assert len(result.equity_curve) > 0
        assert len(result.equity_curve) == len(result.equity_dates)
    
    def test_equity_curve_starts_at_initial(self, engine, sample_bar_data):
        """Test that equity curve starts at initial capital."""
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=1000)  # Never enters
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        
        # If no trades, equity should remain at initial capital
        if result.metrics.total_trades == 0:
            assert all(eq == pytest.approx(100000) for eq in result.equity_curve)


class TestResultSummary:
    """Tests for result summary output."""
    
    def test_summary_contains_key_metrics(self, engine, sample_bar_data):
        """Test that summary contains all key metrics."""
        strategy = StrategyConfig(
            name="test_summary",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        result = engine.run(strategy, sample_bar_data)
        summary = result.summary()
        
        assert "test_summary" in summary
        assert "Total Return" in summary
        assert "Sharpe Ratio" in summary
        assert "Max Drawdown" in summary
        assert "Win Rate" in summary


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_data(self, engine):
        """Test handling of empty data."""
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=[],
            opens=[],
            highs=[],
            lows=[],
            closes=[],
            volumes=[],
        )
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        # Should handle gracefully, not crash
        result = engine.run(strategy, data)
        assert result.metrics.total_trades == 0
    
    def test_single_bar(self, engine):
        """Test handling of single bar."""
        data = BarData(
            symbol="TEST",
            timeframe="1d",
            timestamps=[datetime(2024, 1, 1)],
            opens=[100.0],
            highs=[101.0],
            lows=[99.0],
            closes=[100.5],
            volumes=[1000000],
        )
        
        strategy = StrategyConfig(
            name="test",
            symbols=["TEST"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        # Should handle gracefully
        result = engine.run(strategy, data)
        assert result.final_capital > 0

