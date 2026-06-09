"""Tests for pure signal evaluation (bonito.trading.signals)."""

from datetime import datetime, timedelta

import numpy as np

from bonito.backtest.strategy import (
    Comparison,
    Rule,
    RuleCondition,
    StopLossConfig,
    StopLossType,
    StrategyConfig,
    TakeProfitConfig,
    TakeProfitType,
)
from bonito.data.models import BarData
from bonito.trading import signals


def make_bars(closes: list[float], symbol: str = "TEST") -> BarData:
    n = len(closes)
    start = datetime(2026, 1, 1)
    return BarData(
        symbol=symbol,
        timeframe="1d",
        timestamps=[start + timedelta(days=i) for i in range(n)],
        opens=closes,
        highs=[c * 1.01 for c in closes],
        lows=[c * 0.99 for c in closes],
        closes=closes,
        volumes=[1_000_000.0] * n,
    )


def make_strategy(**overrides) -> StrategyConfig:
    base = {
        "name": "test_strategy",
        "symbols": ["TEST"],
        "timeframe": "1d",
        "indicators": [
            {"type": "sma", "name": "sma_fast", "params": {"period": 3}},
            {"type": "sma", "name": "sma_slow", "params": {"period": 5}},
        ],
        "entry_rules": [
            {
                "conditions": [
                    {"left": "sma_fast", "comparison": "crosses_above", "right": "sma_slow"}
                ],
                "logic": "AND",
                "side": "long",
            }
        ],
        "exit_rules": [
            {
                "conditions": [
                    {"left": "sma_fast", "comparison": "crosses_below", "right": "sma_slow"}
                ],
                "logic": "AND",
                "side": "long",
            }
        ],
        "position_size": {"type": "percent_equity", "value": 10},
    }
    base.update(overrides)
    return StrategyConfig(**base)


