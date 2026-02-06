"""Position and P&L monitoring for trading bots."""

import logging

from .broker import Broker
from .models import Position

logger = logging.getLogger(__name__)


class PositionMonitor:
    """Monitors positions and calculates P&L."""

    def __init__(self, broker: Broker):
        self.broker = broker
        self._positions: list[Position] = []
        self._peak_equity: float = 0.0
        self._realized_pnl: float = 0.0

    async def refresh_positions(self) -> list[Position]:
        """Fetch current positions from broker."""
        self._positions = await self.broker.get_positions()
        return self._positions

    @property
    def positions(self) -> list[Position]:
        """Get cached positions."""
        return self._positions

    @property
    def unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L."""
        return sum(p.unrealized_pnl for p in self._positions)

    @property
    def total_exposure(self) -> float:
        """Calculate total market exposure."""
        return sum(p.market_value for p in self._positions)

    def record_trade_pnl(self, pnl: float) -> None:
        """Record P&L from a completed trade."""
        self._realized_pnl += pnl
        logger.info(f"Trade P&L recorded: {pnl}, total realized: {self._realized_pnl}")

    def update_peak_equity(self, current_equity: float) -> None:
        """Update peak equity for drawdown calculation."""
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

    @property
    def drawdown(self) -> float:
        """Calculate current drawdown from peak."""
        if self._peak_equity == 0:
            return 0.0
        current = sum(p.market_value for p in self._positions)
        return (self._peak_equity - current) / self._peak_equity
