"""Vectorized backtesting engine."""

from datetime import datetime, timedelta

import numpy as np

from quant_agent.backtest.indicators import compute_indicators
from quant_agent.backtest.models import (
    BacktestConfig,
    BacktestResult,
    OrderSide,
    PerformanceMetrics,
    Trade,
)
from quant_agent.backtest.strategy import Comparison, Rule, StrategyConfig
from quant_agent.data.models import BarData


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
        exit_signals = self._evaluate_rules(strategy.exit_rules, indicators) if strategy.exit_rules else np.zeros(len(data), dtype=bool)
        
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
            equity_dates=data.timestamps[:len(equity_curve)],
            drawdown_curve=drawdown_curve.tolist(),
            total_commission=sum(
                t.entry_price * t.quantity * self.config.commission * 2 
                for t in trades
            ),
            total_slippage=sum(
                t.entry_price * t.quantity * self.config.slippage * 2 
                for t in trades
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
        if isinstance(condition.right, (int, float)):
            right = condition.right
        else:
            right = indicators.get(condition.right)
            if right is None:
                # Try to parse as float
                try:
                    right = float(condition.right)
                except ValueError:
                    raise ValueError(f"Unknown indicator: {condition.right}")
        
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
            if isinstance(right, (int, float)):
                right_arr = np.full_like(left, right)
            else:
                right_arr = right
            crosses = np.zeros(len(left), dtype=bool)
            crosses[1:] = (left[:-1] <= right_arr[:-1]) & (left[1:] > right_arr[1:])
            return crosses
        elif condition.comparison == Comparison.CROSSES_BELOW:
            if isinstance(right, (int, float)):
                right_arr = np.full_like(left, right)
            else:
                right_arr = right
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
        position: dict | None = None  # Current position
        
        closes = data.close
        opens = data.open
        timestamps = data.timestamps
        
        for i in range(1, len(data)):  # Start at 1 to use previous bar for signals
            current_equity = cash
            if position:
                current_equity += position["quantity"] * closes[i]
            equity_curve.append(current_equity)
            
            # Check exit conditions if in position
            if position:
                should_exit = False
                exit_reason = "signal"
                
                # Check exit signal
                if exit_signals[i - 1]:  # Signal from previous bar
                    should_exit = True
                    exit_reason = "signal"
                
                # Check stop loss
                if strategy.stop_loss and not should_exit:
                    if strategy.stop_loss.type.value == "percent":
                        stop_price = position["entry_price"] * (1 - strategy.stop_loss.value)
                        if closes[i] <= stop_price:
                            should_exit = True
                            exit_reason = "stop_loss"
                
                # Check take profit
                if strategy.take_profit and not should_exit:
                    if strategy.take_profit.type.value == "percent":
                        tp_price = position["entry_price"] * (1 + strategy.take_profit.value)
                        if closes[i] >= tp_price:
                            should_exit = True
                            exit_reason = "take_profit"
                
                if should_exit:
                    # Exit at open of current bar (signal was on previous bar)
                    exit_price = opens[i] * (1 - self.config.slippage)
                    pnl = (exit_price - position["entry_price"]) * position["quantity"]
                    pnl -= exit_price * position["quantity"] * self.config.commission
                    
                    trades.append(Trade(
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
                    ))
                    
                    cash += exit_price * position["quantity"]
                    cash += pnl
                    position = None
            
            # Check entry conditions if not in position
            if position is None and entry_signals[i - 1]:
                # Calculate position size
                if strategy.position_size.type.value == "percent_equity":
                    position_value = current_equity * (strategy.position_size.value / 100)
                elif strategy.position_size.type.value == "fixed_value":
                    position_value = strategy.position_size.value
                else:  # fixed_quantity
                    position_value = strategy.position_size.value * opens[i]
                
                entry_price = opens[i] * (1 + self.config.slippage)
                quantity = position_value / entry_price
                commission = entry_price * quantity * self.config.commission
                
                if cash >= position_value + commission:
                    position = {
                        "entry_time": timestamps[i],
                        "entry_price": entry_price,
                        "quantity": quantity,
                    }
                    cash -= entry_price * quantity + commission
        
        # Close any open position at end
        if position:
            exit_price = closes[-1]
            pnl = (exit_price - position["entry_price"]) * position["quantity"]
            
            trades.append(Trade(
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
            ))
            
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
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
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

