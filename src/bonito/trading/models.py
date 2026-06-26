"""Pydantic models for trading infrastructure."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ExecutionModel(StrEnum):
    """Execution model for trading bots."""

    SCHEDULED = "scheduled"
    CONTINUOUS = "continuous"
    EVENT_DRIVEN = "event_driven"


class TradingConfig(BaseModel):
    """User-configurable trading parameters."""

    broker: Literal["alpaca"] = "alpaca"
    mode: Literal["paper", "live"] = "paper"
    execution_model: ExecutionModel
    schedule: str | None = None  # Cron expression for scheduled
    order_type: Literal["market", "limit"] = "market"
    limit_offset_pct: float = 0.001
    max_position_pct: float = 100.0
    max_positions: int = 100
    max_daily_loss_pct: float | None = None


class Position(BaseModel):
    """A trading position."""

    symbol: str
    qty: float
    side: Literal["long", "short"]
    entry_price: float
    current_price: float
    unrealized_pnl: float
    market_value: float


class Order(BaseModel):
    """A trading order."""

    id: str
    symbol: str
    qty: float
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "trailing_stop"]
    status: Literal["pending", "filled", "cancelled", "rejected"]
    filled_price: float | None = None
    created_at: datetime
    filled_at: datetime | None = None


class BotConfig(BaseModel):
    """Complete bot configuration."""

    id: str
    name: str
    strategy_name: str
    strategy_config: dict  # Strategy JSON config
    trading_config: TradingConfig
    created_at: datetime
    created_by: str | None = None
    risk_score: Literal["low", "medium", "high", "extreme"] = "low"
    risk_warnings: list[str] = Field(default_factory=list)


class DeployedBot(BaseModel):
    """A running bot instance."""

    id: str
    config: BotConfig
    status: Literal["running", "paused", "stopped", "error", "halted"]
    broker_connected: bool = False
    open_positions: list[Position] = Field(default_factory=list)
    pending_orders: list[Order] = Field(default_factory=list)
    start_time: datetime
    total_trades: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    daily_pnl: float = 0.0
    halt_reason: str = ""


class AccountInfo(BaseModel):
    """Broker account information."""

    account_id: str
    buying_power: float
    cash: float
    portfolio_value: float
    equity: float
