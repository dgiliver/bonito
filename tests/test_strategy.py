"""Tests for strategy configuration parsing."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    IndicatorType,
    PositionSizeConfig,
    PositionSizeType,
    Rule,
    RuleCondition,
    StopLossConfig,
    StopLossType,
    StrategyConfig,
    TakeProfitConfig,
    TakeProfitType,
)


class TestIndicatorConfig:
    """Tests for IndicatorConfig model."""

    def test_valid_sma(self):
        """Test creating valid SMA indicator."""
        config = IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})
        assert config.type == IndicatorType.SMA
        assert config.params["period"] == 20

    def test_valid_macd(self):
        """Test creating valid MACD indicator."""
        config = IndicatorConfig(
            type=IndicatorType.MACD,
            name="macd",
            params={"fast_period": 12, "slow_period": 26, "signal_period": 9},
        )
        assert config.type == IndicatorType.MACD

    def test_default_params(self):
        """Test that params defaults to empty dict."""
        config = IndicatorConfig(type=IndicatorType.RSI, name="rsi")
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
        cond = RuleCondition(left="rsi", comparison=Comparison.LT, right=30)
        assert cond.right == 30

    def test_indicator_comparison(self):
        """Test condition comparing two indicators."""
        cond = RuleCondition(left="fast_ema", comparison=Comparison.CROSSES_ABOVE, right="slow_ema")
        assert cond.right == "slow_ema"

    def test_string_numeric_right(self):
        """Test condition with string numeric on right."""
        cond = RuleCondition(left="rsi", comparison=Comparison.LT, right="30")
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
        rule = Rule(conditions=[RuleCondition(left="rsi", comparison=Comparison.LT, right=30)])
        assert len(rule.conditions) == 1
        assert rule.logic == "AND"  # default

    def test_multiple_conditions_and(self):
        """Test rule with multiple AND conditions."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30),
                RuleCondition(left="close", comparison=Comparison.GT, right="sma_200"),
            ],
            logic="AND",
        )
        assert len(rule.conditions) == 2

    def test_multiple_conditions_or(self):
        """Test rule with multiple OR conditions."""
        rule = Rule(
            conditions=[
                RuleCondition(left="rsi", comparison=Comparison.LT, right=30),
                RuleCondition(left="rsi", comparison=Comparison.GT, right=70),
            ],
            logic="OR",
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
        config = PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=25)
        assert config.type == PositionSizeType.PERCENT_EQUITY
        assert config.value == 25

    def test_fixed_value(self):
        """Test fixed value position sizing."""
        config = PositionSizeConfig(type=PositionSizeType.FIXED_VALUE, value=10000)
        assert config.type == PositionSizeType.FIXED_VALUE

    def test_fixed_quantity(self):
        """Test fixed quantity position sizing."""
        config = PositionSizeConfig(type=PositionSizeType.FIXED_QUANTITY, value=100)
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
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=100)])
            ],
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
                Rule(
                    conditions=[
                        RuleCondition(
                            left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow"
                        )
                    ]
                )
            ],
            exit_rules=[
                Rule(
                    conditions=[
                        RuleCondition(
                            left="fast", comparison=Comparison.CROSSES_BELOW, right="slow"
                        )
                    ]
                )
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
                    Rule(
                        conditions=[
                            RuleCondition(left="close", comparison=Comparison.GT, right=100)
                        ]
                    )
                ],
            )

    def test_no_entry_rules_fails(self):
        """Test that empty entry_rules fails."""
        with pytest.raises(ValidationError):
            StrategyConfig(name="test", symbols=["SPY"], entry_rules=[])

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            StrategyConfig(
                name="test",
                symbols=["SPY"],
                entry_rules=[
                    Rule(
                        conditions=[
                            RuleCondition(left="close", comparison=Comparison.GT, right=100)
                        ]
                    )
                ],
                unknown_field="should fail",
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
                    Rule(
                        conditions=[
                            RuleCondition(left="close", comparison=Comparison.GT, right=100)
                        ]
                    )
                ],
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
            indicators=[IndicatorConfig(type=IndicatorType.RSI, name="rsi", params={"period": 14})],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="rsi", comparison=Comparison.LT, right=30)])
            ],
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
            "indicators": [{"type": "rsi", "name": "rsi_14", "params": {"period": 14}}],
            "entry_rules": [
                {
                    "conditions": [{"left": "rsi_14", "comparison": "lt", "right": 30}],
                    "logic": "AND",
                }
            ],
            "position_size": {"type": "percent_equity", "value": 25},
        }

        config = StrategyConfig(**data)

        assert config.name == "from_dict"
        assert config.timeframe == "1h"
        assert config.indicators[0].type == IndicatorType.RSI
        assert config.position_size.value == 25