class TestEvaluateCondition:
    def test_gt_true(self):
        cond = RuleCondition(left="close", comparison=Comparison.GT, right=100.0)
        indicators = {"close": np.array([99.0, 101.0])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is True

    def test_gt_false(self):
        cond = RuleCondition(left="close", comparison=Comparison.GT, right=100.0)
        indicators = {"close": np.array([99.0, 99.5])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is False

    def test_lt_against_indicator(self):
        cond = RuleCondition(left="rsi", comparison=Comparison.LT, right="threshold")
        indicators = {"rsi": np.array([50.0, 60.0]), "threshold": np.array([65.0, 65.0])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is True

    def test_nan_left_returns_false(self):
        cond = RuleCondition(left="sma", comparison=Comparison.GT, right=0.0)
        indicators = {"sma": np.array([np.nan, np.nan])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is False

    def test_nan_right_returns_false(self):
        cond = RuleCondition(left="close", comparison=Comparison.GT, right="sma")
        indicators = {"close": np.array([100.0, 101.0]), "sma": np.array([np.nan, np.nan])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is False

    def test_unknown_indicator_returns_false(self):
        cond = RuleCondition(left="missing", comparison=Comparison.GT, right=0.0)
        assert signals.evaluate_condition_for_bar(cond, {"close": np.array([1.0])}, 0) is False

    def test_crosses_above(self):
        cond = RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
        indicators = {
            "fast": np.array([9.0, 11.0]),
            "slow": np.array([10.0, 10.0]),
        }
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is True

    def test_crosses_above_no_cross(self):
        cond = RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
        indicators = {
            "fast": np.array([11.0, 12.0]),  # already above
            "slow": np.array([10.0, 10.0]),
        }
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is False

    def test_crosses_above_at_bar_zero_is_false(self):
        cond = RuleCondition(left="fast", comparison=Comparison.CROSSES_ABOVE, right="slow")
        indicators = {"fast": np.array([11.0]), "slow": np.array([10.0])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 0) is False

    def test_crosses_below(self):
        cond = RuleCondition(left="fast", comparison=Comparison.CROSSES_BELOW, right="slow")
        indicators = {
            "fast": np.array([11.0, 9.0]),
            "slow": np.array([10.0, 10.0]),
        }
        assert signals.evaluate_condition_for_bar(cond, indicators, 1) is True

    def test_was_above_within_lookback(self):
        cond = RuleCondition(
            left="rsi", comparison=Comparison.WAS_ABOVE, right=70.0, lookback=3
        )
        indicators = {"rsi": np.array([50.0, 75.0, 60.0, 55.0])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 3) is True

    def test_was_above_outside_lookback(self):
        cond = RuleCondition(
            left="rsi", comparison=Comparison.WAS_ABOVE, right=70.0, lookback=2
        )
        indicators = {"rsi": np.array([75.0, 60.0, 55.0, 50.0])}
        assert signals.evaluate_condition_for_bar(cond, indicators, 3) is False

    def test_crossed_above_within(self):
        cond = RuleCondition(
            left="fast", comparison=Comparison.CROSSED_ABOVE_WITHIN, right="slow", lookback=3
        )
        indicators = {
            "fast": np.array([9.0, 11.0, 12.0, 13.0]),  # crossed at idx 1
            "slow": np.array([10.0, 10.0, 10.0, 10.0]),
        }
        assert signals.evaluate_condition_for_bar(cond, indicators, 3) is True


class TestEvaluateRule:
    def test_and_logic_all_required(self):
        rule = Rule(
            conditions=[
                RuleCondition(left="a", comparison=Comparison.GT, right=0.0),
                RuleCondition(left="b", comparison=Comparison.GT, right=0.0),
            ],
            logic="AND",
            side="long",
        )
        indicators = {"a": np.array([1.0]), "b": np.array([-1.0])}
        assert signals.evaluate_rule_for_bar(rule, indicators, 0) is False
        indicators["b"] = np.array([1.0])
        assert signals.evaluate_rule_for_bar(rule, indicators, 0) is True

    def test_or_logic_any_suffices(self):
        rule = Rule(
            conditions=[
                RuleCondition(left="a", comparison=Comparison.GT, right=0.0),
                RuleCondition(left="b", comparison=Comparison.GT, right=0.0),
            ],
            logic="OR",
            side="long",
        )
        indicators = {"a": np.array([1.0]), "b": np.array([-1.0])}
        assert signals.evaluate_rule_for_bar(rule, indicators, 0) is True


class TestStopLoss:
    def test_fixed_percent_long_triggers_on_drop(self):
        cfg = StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        triggered, _ = signals.stop_loss_triggered("long", 100.0, 94.9, cfg)
        assert triggered is True

    def test_fixed_percent_long_holds_above_stop(self):
        cfg = StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        triggered, _ = signals.stop_loss_triggered("long", 100.0, 95.1, cfg)
        assert triggered is False

    def test_fixed_percent_short_triggers_on_rise(self):
        cfg = StopLossConfig(type=StopLossType.PERCENT, value=0.05)
        triggered, _ = signals.stop_loss_triggered("short", 100.0, 105.1, cfg)
        assert triggered is True

    def test_trailing_percent_tracks_high(self):
        cfg = StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05)
        # Price runs to 120, extreme follows
        triggered, extreme = signals.stop_loss_triggered("long", 100.0, 120.0, cfg, None)
        assert triggered is False
        assert extreme == 120.0
        # 5% below 120 = 114; price at 113 triggers
        triggered, extreme = signals.stop_loss_triggered("long", 100.0, 113.0, cfg, extreme)
        assert triggered is True
        assert extreme == 120.0  # extreme unchanged on the way down

    def test_trailing_does_not_mutate_caller_state(self):
        cfg = StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05)
        triggered, extreme = signals.stop_loss_triggered("long", 100.0, 110.0, cfg, 105.0)
        assert extreme == 110.0
        assert triggered is False


class TestTakeProfit:
    def test_long_triggers_at_target(self):
        cfg = TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.10)
        assert signals.take_profit_triggered("long", 100.0, 110.0, cfg) is True
        assert signals.take_profit_triggered("long", 100.0, 109.9, cfg) is False

    def test_short_triggers_on_fall(self):
        cfg = TakeProfitConfig(type=TakeProfitType.PERCENT, value=0.10)
        assert signals.take_profit_triggered("short", 100.0, 90.0, cfg) is True
        assert signals.take_profit_triggered("short", 100.0, 91.0, cfg) is False


class TestLatestEntrySignal:
    def test_crossover_fires_entry(self):
        # Downtrend then sharp reversal: fast SMA(3) crosses above slow SMA(5)
        closes = [100.0, 98.0, 96.0, 94.0, 92.0, 90.0, 95.0, 102.0]
        strategy = make_strategy()
        side, reason = signals.latest_entry_signal(strategy, make_bars(closes))
        assert side == "long"
        assert "entry rule matched" in reason

    def test_no_signal_in_steady_trend(self):
        closes = [100.0 + i for i in range(20)]  # fast stays above slow, no cross
        strategy = make_strategy()
        side, reason = signals.latest_entry_signal(strategy, make_bars(closes))
        assert side is None

    def test_insufficient_data(self):
        strategy = make_strategy()
        side, reason = signals.latest_entry_signal(strategy, make_bars([100.0]))
        assert side is None
        assert "insufficient" in reason


class TestLatestExitSignal:
    def test_cross_below_exits(self):
        # Uptrend then sharp reversal: fast SMA(3) crosses below slow SMA(5)
        closes = [90.0, 92.0, 94.0, 96.0, 98.0, 100.0, 95.0, 88.0]
        strategy = make_strategy()
        should_exit, reason, _ = signals.latest_exit_signal(
            strategy, make_bars(closes), side="long", entry_price=90.0
        )
        assert should_exit is True
        assert reason == "exit rule matched"

    def test_stop_loss_exit(self):
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 104.0, 80.0]
        strategy = make_strategy(
            stop_loss={"type": "percent", "value": 0.05},
            exit_rules=[],
        )
        should_exit, reason, _ = signals.latest_exit_signal(
            strategy, make_bars(closes), side="long", entry_price=100.0
        )
        assert should_exit is True
        assert reason == "stop loss triggered"

    def test_take_profit_exit(self):
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 115.0]
        strategy = make_strategy(
            take_profit={"type": "percent", "value": 0.10},
            exit_rules=[],
        )
        should_exit, reason, _ = signals.latest_exit_signal(
            strategy, make_bars(closes), side="long", entry_price=100.0
        )
        assert should_exit is True
        assert reason == "take profit triggered"

    def test_hold_when_nothing_fires(self):
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
        strategy = make_strategy(
            stop_loss={"type": "percent", "value": 0.05},
            take_profit={"type": "percent", "value": 0.50},
        )
        should_exit, reason, _ = signals.latest_exit_signal(
            strategy, make_bars(closes), side="long", entry_price=100.0
        )
        assert should_exit is False
        assert reason == "hold"

    def test_trailing_extreme_propagates(self):
        closes = [100.0, 105.0, 110.0, 115.0, 120.0, 118.0, 117.0, 116.0]
        strategy = make_strategy(
            stop_loss={"type": "trailing_percent", "value": 0.10},
            exit_rules=[],
        )
        should_exit, reason, extreme = signals.latest_exit_signal(
            strategy, make_bars(closes), side="long", entry_price=100.0, tracked_extreme=119.0
        )
        assert should_exit is False
        assert extreme == 119.0  # last close 116 didn't beat tracked 119


class TestBotParity:
    """The bot must produce identical results through its delegating methods."""

    def test_bot_delegates_to_signals(self):
        from unittest.mock import MagicMock

        from bonito.trading.bot import TradingBot

        bot = MagicMock(spec=TradingBot)
        # Bind real methods to the mock instance
        rule = Rule(
            conditions=[RuleCondition(left="a", comparison=Comparison.GT, right=0.0)],
            logic="AND",
            side="long",
        )
        indicators = {"a": np.array([1.0])}
        result = TradingBot._evaluate_rule_for_bar(bot, rule, indicators, 0)
        assert result is True
        assert result == signals.evaluate_rule_for_bar(rule, indicators, 0)
