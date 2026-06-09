"""Pure signal evaluation for live trading.

Shared by TradingBot and the daily live runner so both execute identical
rule logic. No broker, network, or storage dependencies — every function
here is deterministic over its inputs, which is what makes the live
pipeline unit-testable.
"""

import logging
from datetime import UTC, datetime
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from bonito.backtest.indicators import compute_indicators
from bonito.backtest.strategy import (
    Comparison,
    Rule,
    RuleCondition,
    StopLossConfig,
    StrategyConfig,
    TakeProfitConfig,
)
from bonito.data.models import BarData

logger = logging.getLogger(__name__)


class TradeIntent(BaseModel):
    """A single intended trade, produced by signal evaluation.

    Intents are the handoff between Bonito's signal code and whatever
    executes them (paper ledger or a Claude session placing Robinhood
    orders). They carry everything needed to review the trade.
    """

    symbol: str
    side: Literal["buy", "sell"]
    dollar_amount: float | None = Field(
        default=None, description="Notional for dollar-based (fractional) orders"
    )
    quantity: float | None = Field(
        default=None, description="Share quantity for exits (sell entire position)"
    )
    reason: str
    signal_price: float = Field(..., description="Close price when the signal fired")
    signal_date: datetime
    strategy_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def evaluate_condition_for_bar(
    condition: RuleCondition,
    indicators: dict[str, np.ndarray],
    bar_idx: int,
) -> bool:
    """Evaluate a single condition at one bar index."""
    left_array = indicators.get(condition.left)
    if left_array is None:
        logger.warning(f"Unknown indicator: {condition.left}")
        return False

    if np.isnan(left_array[bar_idx]):
        return False

    left_val = left_array[bar_idx]

    right_array: np.ndarray | None = None
    if isinstance(condition.right, int | float):
        right_val = float(condition.right)
    else:
        right_array = indicators.get(condition.right)
        if right_array is None:
            try:
                right_val = float(condition.right)
            except ValueError:
                logger.warning(f"Unknown indicator: {condition.right}")
                return False
        else:
            if np.isnan(right_array[bar_idx]):
                return False
            right_val = right_array[bar_idx]

    comparison = condition.comparison
    if comparison == Comparison.GT:
        return bool(left_val > right_val)
    elif comparison == Comparison.GTE:
        return bool(left_val >= right_val)
    elif comparison == Comparison.LT:
        return bool(left_val < right_val)
    elif comparison == Comparison.LTE:
        return bool(left_val <= right_val)
    elif comparison == Comparison.EQ:
        return bool(np.isclose(left_val, right_val))
    elif comparison == Comparison.CROSSES_ABOVE:
        if bar_idx < 1:
            return False
        prev_left = left_array[bar_idx - 1]
        prev_right = right_val if right_array is None else right_array[bar_idx - 1]
        return bool(prev_left <= prev_right and left_val > right_val)
    elif comparison == Comparison.CROSSES_BELOW:
        if bar_idx < 1:
            return False
        prev_left = left_array[bar_idx - 1]
        prev_right = right_val if right_array is None else right_array[bar_idx - 1]
        return bool(prev_left >= prev_right and left_val < right_val)
    elif comparison == Comparison.WAS_ABOVE:
        lookback = condition.lookback or 5
        start_idx = max(0, bar_idx - lookback + 1)
        window = left_array[start_idx : bar_idx + 1]
        if right_array is None:
            return bool(np.any(window > right_val))
        return bool(np.any(window > right_array[start_idx : bar_idx + 1]))
    elif comparison == Comparison.WAS_BELOW:
        lookback = condition.lookback or 5
        start_idx = max(0, bar_idx - lookback + 1)
        window = left_array[start_idx : bar_idx + 1]
        if right_array is None:
            return bool(np.any(window < right_val))
        return bool(np.any(window < right_array[start_idx : bar_idx + 1]))
    elif comparison == Comparison.CROSSED_ABOVE_WITHIN:
        lookback = condition.lookback or 5
        start_idx = max(1, bar_idx - lookback + 1)
        for i in range(start_idx, bar_idx + 1):
            prev_left = left_array[i - 1]
            curr_left = left_array[i]
            if right_array is None:
                if prev_left <= right_val and curr_left > right_val:
                    return True
            else:
                if prev_left <= right_array[i - 1] and curr_left > right_array[i]:
                    return True
        return False
    elif comparison == Comparison.CROSSED_BELOW_WITHIN:
        lookback = condition.lookback or 5
        start_idx = max(1, bar_idx - lookback + 1)
        for i in range(start_idx, bar_idx + 1):
            prev_left = left_array[i - 1]
            curr_left = left_array[i]
            if right_array is None:
                if prev_left >= right_val and curr_left < right_val:
                    return True
            else:
                if prev_left >= right_array[i - 1] and curr_left < right_array[i]:
                    return True
        return False
    else:
        logger.warning(f"Unknown comparison: {comparison}")
        return False