class TestStrEnumSerializationStability:
    """Regression test for the (str, Enum) -> enum.StrEnum migration (P2-2,
    commit 69cecbd, Phase 2 Decision #2).

    StrEnum members format identically to plain str via str()/f-strings
    ("sma", not the legacy (str, Enum) default of "IndicatorType.SMA"), but
    nothing structurally prevents a future regression if code starts relying
    on str(member) instead of member.value. This test builds a StrategyConfig
    that exercises all 5 strategy.py enums (IndicatorType, Comparison,
    PositionSizeType, StopLossType, TakeProfitType) and asserts the actual
    JSON payload contains the plain .value strings, not "ClassName.MEMBER".
    """

    def _build_strategy(self) -> StrategyConfig:
        return StrategyConfig(
            name="strenum_stability_test",
            symbols=["SPY"],
            indicators=[
                IndicatorConfig(type=IndicatorType.RSI, name="rsi_14", params={"period": 14})
            ],
            entry_rules=[
                Rule(conditions=[RuleCondition(left="rsi_14", comparison=Comparison.LT, right=30)])
            ],
            exit_rules=[
                Rule(conditions=[RuleCondition(left="rsi_14", comparison=Comparison.GT, right=70)])
            ],
            position_size=PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=10),
            stop_loss=StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05),
            take_profit=TakeProfitConfig(type=TakeProfitType.RISK_MULTIPLE, value=2.0),
        )

    def test_json_contains_plain_enum_values_not_class_qualified_names(self):
        """The actual regression StrEnum migration could silently break: if
        any code relied on str(member)'s old (str, Enum) format, the JSON
        would contain "IndicatorType.RSI" instead of "rsi". Assert the plain
        values are present and the legacy qualified format is absent."""
        config = self._build_strategy()
        json_str = config.model_dump_json()

        # Plain .value strings for every enum instance used above.
        assert '"type":"rsi"' in json_str
        assert '"comparison":"lt"' in json_str
        assert '"comparison":"gt"' in json_str
        assert '"type":"percent_equity"' in json_str
        assert '"type":"trailing_percent"' in json_str
        assert '"type":"risk_multiple"' in json_str

        # The legacy (str, Enum) str() format must never appear.
        assert "IndicatorType." not in json_str
        assert "Comparison." not in json_str
        assert "PositionSizeType." not in json_str
        assert "StopLossType." not in json_str
        assert "TakeProfitType." not in json_str

    def test_strategy_hash_is_stable_and_value_based(self):
        """strategy_hash() (bonito.trading.validation) hashes model_dump_json()
        output directly — confirm it's deterministic and built from the same
        plain-value JSON, not affected by enum repr/str differences."""
        from bonito.trading.validation import strategy_hash

        config = self._build_strategy()
        h1 = strategy_hash(config)
        h2 = strategy_hash(config)
        assert h1 == h2
        assert len(h1) == 12

        # Re-building an equivalent config (fresh enum instances) must hash
        # identically - the hash is content-based, not identity-based.
        rebuilt = self._build_strategy()
        assert strategy_hash(rebuilt) == h1

    def test_round_trip_preserves_enum_values_through_json(self):
        """Full round-trip: serialize all 5 enums, reload, confirm equality
        and that reloaded fields are still usable as their StrEnum members
        (not raw strings that merely look right)."""
        config = self._build_strategy()
        reloaded = StrategyConfig.model_validate_json(config.model_dump_json())

        assert reloaded.indicators[0].type == IndicatorType.RSI
        assert reloaded.entry_rules[0].conditions[0].comparison == Comparison.LT
        assert reloaded.exit_rules[0].conditions[0].comparison == Comparison.GT
        assert reloaded.position_size.type == PositionSizeType.PERCENT_EQUITY
        assert reloaded.stop_loss.type == StopLossType.TRAILING_PERCENT
        assert reloaded.take_profit.type == TakeProfitType.RISK_MULTIPLE

        # Byte-identical re-serialization (the actual "stability" claim).
        assert reloaded.model_dump_json() == config.model_dump_json()


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
                Rule(
                    conditions=[
                        RuleCondition(left="close", comparison=Comparison.GT, right="sma_20")
                    ]
                )
            ],
            stop_loss=StopLossConfig(type=StopLossType.PERCENT, value=0.05),
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
                Rule(conditions=[RuleCondition(left="close", comparison=Comparison.GT, right=100)])
            ],
        )

        desc = config.to_prompt_description()

        # Should have line breaks and structure
        assert "\n" in desc
        assert "Strategy:" in desc
        assert "Entry Rules:" in desc
