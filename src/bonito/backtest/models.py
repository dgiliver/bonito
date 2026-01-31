"""Models for backtest configuration and results."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class Trade(BaseModel):
    """A completed trade."""

    symbol: str
    side: OrderSide  # BUY for long entry, SELL for short entry
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    exit_reason: str = Field(default="signal", description="Why the trade was closed")
    position_side: str = Field(
        default="long",
        description="Position type: 'long' (profit when price rises) or 'short' (profit when price falls)",
    )


class BacktestConfig(BaseModel):
    """Configuration for a backtest run."""

    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(default=100_000.0)
    commission: float = Field(default=0.001, description="Commission rate (e.g., 0.001 = 0.1%)")
    slippage: float = Field(default=0.0005, description="Slippage rate")


class PerformanceMetrics(BaseModel):
    """Performance metrics for a backtest."""

    # Returns
    total_return: float = Field(..., description="Total return as decimal (0.25 = 25%)")
    annualized_return: float = Field(..., description="Annualized return")

    # Risk metrics
    sharpe_ratio: float = Field(..., description="Sharpe ratio (assuming 0% risk-free rate)")
    sortino_ratio: float = Field(..., description="Sortino ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown as decimal")
    max_drawdown_duration_days: int = Field(..., description="Longest drawdown duration")

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float = Field(..., description="Win rate as decimal")
    profit_factor: float = Field(..., description="Gross profit / gross loss")
    average_win: float = Field(..., description="Average winning trade return")
    average_loss: float = Field(..., description="Average losing trade return")
    largest_win: float
    largest_loss: float

    # Exposure
    avg_exposure: float = Field(..., description="Average capital exposure")

    # Additional
    calmar_ratio: float = Field(..., description="Annualized return / max drawdown")


class BacktestResult(BaseModel):
    """Complete backtest result."""

    # Metadata
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float

    # Core results
    metrics: PerformanceMetrics
    trades: list[Trade]

    # Time series (for charting)
    equity_curve: list[float] = Field(..., description="Daily equity values")
    equity_dates: list[datetime] = Field(..., description="Dates for equity curve")
    drawdown_curve: list[float] = Field(..., description="Drawdown at each point")

    # Execution details
    total_commission: float
    total_slippage: float

    def summary(self) -> str:
        """Generate a text summary of the results."""
        m = self.metrics
        return f"""
Backtest Results: {self.strategy_name}
{"=" * 50}
Period: {self.start_date.date()} to {self.end_date.date()}
Initial Capital: ${self.initial_capital:,.2f}
Final Capital: ${self.final_capital:,.2f}

RETURNS
  Total Return: {m.total_return:.2%}
  Annualized Return: {m.annualized_return:.2%}

RISK
  Sharpe Ratio: {m.sharpe_ratio:.2f}
  Sortino Ratio: {m.sortino_ratio:.2f}
  Max Drawdown: {m.max_drawdown:.2%}
  Calmar Ratio: {m.calmar_ratio:.2f}

TRADES
  Total Trades: {m.total_trades}
  Win Rate: {m.win_rate:.1%}
  Profit Factor: {m.profit_factor:.2f}
  Avg Win: {m.average_win:.2%}
  Avg Loss: {m.average_loss:.2%}

COSTS
  Total Commission: ${self.total_commission:,.2f}
  Total Slippage: ${self.total_slippage:,.2f}
"""