def evaluate_rule_for_bar(
    rule: Rule,
    indicators: dict[str, np.ndarray],
    bar_idx: int,
) -> bool:
    """Evaluate a rule (AND/OR of conditions) at one bar index."""
    results = [evaluate_condition_for_bar(c, indicators, bar_idx) for c in rule.conditions]
    if rule.logic == "AND":
        return all(results)
    return any(results)


def stop_loss_triggered(
    side: Literal["long", "short"],
    entry_price: float,
    current_price: float,
    stop_config: StopLossConfig,
    tracked_extreme: float | None = None,
) -> tuple[bool, float]:
    """Check a stop loss without mutating any state.

    Args:
        tracked_extreme: For trailing stops, the highest (long) or lowest
            (short) price seen since entry, BEFORE observing current_price.

    Returns:
        (triggered, new_tracked_extreme) — callers persist the new extreme.
    """
    stop_type = stop_config.type.value
    is_short = side == "short"
    extreme = tracked_extreme if tracked_extreme is not None else entry_price

    if stop_type == "percent":
        if is_short:
            return current_price >= entry_price * (1 + stop_config.value), extreme
        return current_price <= entry_price * (1 - stop_config.value), extreme

    if stop_type == "trailing_percent":
        if is_short:
            extreme = min(extreme, current_price)
            return current_price >= extreme * (1 + stop_config.value), extreme
        extreme = max(extreme, current_price)
        return current_price <= extreme * (1 - stop_config.value), extreme

    return False, extreme


def take_profit_triggered(
    side: Literal["long", "short"],
    entry_price: float,
    current_price: float,
    tp_config: TakeProfitConfig,
) -> bool:
    """Check a take profit target."""
    if tp_config.type.value != "percent":
        return False
    # Epsilon absorbs float error so a fill exactly at target triggers
    # (e.g. 100 * 1.10 == 110.00000000000001).
    eps = 1e-9
    if side == "short":
        return current_price <= entry_price * (1 - tp_config.value) + eps
    return current_price >= entry_price * (1 + tp_config.value) - eps


def latest_entry_signal(
    strategy: StrategyConfig,
    data: BarData,
) -> tuple[Literal["long", "short"] | None, str]:
    """Evaluate entry rules at the most recent bar.

    Returns:
        (side, reason). side is None when no entry rule fires.
    """
    if len(data) < 2:
        return None, "insufficient data"

    indicators = compute_indicators(data, strategy.indicators)
    latest_idx = len(data) - 1

    for rule in strategy.entry_rules:
        if evaluate_rule_for_bar(rule, indicators, latest_idx):
            conditions = ", ".join(
                f"{c.left} {c.comparison.value} {c.right}" for c in rule.conditions
            )
            return rule.side, f"entry rule matched: {conditions}"

    return None, "no entry rule matched"


def latest_exit_signal(
    strategy: StrategyConfig,
    data: BarData,
    side: Literal["long", "short"],
    entry_price: float,
    tracked_extreme: float | None = None,
) -> tuple[bool, str, float]:
    """Evaluate exit rules, stop loss, and take profit at the most recent bar.

    Returns:
        (should_exit, reason, new_tracked_extreme).
    """
    indicators = compute_indicators(data, strategy.indicators)
    latest_idx = len(data) - 1
    current_price = data.closes[latest_idx]
    extreme = tracked_extreme if tracked_extreme is not None else entry_price

    for rule in strategy.exit_rules:
        if rule.side == side and evaluate_rule_for_bar(rule, indicators, latest_idx):
            return True, "exit rule matched", extreme

    if strategy.stop_loss:
        triggered, extreme = stop_loss_triggered(
            side, entry_price, current_price, strategy.stop_loss, extreme
        )
        if triggered:
            return True, "stop loss triggered", extreme

    if strategy.take_profit and take_profit_triggered(
        side, entry_price, current_price, strategy.take_profit
    ):
        return True, "take profit triggered", extreme

    return False, "hold", extreme
