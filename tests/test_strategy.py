"""Tests for strategy configuration parsing."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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


class TestIndicatorConfig:
    """Tests for IndicatorConfig model."""
    
    def test_valid_sma(self):
        """Test creating valid SMA indicator."""
        config = IndicatorConfig(
            type=IndicatorType.SMA,
            name="sma_20",
            params={"period": 20}
        )
        assert config.type == IndicatorType.SMA
        assert config.params["period"] == 20
    
    def test_valid_macd(self):
        """Test creating valid MACD indicator."""
        config = IndicatorConfig(
            type=IndicatorType.MACD,
            name="macd",
            params={"fast_period": 12, "slow_period": 26, "signal_period": 9}
        )
        assert config.type == IndicatorType.MACD
    
    def test_default_params(self):
        """Test that params defaults to empty dict."""
        config = IndicatorConfig(
            type=IndicatorType.RSI,
            name="rsi"
        )
        assert config.params == {}
    
    def test_all_indicator_types(self):
        """Test that all indicator types are valid."""
        types = [
            IndicatorType.SMA,
            IndicatorType.EMA,
            IndicatorType.RSI,
            IndicatorType.MACD,
            IndicatorType.ATR,
            IndicatorType.BBANDS,
            IndicatorType.STOCH,
        ]
        for ind_type in types:
            config = IndicatorConfig(type=ind_type, name=f"test_{ind_type.value}")
            assert config.type == ind_type


class TestRuleCondition:
    """Tests for RuleCondition model."""
    
    def test_numeric_comparison(self):
        """Test condition with numeric right side."""
        cond = RuleCondition(
            left="rsi",
            comparison=Comparison.LT,
            right=30
        )
        assert cond.right == 30
    
    def test_indicator_comparison(self):
        """Test condition comparing two indicators."""
        cond = RuleCondition(
            left="fast_ema",
            comparison=Comparison.CROSSES_ABOVE,
            right="slow_ema"
        )
        assert cond.right == "slow_ema"
    
    def test_string_numeric_right(self):
        """Test condition with string numeric on right."""
        cond = RuleCondition(
            left="rsi",
            comparison=Comparison.LT,
            right="30"
        )
        assert cond.right == "30"
    
    def test_all_comparison_types(self):
        """Test all comparison operators are valid."""
        comparisons = [
            Comparison.GT,
            Comparison.GTE,
            Comparison.LT,
            Comparison.LTE,
            Comparison.EQ,
            Comparison.CROSSES_ABOVE,
            Comparison.CROSSES_BELOW,
        ]
        for comp in comparisons:
            cond = RuleCondition(left="a", comparison=comp, right="b")
            assert cond.comparison == comp


class TestRule:
    """Tests for Rule model."""
    
    def test_single_condition(self):
        """Test rule with single condition."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30)
            ]
        )
        assert len(rule.conditions) == 1
        assert rule.logic == "AND"  # default
    
    def test_multiple_conditions_and(self):
        """Test rule with multiple AND conditions."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30),
                RuleCondition(left="close", comparison=Comparison.GT, right="sma_200"),
            ],
            logic="AND"
        )
        assert len(rule.conditions) == 2
    
    def test_multiple_conditions_or(self):
        """Test rule with multiple OR conditions."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30),
                RuleCondition(left="rsi", comparison=Comparison.GT, right=70),
            ],
            logic="OR"
        )
        assert rule.logic == "OR"
    
    def test_empty_conditions_fails(self):
        """Test that empty conditions list fails validation."""
        with pytest.raises(ValidationError):
            Rule(conditions=[])


class TestPositionSizeConfig:
    """Tests for PositionSizeConfig model."""
    
    def test_percent_equity(self):
        """Test percent equity position sizing."""
        config = PositionSizeConfig(
            type=PositionSizeType.PERCENT_EQUITY,
            value=25
        )
        assert config.type == PositionSizeType.PERCENT_EQUITY
        assert config.value == 25
    
    def test_fixed_value(self):
        """Test fixed value position sizing."""
        config = PositionSizeConfig(
            type=PositionSizeType.FIXED_VALUE,
            value=10000
        )
        assert config.type == PositionSizeType.FIXED_VALUE
    
    def test_fixed_quantity(self):
        """Test fixed quantity position sizing."""
        config = PositionSizeConfig(
            type=PositionSizeType.FIXED_QUANTITY,
            value=100
        )
        assert config.type == PositionSizeType.FIXED_QUANTITY


class TestStopLossConfig:
    """Tests for StopLossConfig model."""
    
    def test_percent_stop(self):
        """Test percent stop loss."""
        config = StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        assert config.type == StopLossType.PERCENT
        assert config.value == 0.05
    
    def test_atr_stop(self):
        """Test ATR-based stop loss."""
        config = StopLossConfig(type=StopLossType.ATR, value=2.0)
        assert config.type == StopLossType.ATR
    
    def test_fixed_stop(self):
        """Test fixed price stop loss."""
        config = StopLossConfig(type=StopLossType.FIXED, value=5.0)
        assert config.type == StopLossType.FIXED


class TestTakeProfitConfig:
    """Tests for TakeProfitConfig model."""
    
    def test_percent_target(self):
        """Test percent take profit."""
        config = TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.10)
        assert config.type == TakeProfitType.PERCENT
    
    def test_risk_multiple(self):
        """Test risk multiple take profit."""
        config = TakeProfitConfig(type=TakeProfitType.RISK_MULTIPLE, value=2.0)
        assert config.type == TakeProfitType.RISK_MULTIPLE


