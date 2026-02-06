"""Abstract broker interface for trading operations."""

from abc import ABC, abstractmethod

from .models import AccountInfo, Order, Position


class Broker(ABC):
    """Abstract broker interface for trading operations."""

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the broker.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get account information.

        Returns:
            AccountInfo with current account state.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass

    @abstractmethod
    async def submit_order(
        self, symbol: str, qty: float, side: str, order_type: str, **kwargs
    ) -> Order:
        """Submit a new order.

        Args:
            symbol: Stock symbol to trade.
            qty: Quantity to trade.
            side: "buy" or "sell".
            order_type: "market", "limit", "stop", or "trailing_stop".
            **kwargs: Additional order parameters (e.g., limit_price, stop_price).

        Returns:
            Order object with order details.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: ID of order to cancel.

        Returns:
            True if order was cancelled, False otherwise.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of open positions.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass

    @abstractmethod
    async def close_position(self, symbol: str) -> Order:
        """Close a specific position.

        Args:
            symbol: Symbol of position to close.

        Returns:
            Order object for the closing order.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass

    @abstractmethod
    async def close_all_positions(self) -> list[Order]:
        """Close all open positions.

        Returns:
            List of orders for all positions closed.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Get order status by ID.

        Args:
            order_id: ID of order to fetch.

        Returns:
            Order object with current status.

        Raises:
            RuntimeError: If not connected to broker.
        """
        pass
