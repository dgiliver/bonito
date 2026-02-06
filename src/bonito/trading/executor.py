"""Order execution logic for trading bots."""

import logging
from typing import Literal

from .broker import Broker
from .models import Order, TradingConfig

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Executes orders according to trading configuration."""

    def __init__(self, broker: Broker, config: TradingConfig):
        self.broker = broker
        self.config = config

    async def execute_signal(
        self, symbol: str, side: Literal["buy", "sell"], quantity: float, reason: str = ""
    ) -> Order:
        """Execute a trading signal."""
        logger.info(f"Executing {side} {quantity} {symbol}: {reason}")

        order = await self.broker.submit_order(
            symbol=symbol,
            qty=quantity,
            side=side,
            order_type=self.config.order_type,
        )

        logger.info(f"Order {order.id} submitted: {order.status}")
        return order

    async def close_position(self, symbol: str) -> Order:
        """Close a specific position."""
        return await self.broker.close_position(symbol)

    async def close_all_positions(self) -> list[Order]:
        """Close all open positions."""
        return await self.broker.close_all_positions()
