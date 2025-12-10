"""Vectorized backtesting engine."""

from datetime import datetime
from typing import Any

import numpy as np

from bonito.backtest.indicators import compute_indicators
from bonito.backtest.models import (
    BacktestConfig,
    BacktestResult,
    OrderSide,
    PerformanceMetrics,
    Trade,
)
from bonito.backtest.strategy import Comparison, Rule, StopLossConfig, StrategyConfig
from bonito.data.models import BarData


class BacktestEngine:
    """Vectorized backtesting engine.

    Optimized for speed - uses numpy operations where possible.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        """Initialize the backtest engine.

        Args:
            config: Backtest configuration. Uses defaults if not provided.
        """
        self.config = config or BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
        )

    def run(
        self,
        strategy: StrategyConfig,
        data: BarData,
    ) -> BacktestResult:
        """Run a backtest.

        Args:
            strategy: Strategy configuration
            data: Historical bar data

        Returns:
            BacktestResult with metrics and trade history
        """
        # Compute indicators
        indicators = compute_indicators(data, strategy.indicators)

        # Generate signals
        entry_signals = self._evaluate_rules(strategy.entry_rules, indicators)
        exit_signals = (
            self._evaluate_rules(strategy.exit_rules, indicators)
            if strategy.exit_rules
            else np.zeros(len(data), dtype=bool)
        )

        # Run simulation
        trades, equity_curve = self._simulate(
            strategy=strategy,
            data=data,
            indicators=indicators,
            entry_signals=entry_signals,
            exit_signals=exit_signals,
        )

        # Calculate metrics
        metrics = self._calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self.config.initial_capital,
        )

        # Calculate drawdown curve
        equity_arr = np.array(equity_curve)
        peak = np.maximum.accumulate(equity_arr)
        drawdown_curve = (equity_arr - peak) / peak

        return BacktestResult(
            strategy_name=strategy.name,
            symbol=strategy.symbols[0],  # MVP: single symbol
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_capital=equity_curve[-1] if equity_curve else self.config.initial_capital,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            equity_dates=data.timestamps[: len(equity_curve)],
            drawdown_curve=drawdown_curve.tolist(),
            total_commission=sum(
                t.entry_price * t.quantity * self.config.commission * 2 for t in trades
            ),
            total_slippage=sum(
                t.entry_price * t.quantity * self.config.slippage * 2 for t in trades
            ),
        )

    def _evaluate_rules(
        self,
        rules: list[Rule],
        indicators: dict[str, np.ndarray],
    ) -> np.ndarray:
        """Evaluate rules to generate signals.

        Returns a boolean array - True where ANY rule is satisfied.
        """
        n = len(next(iter(indicators.values())))
        any_rule_triggered = np.zeros(n, dtype=bool)

        for rule in rules:
            rule_result = self._evaluate_single_rule(rule, indicators)
            any_rule_triggered |= rule_result

        return any_rule_triggered

    def _evaluate_single_rule(
        self,
        rule: Rule,
        indicators: dict[str, np.ndarray],
    ) -> np.ndarray:
        """Evaluate a single rule with multiple conditions."""
        n = len(next(iter(indicators.values())))

        if rule.logic == "AND":
            result = np.ones(n, dtype=bool)
            for condition in rule.conditions:
                cond_result = self._evaluate_condition(condition, indicators)
                result &= cond_result
        else:  # OR
            result = np.zeros(n, dtype=bool)
            for condition in rule.conditions:
                cond_result = self._evaluate_condition(condition, indicators)
                result |= cond_result

        return result

    def _evaluate_condition(
        self,
        condition,  # RuleCondition
        indicators: dict[str, np.ndarray],
    ) -> np.ndarray:
        """Evaluate a single condition."""
        # Get left operand
        left = indicators.get(condition.left)
        if left is None:
            raise ValueError(f"Unknown indicator: {condition.left}")

        # Get right operand
        right: float | np.ndarray
        if isinstance(condition.right, int | float):
            right = condition.right
        else:
            right_indicator = indicators.get(condition.right)
            if right_indicator is None:
                # Try to parse as float
                try:
                    right = float(condition.right)
                except ValueError as err:
                    raise ValueError(f"Unknown indicator: {condition.right}") from err
            else:
                right = right_indicator

        # Apply comparison
        if condition.comparison == Comparison.GT:
            return left > right
        elif condition.comparison == Comparison.GTE:
            return left >= right
        elif condition.comparison == Comparison.LT:
            return left < right
        elif condition.comparison == Comparison.LTE:
            return left <= right
        elif condition.comparison == Comparison.EQ:
            return np.isclose(left, right)
        elif condition.comparison == Comparison.CROSSES_ABOVE:
            right_arr = np.full_like(left, right) if isinstance(right, int | float) else right
            crosses = np.zeros(len(left), dtype=bool)
            crosses[1:] = (left[:-1] <= right_arr[:-1]) & (left[1:] > right_arr[1:])
            return crosses
        elif condition.comparison == Comparison.CROSSES_BELOW:
            right_arr = np.full_like(left, right) if isinstance(right, int | float) else right
            crosses = np.zeros(len(left), dtype=bool)
            crosses[1:] = (left[:-1] >= right_arr[:-1]) & (left[1:] < right_arr[1:])
            return crosses
        else:
            raise ValueError(f"Unknown comparison: {condition.comparison}")

    def _simulate(
        self,
        strategy: StrategyConfig,
        data: BarData,
        indicators: dict[str, np.ndarray],
        entry_signals: np.ndarray,
        exit_signals: np.ndarray,
    ) -> tuple[list[Trade], list[float]]:
        """Run the simulation loop."""
        trades: list[Trade] = []
        equity_curve: list[float] = []

        cash = self.config.initial_capital
        position: dict[str, Any] | None = None  # Current position

        closes = data.close
        opens = data.open
        highs = data.high
        timestamps = data.timestamps

        # Pre-compute ATR if needed for trailing ATR stops
        atr_values: np.ndarray | None = None
        if strategy.stop_loss and strategy.stop_loss.type.value == "trailing_atr":
            atr_values = self._compute_atr(data, strategy.stop_loss.atr_period)

        for i in range(1, len(data)):  # Start at 1 to use previous bar for signals
            current_equity = cash
            if position:
                current_equity += position["quantity"] * closes[i]
            equity_curve.append(current_equity)

            # Check exit conditions if in position
            if position:
                should_exit = False
                exit_reason = "signal"

                # Update trailing stop state (high water mark, current stop)
                if strategy.stop_loss:
                    position = self._update_trailing_stop(
                        position, strategy.stop_loss, highs[i], closes[i], atr_values, i
                    )

                # Check exit signal
                if exit_signals[i - 1]:  # Signal from previous bar
                    should_exit = True
                    exit_reason = "signal"

                # Check stop loss (fixed or trailing)
                if strategy.stop_loss and not should_exit:
                    stop_price = self._get_current_stop_price(
                        position, strategy.stop_loss, atr_values, i
                    )
                    if stop_price is not None and closes[i] <= stop_price:
                        should_exit = True
                        exit_reason = "stop_loss"

                # Check take profit
                if (
                    strategy.take_profit
                    and not should_exit
                    and strategy.take_profit.type.value == "percent"
                ):
                    tp_price = position["entry_price"] * (1 + strategy.take_profit.value)
                    if closes[i] >= tp_price:
                        should_exit = True
                        exit_reason = "take_profit"

                if should_exit:
                    # Exit at open of current bar (signal was on previous bar)
                    exit_price = opens[i] * (1 - self.config.slippage)
                    pnl = (exit_price - position["entry_price"]) * position["quantity"]
                    pnl -= exit_price * position["quantity"] * self.config.commission

                    trades.append(
                        Trade(
                            symbol=strategy.symbols[0],
                            side=OrderSide.BUY,
                            entry_time=position["entry_time"],
                            entry_price=position["entry_price"],
                            exit_time=timestamps[i],
                            exit_price=exit_price,
                            quantity=position["quantity"],
                            pnl=pnl,
                            pnl_percent=pnl / (position["entry_price"] * position["quantity"]),
                            exit_reason=exit_reason,
                        )
                    )

                    cash += exit_price * position["quantity"]
                    cash += pnl
                    position = None

            # Check entry conditions if not in position
            if position is None and entry_signals[i - 1]:
                # Calculate position size
                entry_price = opens[i] * (1 + self.config.slippage)

                if strategy.position_size.type.value == "percent_equity":
                    # Reserve cash for commission when using percent_equity
                    # Use 99.5% of target to ensure we have buffer for commission + float errors
                    pct = min(strategy.position_size.value, 99.5) / 100
                    position_value = current_equity * pct
                elif strategy.position_size.type.value == "fixed_value":
                    position_value = strategy.position_size.value
                else:  # fixed_quantity
                    position_value = strategy.position_size.value * opens[i]

                quantity = position_value / entry_price
                commission = entry_price * quantity * self.config.commission
                total_cost = position_value + commission

                if cash >= total_cost:
                    position = {
                        "entry_time": timestamps[i],
                        "entry_price": entry_price,
                        "quantity": quantity,
                        # Trailing stop state
                        "highest_price": entry_price,  # Start tracking from entry
                        "breakeven_triggered": False,  # For breakeven stops
                    }
                    cash -= entry_price * quantity + commission

        # Close any open position at end
        if position:
            exit_price = closes[-1]
            pnl = (exit_price - position["entry_price"]) * position["quantity"]

            trades.append(
                Trade(
                    symbol=strategy.symbols[0],
                    side=OrderSide.BUY,
                    entry_time=position["entry_time"],
                    entry_price=position["entry_price"],
                    exit_time=timestamps[-1],
                    exit_price=exit_price,
                    quantity=position["quantity"],
                    pnl=pnl,
                    pnl_percent=pnl / (position["entry_price"] * position["quantity"]),
                    exit_reason="end_of_data",
                )
            )

            cash += exit_price * position["quantity"] + pnl
            equity_curve.append(cash)

        return trades, equity_curve

    def _compute_atr(self, data: BarData, period: int) -> np.ndarray:
        """Compute Average True Range for trailing ATR stops."""
        highs = data.high
        lows = data.low
        closes = data.close

        # True Range
        tr1 = highs - lows
        tr2 = np.abs(highs - np.roll(closes, 1))
        tr3 = np.abs(lows - np.roll(closes, 1))
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        tr[0] = tr1[0]  # First bar has no previous close

        # ATR (simple moving average of TR)
        atr = np.zeros_like(tr)
        for i in range(len(tr)):
            if i < period:
                atr[i] = np.mean(tr[: i + 1])
            else:
                atr[i] = np.mean(tr[i - period + 1 : i + 1])

        return atr

    def _update_trailing_stop(
        self,
        position: dict[str, Any],
        stop_config: "StopLossConfig",
        current_high: float,
        current_close: float,
        atr_values: np.ndarray | None,
        bar_index: int,
    ) -> dict[str, Any]:
        """Update trailing stop state for the current bar.

        Updates highest_price for trailing stops, and breakeven_triggered for breakeven stops.
        """
        stop_type = stop_config.type.value

        if stop_type in ("trailing_percent", "trailing_atr"):
            # Update high water mark (ratchet effect - never moves down)
            new_high = max(position["highest_price"], current_high)
            position["highest_price"] = new_high

        elif stop_type == "breakeven":
            # Check if profit threshold reached to trigger breakeven
            if not position["breakeven_triggered"]:
                entry_price = position["entry_price"]
                trigger_pct = stop_config.trigger_percent or 0.05
                trigger_price = entry_price * (1 + trigger_pct)

                if current_close >= trigger_price:
                    position["breakeven_triggered"] = True

        return position

    def _get_current_stop_price(
        self,
        position: dict[str, Any],
        stop_config: "StopLossConfig",
        atr_values: np.ndarray | None,
        bar_index: int,
    ) -> float | None:
        """Calculate the current stop price based on stop type."""
        stop_type = stop_config.type.value
        entry_price = position["entry_price"]

        if stop_type == "percent":
            # Fixed percent stop
            return entry_price * (1 - stop_config.value)

        elif stop_type == "trailing_percent":
            # Trailing percent stop - trails below high water mark
            highest_price = position["highest_price"]
            return highest_price * (1 - stop_config.value)

        elif stop_type == "trailing_atr":
            # Trailing ATR stop - trails ATR multiple below high water mark
            if atr_values is None:
                return None
            highest_price = position["highest_price"]
            atr = atr_values[bar_index]
            return highest_price - (stop_config.value * atr)

        elif stop_type == "breakeven":
            # Breakeven stop - only active after trigger
            if position["breakeven_triggered"]:
                # Stop at entry price (breakeven)
                return entry_price + stop_config.value  # value can add buffer
            return None  # Not triggered yet, no stop

        elif stop_type == "atr":
            # Fixed ATR stop (not trailing)
            if atr_values is None:
                return None
            atr = atr_values[bar_index]
            return entry_price - (stop_config.value * atr)

        elif stop_type == "fixed":
            # Fixed price stop
            return stop_config.value

        return None

    def _calculate_metrics(
        self,
        trades: list[Trade],
        equity_curve: list[float],
        initial_capital: float,
    ) -> PerformanceMetrics:
        """Calculate performance metrics."""
        if not trades:
            return PerformanceMetrics(
                total_return=0.0,
                annualized_return=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_duration_days=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                average_win=0.0,
                average_loss=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                avg_exposure=0.0,
                calmar_ratio=0.0,
            )

        equity = np.array(equity_curve)

        # Returns
        total_return = (equity[-1] - initial_capital) / initial_capital
        n_periods = len(equity)
        annualized_return = (1 + total_return) ** (252 / max(n_periods, 1)) - 1

        # Daily returns
        daily_returns = np.diff(equity) / equity[:-1]

        # Sharpe ratio (assuming 0% risk-free rate)
        if len(daily_returns) > 0 and np.std(daily_returns) > 0:
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        # Sortino ratio
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0 and np.std(negative_returns) > 0:
            sortino_ratio = np.mean(daily_returns) / np.std(negative_returns) * np.sqrt(252)
        else:
            sortino_ratio = 0.0

        # Drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = abs(float(np.min(drawdown)))

        # Max drawdown duration
        in_drawdown = drawdown < 0
        max_dd_duration = 0
        current_dd_duration = 0
        for is_dd in in_drawdown:
            if is_dd:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0

        # Trade statistics
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]

        total_trades = len(trades)
        winning_trades = len(winning)
        losing_trades = len(losing)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        average_win = np.mean([t.pnl_percent for t in winning]) if winning else 0.0
        average_loss = np.mean([t.pnl_percent for t in losing]) if losing else 0.0

        largest_win = max((t.pnl for t in trades), default=0.0)
        largest_loss = min((t.pnl for t in trades), default=0.0)

        # Calmar ratio
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0

        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration_days=max_dd_duration,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=min(profit_factor, 999.99),  # Cap for display
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_exposure=0.5,  # TODO: Calculate properly
            calmar_ratio=calmar_ratio,
        )