class TestStrategyConfig:
    """Tests for StrategyConfig model."""
    
    def test_minimal_valid_strategy(self):
        """Test creating minimal valid strategy."""
        config = StrategyConfig(
            name="test",
            symbols=["SPY"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        assert config.name == "test"
        assert config.timeframe == "1d"  # default
        assert config.max_positions == 1  # default
    
    def test_full_strategy(self):
        """Test creating fully-specified strategy."""
        config = StrategyConfig(
            name="full_test",
            description="A complete test strategy",
            version="2.0",
            symbols=["SPY", "QQQ"],
            timeframe="1h",
            indicators=[
                IndicatorConfig(type=IndicatorType.EMA, name="fast", params={"period": 12}),
                IndicatorConfig(type=IndicatorType.EMA, name="slow", params={"period": 26}),
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
                ])
            ],
            exit_rules=[
                Rule(conditions=[
                    RuleCondition(left="fast", comparison=Comparison.CROSSES_BELOW, right="slow")
                ])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=25),
            max_positions=2,
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05),
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.10),
        )
        
        assert config.version == "2.0"
        assert len(config.indicators) == 2
        assert config.position_size.value == 25
    
    def test_no_symbols_fails(self):
        """Test that empty symbols list fails."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=[],
                entry_rules=[
                    Rule(conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right=100)
                    ])
                ]
            )
    
    def test_no_entry_rules_fails(self):
        """Test that empty entry_rules fails."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=["SPY"],
                entry_rules=[]
            )
    
    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=["SPY"],
                entry_rules=[
                    Rule(conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right=100)
                    ])
                ],
                unknown_field="should fail"
            )
    
    def test_all_timeframes(self):
        """Test that all timeframes are valid."""
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        for tf in timeframes:
            config = StrategyConfig(
                name="test",
                symbols=["SPY"],
                timeframe=tf,
                entry_rules=[
                    Rule(conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right=100)
                    ])
                ]
            )
            assert config.timeframe == tf


class TestStrategyFromJSON:
    """Tests for loading strategies from JSON."""
    
    def test_load_ema_cross_example(self):
        """Test loading the example EMA cross strategy."""
        example_path = Path("examples/ema_cross_strategy.json")
        if not example_path.exists():
            pytest.skip("Example file not found")
        
        with open(example_path) as f:
            data = json.load(f)
        
        config = StrategyConfig(**data)
        assert config.name == "ema_cross_basic"
        assert "SPY" in config.symbols
    
    def test_load_rsi_mean_reversion_example(self):
        """Test loading the example RSI mean reversion strategy."""
        example_path = Path("examples/rsi_mean_reversion.json")
        if not example_path.exists():
            pytest.skip("Example file not found")
        
        with open(example_path) as f:
            data = json.load(f)
        
        config = StrategyConfig(**data)
        assert config.name == "rsi_mean_reversion"
    
    def test_roundtrip_json(self):
        """Test that strategy can be serialized and deserialized."""
        original = StrategyConfig(
            name="roundtrip_test",
            symbols=["AAPL"],
            indicators=[
                IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="rsi", comparison=Comparison.LT, right=30)
                ])
            ]
        )
        
        # Serialize
        json_str = original.model_dump_json()
        
        # Deserialize
        loaded = StrategyConfig.model_validate_json(json_str)
        
        assert loaded.name == original.name
        assert loaded.symbols == original.symbols
        assert loaded.indicators[0].name == original.indicators[0].name
    
    def test_from_dict(self):
        """Test creating strategy from dictionary."""
        data = {
            "name": "from_dict",
            "symbols": ["QQQ"],
            "timeframe": "1h",
            "indicators": [
                {"type": "rsi", "name": "rsi_14", "params": {"period": 14}}
            ],
            "entry_rules": [
                {
                    "conditions": [
                        {"left": "rsi_14", "comparison": "<", "right": 30}
                    ],
                    "logic": "AND"
                }
            ],
            "position_size": {"type": "percent_equity", "value": 25}
        }
        
        config = StrategyConfig(**data)
        
        assert config.name == "from_dict"
        assert config.timeframe == "1h"
        assert config.indicators[0].type == IndicatorType.RSI
        assert config.position_size.value == 25


class TestToPromptDescription:
    """Tests for to_prompt_description method."""
    
    def test_includes_key_info(self):
        """Test that description includes all key information."""
        config = StrategyConfig(
            name="test_strategy",
            description="My test",
            symbols=["SPY"],
            indicators=[
                IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})
            ],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right="sma_20")
                ])
            ],
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        )
        
        desc = config.to_prompt_description()
        
        assert "test_strategy" in desc
        assert "SPY" in desc
        assert "sma_20" in desc
        assert "close" in desc
        assert "Stop Loss" in desc
    
    def test_readable_format(self):
        """Test that description is human-readable."""
        config = StrategyConfig(
            name="readable_test",
            symbols=["AAPL"],
            entry_rules=[
                Rule(conditions=[
                    RuleCondition(left="close", comparison=Comparison.GT, right=100)
                ])
            ]
        )
        
        desc = config.to_prompt_description()
        
        # Should have line breaks and structure
        assert "\n" in desc
        assert "Strategy:" in desc
        assert "Entry Rules:" in desc
