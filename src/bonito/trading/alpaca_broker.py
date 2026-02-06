"""Alpaca trading API wrapper."""

import logging
from typing import Literal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    StopOrderRequest,
    TrailingStopOrderRequest,
)

from .broker import Broker
from .models import AccountInfo, Order, Position

logger = logging.getLogger(__name__)


class AlpacaBroker(Broker):
    """Alpaca trading API wrapper using alpaca-py SDK."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        mode: Literal["paper", "live"] = "paper",
        use_mock: bool = False,
    ):
        """Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key.
            secret_key: Alpaca secret key.
            mode: Trading mode - "paper" for paper trading, "live" for live trading.
            use_mock: If True, use mock mode for testing (doesn't hit real API).
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.mode = mode
        self.use_mock = use_mock
        self._connected = False
        self._client: TradingClient | None = None

    async def connect(self) -> bool:
        """Connect to Alpaca API.

        Returns:
            True if connection successful.
        """
        if self.use_mock:
            # Mock mode for testing - don't actually connect
            self._connected = True
            logger.info("Connected to Alpaca (mock mode)")
            return True

        try:
            self._client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.mode == "paper",
            )
            # Test connection by fetching account
            _ = self._client.get_account()
            self._connected = True
            logger.info(f"Connected to Alpaca ({self.mode} mode)")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            self._connected = False
            self._client = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from Alpaca API."""
        self._connected = False
        self._client = None

    async def get_account(self) -> AccountInfo:
        """Get Alpaca account information.

        Returns:
            AccountInfo with current account state.

        Raises:
            RuntimeError: If not connected to broker.
        """
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            return AccountInfo(
                account_id="mock_account",
                buying_power=100000.0,
                cash=100000.0,
                portfolio_value=100000.0,
                equity=100000.0,
            )

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        account = self._client.get_account()
        return AccountInfo(
            account_id=str(account.account_number),
            buying_power=float(account.buying_power),
            cash=float(account.cash),
            portfolio_value=float(account.portfolio_value),
            equity=float(account.equity),
        )

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
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            import uuid
            from datetime import datetime

            return Order(
                id=str(uuid.uuid4()),
                symbol=symbol,
                qty=qty,
                side=side,  # type: ignore
                order_type=order_type,  # type: ignore
                status="pending",
                created_at=datetime.now(),
            )

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        # Map side to Alpaca OrderSide
        alpaca_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

        # Get time in force (default to DAY)
        time_in_force = TimeInForce.DAY

        # Create appropriate order request based on type
        if order_type == "market":
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=time_in_force,
            )
        elif order_type == "limit":
            limit_price = kwargs.get("limit_price")
            if limit_price is None:
                raise ValueError("limit_price required for limit orders")
            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=time_in_force,
                limit_price=limit_price,
            )
        elif order_type == "stop":
            stop_price = kwargs.get("stop_price")
            if stop_price is None:
                raise ValueError("stop_price required for stop orders")
            request = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=time_in_force,
                stop_price=stop_price,
            )
        elif order_type == "trailing_stop":
            trail_percent = kwargs.get("trail_percent")
            if trail_percent is None:
                raise ValueError("trail_percent required for trailing_stop orders")
            request = TrailingStopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=time_in_force,
                trail_percent=trail_percent,
            )
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        # Submit order to Alpaca
        alpaca_order = self._client.submit_order(request)

        # Map Alpaca order status to our status
        status_map = {
            "new": "pending",
            "accepted": "pending",
            "filled": "filled",
            "canceled": "cancelled",
            "rejected": "rejected",
            "pending_new": "pending",
            "stopped": "cancelled",
            "pending_cancel": "pending",
            "pending_replace": "pending",
        }
        status = status_map.get(alpaca_order.status, "pending")

        return Order(
            id=str(alpaca_order.id),
            symbol=alpaca_order.symbol,
            qty=float(alpaca_order.qty),
            side=side,  # type: ignore
            order_type=order_type,  # type: ignore
            status=status,  # type: ignore
            filled_price=float(alpaca_order.filled_avg_price)
            if alpaca_order.filled_avg_price
            else None,
            created_at=alpaca_order.created_at,
            filled_at=alpaca_order.filled_at if alpaca_order.filled_at else None,
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: ID of order to cancel.

        Returns:
            True if order was cancelled.

        Raises:
            RuntimeError: If not connected to broker.
        """
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            return True

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of open positions.

        Raises:
            RuntimeError: If not connected to broker.
        """
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            return []

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        positions = self._client.get_all_positions()
        return [
            Position(
                symbol=pos.symbol,
                qty=abs(float(pos.qty)),  # Use absolute value for qty
                side="long" if float(pos.qty) > 0 else "short",
                entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pnl=float(pos.unrealized_pl),
                market_value=float(pos.market_value),
            )
            for pos in positions
        ]

    async def close_position(self, symbol: str) -> Order:
        """Close a specific position.

        Args:
            symbol: Symbol of position to close.

        Returns:
            Order object for the closing order.

        Raises:
            RuntimeError: If not connected to broker.
        """
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            import uuid
            from datetime import datetime

            return Order(
                id=str(uuid.uuid4()),
                symbol=symbol,
                qty=100.0,
                side="sell",
                order_type="market",
                status="pending",
                created_at=datetime.now(),
            )

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        # Close the position (Alpaca automatically determines buy/sell based on current position)
        alpaca_order = self._client.close_position(symbol)

        # Map status
        status_map = {
            "new": "pending",
            "accepted": "pending",
            "filled": "filled",
            "canceled": "cancelled",
            "rejected": "rejected",
            "pending_new": "pending",
            "stopped": "cancelled",
            "pending_cancel": "pending",
            "pending_replace": "pending",
        }
        status = status_map.get(alpaca_order.status, "pending")

        return Order(
            id=str(alpaca_order.id),
            symbol=alpaca_order.symbol,
            qty=float(alpaca_order.qty),
            side=alpaca_order.side.value,  # type: ignore
            order_type="market",
            status=status,  # type: ignore
            filled_price=float(alpaca_order.filled_avg_price)
            if alpaca_order.filled_avg_price
            else None,
            created_at=alpaca_order.created_at,
            filled_at=alpaca_order.filled_at if alpaca_order.filled_at else None,
        )

    async def close_all_positions(self) -> list[Order]:
        """Close all open positions.

        Returns:
            List of orders for all positions closed.

        Raises:
            RuntimeError: If not connected to broker.
        """
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            return []

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        # Get all current positions
        positions = await self.get_positions()

        # Close each position
        orders = []
        for pos in positions:
            try:
                order = await self.close_position(pos.symbol)
                orders.append(order)
            except Exception as e:
                logger.error(f"Failed to close position {pos.symbol}: {e}")

        return orders

    async def get_order(self, order_id: str) -> Order:
        """Get order status by ID.

        Args:
            order_id: ID of order to fetch.

        Returns:
            Order object with current status.

        Raises:
            RuntimeError: If not connected to broker.
        """
        if not self._connected:
            raise RuntimeError("Not connected to broker")

        if self.use_mock:
            # Mock implementation for testing
            from datetime import datetime

            return Order(
                id=order_id,
                symbol="SPY",
                qty=100.0,
                side="buy",
                order_type="market",
                status="filled",
                filled_price=450.0,
                created_at=datetime.now(),
                filled_at=datetime.now(),
            )

        if self._client is None:
            raise RuntimeError("Not connected to broker")

        alpaca_order = self._client.get_order_by_id(order_id)

        # Map status
        status_map = {
            "new": "pending",
            "accepted": "pending",
            "filled": "filled",
            "canceled": "cancelled",
            "rejected": "rejected",
            "pending_new": "pending",
            "stopped": "cancelled",
            "pending_cancel": "pending",
            "pending_replace": "pending",
        }
        status = status_map.get(alpaca_order.status, "pending")

        return Order(
            id=str(alpaca_order.id),
            symbol=alpaca_order.symbol,
            qty=float(alpaca_order.qty),
            side=alpaca_order.side.value,  # type: ignore
            order_type=alpaca_order.type.value,  # type: ignore
            status=status,  # type: ignore
            filled_price=float(alpaca_order.filled_avg_price)
            if alpaca_order.filled_avg_price
            else None,
            created_at=alpaca_order.created_at,
            filled_at=alpaca_order.filled_at if alpaca_order.filled_at else None,
        )
