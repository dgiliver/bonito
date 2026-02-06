"""Tests for broker implementations."""

from datetime import datetime

import pytest

from bonito.trading.alpaca_broker import AlpacaBroker
from bonito.trading.broker import Broker
from bonito.trading.models import AccountInfo, Order


class TestAlpacaBroker:
    """Test AlpacaBroker implementation."""

    def test_initialization(self):
        """Test broker initialization."""
        broker = AlpacaBroker(
            api_key="test_key",
            secret_key="test_secret",
            mode="paper",
            use_mock=True,
        )
        assert broker.api_key == "test_key"
        assert broker.secret_key == "test_secret"
        assert broker.mode == "paper"
        assert broker.use_mock is True
        assert broker._connected is False

    def test_initialization_live_mode(self):
        """Test broker initialization in live mode."""
        broker = AlpacaBroker(
            api_key="test_key",
            secret_key="test_secret",
            mode="live",
            use_mock=True,
        )
        assert broker.mode == "live"

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting to broker."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        result = await broker.connect()
        assert result is True
        assert broker._connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnecting from broker."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()
        assert broker._connected is True

        await broker.disconnect()
        assert broker._connected is False

    @pytest.mark.asyncio
    async def test_get_account_not_connected(self):
        """Test getting account info when not connected raises error."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.get_account()

    @pytest.mark.asyncio
    async def test_get_account_connected(self):
        """Test getting account info when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        account = await broker.get_account()
        assert isinstance(account, AccountInfo)
        assert account.account_id == "mock_account"
        assert account.buying_power == 100000.0
        assert account.cash == 100000.0
        assert account.portfolio_value == 100000.0
        assert account.equity == 100000.0

    @pytest.mark.asyncio
    async def test_submit_order_not_connected(self):
        """Test submitting order when not connected raises error."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.submit_order(
                symbol="SPY",
                qty=100,
                side="buy",
                order_type="market",
            )

    @pytest.mark.asyncio
    async def test_submit_order_connected(self):
        """Test submitting order when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        order = await broker.submit_order(
            symbol="SPY",
            qty=100,
            side="buy",
            order_type="market",
        )
        assert isinstance(order, Order)
        assert order.symbol == "SPY"
        assert order.qty == 100
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.status == "pending"
        assert order.filled_price is None
        assert order.filled_at is None
        assert isinstance(order.created_at, datetime)

    @pytest.mark.asyncio
    async def test_cancel_order_not_connected(self):
        """Test cancelling order when not connected raises error."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.cancel_order("order_123")

    @pytest.mark.asyncio
    async def test_cancel_order_connected(self):
        """Test cancelling order when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        result = await broker.cancel_order("order_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_positions_not_connected(self):
        """Test getting positions when not connected raises error."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.get_positions()

    @pytest.mark.asyncio
    async def test_get_positions_connected(self):
        """Test getting positions when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        positions = await broker.get_positions()
        assert isinstance(positions, list)
        assert len(positions) == 0  # Mock returns empty list

    @pytest.mark.asyncio
    async def test_close_position_not_connected(self):
        """Test closing position when not connected raises error."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.close_position("SPY")

    @pytest.mark.asyncio
    async def test_close_position_connected(self):
        """Test closing position when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        order = await broker.close_position("SPY")
        assert isinstance(order, Order)
        assert order.symbol == "SPY"
        assert order.side == "sell"
        assert order.order_type == "market"
        assert order.status == "pending"

    @pytest.mark.asyncio
    async def test_close_all_positions_not_connected(self):
        """Test closing all positions when not connected raises error."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.close_all_positions()

    @pytest.mark.asyncio
    async def test_close_all_positions_connected(self):
        """Test closing all positions when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        orders = await broker.close_all_positions()
        assert isinstance(orders, list)
        assert len(orders) == 0  # Mock returns empty list

    @pytest.mark.asyncio
    async def test_get_order_connected(self):
        """Test getting order when connected."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        await broker.connect()

        order = await broker.get_order("order_123")
        assert isinstance(order, Order)
        assert order.id == "order_123"
        assert order.status == "filled"

    @pytest.mark.asyncio
    async def test_broker_interface_compliance(self):
        """Test that AlpacaBroker implements Broker interface."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)
        assert isinstance(broker, Broker)

        # Verify all abstract methods are implemented
        assert hasattr(broker, "connect")
        assert hasattr(broker, "disconnect")
        assert hasattr(broker, "get_account")
        assert hasattr(broker, "submit_order")
        assert hasattr(broker, "cancel_order")
        assert hasattr(broker, "get_positions")
        assert hasattr(broker, "close_position")
        assert hasattr(broker, "close_all_positions")
        assert hasattr(broker, "get_order")

    @pytest.mark.asyncio
    async def test_connection_lifecycle(self):
        """Test complete connection lifecycle."""
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret", use_mock=True)

        # Initially not connected
        assert broker._connected is False

        # Connect
        await broker.connect()
        assert broker._connected is True

        # Can perform operations
        account = await broker.get_account()
        assert isinstance(account, AccountInfo)

        # Disconnect
        await broker.disconnect()
        assert broker._connected is False

        # Can't perform operations after disconnect
        with pytest.raises(RuntimeError, match="Not connected to broker"):
            await broker.get_account()
