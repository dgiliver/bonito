"""Plugin Adapter - Bridge between plugin signals and backtest engine.

This module provides the adapter layer that allows plugins to be executed
through the standard backtest engine infrastructure, including:
- Position sizing
- Stop losses and take profits
- P&L calculation
- Trade tracking
"""

from datetime import datetime
from typing import Any

import numpy as np

from bonito.backtest.models import (
    BacktestConfig,
    BacktestResult,
    OrderSide,
    PerformanceMetrics,
    Trade,
)
from bonito.backtest.plugins import SignalOutput, StrategyPlugin
from bonito.data.models import BarData


class PluginAdapter:
    """Adapter to run plugin strategies through the backtest engine.

    This class takes plugin signal outputs and runs them through a simulation
    loop similar to the main BacktestEngine, but using the pre-computed signals
    from the plugin instead of the DSL rule evaluation.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        """Initialize the plugin adapter.

        Args:
            config: Backtest configuration. Uses defaults if not provided.
        """
        self.config = config or BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
        )

    def run(
        self,
        plugin: StrategyPlugin,
        data: BarData,
        params: dict[str, Any] | None = None,
        position_size_pct: float = 100.0,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> BacktestResult:
        """Run a backtest using a plugin's signals.

        Args:
            plugin: The strategy plugin to execute
            data: Historical bar data
            params: Parameters to pass to the plugin (defaults will be used if not provided)
            position_size_pct: Position size as percentage of equity (default: 100%)
            stop_loss_pct: Optional stop loss percentage (e.g., 0.05 for 5%)
            take_profit_pct: Optional take profit percentage

        Returns:
            BacktestResult with metrics and trade history
        """
        # Validate and fill in default parameters
        validated_params = plugin.validate_params(params or {})

        # Compute signals from the plugin
        signals = plugin.compute_signals(data, validated_params)

        # Run the simulation
        trades, equity_curve = self._simulate(
            data=data,
            signals=signals,
            position_size_pct=position_size_pct,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        # Calculate metrics
        metrics = self._calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self.config.initial_capital,
        )

        # Calculate drawdown curve
        equity_arr = (
            np.array(equity_curve) if equity_curve else np.array([self.config.initial_capital])
        )
        peak = np.maximum.accumulate(equity_arr)
        drawdown_curve = ((equity_arr - peak) / peak).tolist()

        return BacktestResult(
            strategy_name=f"plugin:{plugin.name}",
            symbol=data.symbol,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_capital=equity_curve[-1] if equity_curve else self.config.initial_capital,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            equity_dates=data.timestamps[: len(equity_curve)],
            drawdown_curve=drawdown_curve,
            total_commission=sum(
                t.entry_price * t.quantity * self.config.commission * 2 for t in trades
            ),
            total_slippage=sum(
                t.entry_price * t.quantity * self.config.slippage * 2 for t in trades
            ),
        )

    def _simulate(
        self,
        data: BarData,
        signals: SignalOutput,
        position_size_pct: float,
        stop_loss_pct: float | None,
        take_profit_pct: float | None,
    ) -> tuple[list[Trade], list[float]]:
        """Run the simulation loop with plugin signals.

        Args:
            data: Bar data
            signals: Pre-computed signals from plugin
            position_size_pct: Position size percentage
            stop_loss_pct: Optional stop loss percentage
            take_profit_pct: Optional take profit percentage

        Returns:
            Tuple of (trades list, equity curve)
        """
        trades: list[Trade] = []
        equity_curve: list[float] = []

        cash = self.config.initial_capital
        position: dict[str, Any] | None = None

        closes = data.close
        opens = data.open
        timestamps = data.timestamps

        entry_signals = signals.entries
        exit_signals = signals.exits
        entry_side = signals.entry_side

        for i in range(1, len(data)):
            current_equity = cash
            if position:
                # Mark-to-market
                if position["side"] == "long":
                    current_equity += position["quantity"] * closes[i]
                else:
                    unrealized_pnl = (position["entry_price"] - closes[i]) * position["quantity"]
                    current_equity += (
                        position["entry_price"] * position["quantity"] + unrealized_pnl
                    )
            equity_curve.append(current_equity)

            # Check exit conditions
            if position:
                should_exit = False
                exit_reason = "signal"
                is_short = position["side"] == "short"

                # Exit signal from plugin
                if exit_signals[i - 1]:
                    should_exit = True
                    exit_reason = "signal"

                # Stop loss
                if stop_loss_pct is not None and not should_exit:
                    entry_price = position["entry_price"]
                    if is_short:
                        stop_price = entry_price * (1 + stop_loss_pct)
                        if closes[i] >= stop_price:
                            should_exit = True
                            exit_reason = "stop_loss"
                    else:
                        stop_price = entry_price * (1 - stop_loss_pct)
                        if closes[i] <= stop_price:
                            should_exit = True
                            exit_reason = "stop_loss"

                # Take profit
                if take_profit_pct is not None and not should_exit:
                    entry_price = position["entry_price"]
                    if is_short:
                        tp_price = entry_price * (1 - take_profit_pct)
                        if closes[i] <= tp_price:
                            should_exit = True
                            exit_reason = "take_profit"
                    else:
                        tp_price = entry_price * (1 + take_profit_pct)
                        if closes[i] >= tp_price:
                            should_exit = True
                            exit_reason = "take_profit"

                if should_exit:
                    if is_short:
                        exit_price = opens[i] * (1 + self.config.slippage)
                        pnl = (position["entry_price"] - exit_price) * position["quantity"]
                    else:
                        exit_price = opens[i] * (1 - self.config.slippage)
                        pnl = (exit_price - position["entry_price"]) * position["quantity"]

                    pnl -= exit_price * position["quantity"] * self.config.commission

                    trades.append(
                        Trade(
                            symbol=data.symbol,
                            side=OrderSide.SELL if is_short else OrderSide.BUY,
                            entry_time=position["entry_time"],
                            entry_price=position["entry_price"],
                            exit_time=timestamps[i],
                            exit_price=exit_price,
                            quantity=position["quantity"],
                            pnl=pnl,
                            pnl_percent=pnl / (position["entry_price"] * position["quantity"]),
                            exit_reason=exit_reason,
                            position_side=position["side"],
                        )
                    )

                    if is_short:
                        cash += position["entry_price"] * position["quantity"] + pnl
                    else:
                        cash += exit_price * position["quantity"] + pnl

                    position = None

            # Check entry conditions
            if position is None and entry_signals[i - 1]:
                if entry_side == "long":
                    entry_price = opens[i] * (1 + self.config.slippage)
                else:
                    entry_price = opens[i] * (1 - self.config.slippage)

                pct = min(position_size_pct, 99.5) / 100
                position_value = current_equity * pct

                quantity = position_value / entry_price
                commission = entry_price * quantity * self.config.commission
                total_cost = position_value + commission

                if cash >= total_cost:
                    position = {
                        "entry_time": timestamps[i],
                        "entry_price": entry_price,
                        "quantity": quantity,
                        "side": entry_side,
                    }
                    if entry_side == "long":
                        cash -= entry_price * quantity + commission
                    else:
                        cash -= commission

        # Close any open position at end
        if position:
            is_short = position["side"] == "short"
            exit_price = closes[-1]

            if is_short:
                pnl = (position["entry_price"] - exit_price) * position["quantity"]
            else:
                pnl = (exit_price - position["entry_price"]) * position["quantity"]

            trades.append(
                Trade(
                    symbol=data.symbol,
                    side=OrderSide.SELL if is_short else OrderSide.BUY,
                    entry_time=position["entry_time"],
                    entry_price=position["entry_price"],
                    exit_time=timestamps[-1],
                    exit_price=exit_price,
                    quantity=position["quantity"],
                    pnl=pnl,
                    pnl_percent=pnl / (position["entry_price"] * position["quantity"]),
                    exit_reason="end_of_data",
                    position_side=position["side"],
                )
            )

            if is_short:
                cash += position["entry_price"] * position["quantity"] + pnl
            else:
                cash += exit_price * position["quantity"] + pnl
            equity_curve.append(cash)

        return trades, equity_curve

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

        total_return = (equity[-1] - initial_capital) / initial_capital
        n_periods = len(equity)
        annualized_return = (1 + total_return) ** (252 / max(n_periods, 1)) - 1

        daily_returns = np.diff(equity) / equity[:-1]

        if len(daily_returns) > 0 and np.std(daily_returns) > 0:
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0 and np.std(negative_returns) > 0:
            sortino_ratio = np.mean(daily_returns) / np.std(negative_returns) * np.sqrt(252)
        else:
            sortino_ratio = 0.0

        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = abs(float(np.min(drawdown)))

        in_drawdown = drawdown < 0
        max_dd_duration = 0
        current_dd_duration = 0
        for is_dd in in_drawdown:
            if is_dd:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0

        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]

        total_trades = len(trades)
        winning_trades = len(winning)
        losing_trades = len(losing)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        average_win = float(np.mean([t.pnl_percent for t in winning])) if winning else 0.0
        average_loss = float(np.mean([t.pnl_percent for t in losing])) if losing else 0.0

        largest_win = max((t.pnl for t in trades), default=0.0)
        largest_loss = min((t.pnl for t in trades), default=0.0)

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
            profit_factor=min(profit_factor, 999.99),
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_exposure=0.5,
            calmar_ratio=calmar_ratio,
        )
