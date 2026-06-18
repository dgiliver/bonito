"""Tests for trading bot lifecycle management."""

import asyncio
from datetime import datetime, timedelta

import pytest

from bonito.trading import (
    BotConfig,
    BotRegistry,
    ExecutionModel,
    OrderExecutor,
    PositionMonitor,
    TradingBot,
    TradingConfig,
    calculate_risk_score,
    should_require_acknowledgment,
)
from bonito.trading.models import Position


class MockBroker:
    """Mock broker for testing."""

    def __init__(self):
        self._connected = False
        self._positions = []
        self.api_key = "mock_api_key"
        self.secret_key = "mock_secret_key"

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_positions(self) -> list[Position]:
        return self._positions

    async def get_account(self):
        from bonito.trading.models import AccountInfo

        return AccountInfo(
            account_id="mock_account",
            buying_power=100000.0,
            cash=100000.0,
            portfolio_value=100000.0,
            equity=100000.0,
        )

    async def close_all_positions(self):
        orders = []
        self._positions = []
        return orders

    async def submit_order(self, symbol: str, qty: float, side: str, order_type: str, **kwargs):
        from bonito.trading.models import Order

        return Order(
            id="test_order_123",
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            status="pending",
            created_at=datetime.utcnow(),
        )

    async def close_position(self, symbol: str):
        from bonito.trading.models import Order

        return Order(
            id="close_order_123",
            symbol=symbol,
            qty=100.0,
            side="sell",
            order_type="market",
            status="pending",
            created_at=datetime.utcnow(),
        )


@pytest.fixture
def mock_broker():
    """Create a mock broker."""
    return MockBroker()


@pytest.fixture
def bot_config():
    """Create a test bot config."""
    return BotConfig(
        id="test_bot_001",
        name="Test Bot",
        strategy_name="test_strategy",
        strategy_config={
            "name": "test_strategy",
            "symbols": ["SPY"],
            "timeframe": "1d",
            "indicators": [{"type": "sma", "name": "sma_20", "params": {"period": 20}}],
            "entry_rules": [
                {
                    "conditions": [
                        {"left": "close", "comparison": "crosses_above", "right": "sma_20"}
                    ],
                    "logic": "AND",
                    "side": "long",
                }
            ],
            "exit_rules": [
                {
                    "conditions": [
                        {"left": "close", "comparison": "crosses_below", "right": "sma_20"}
                    ],
                    "logic": "AND",
                }
            ],
            "position_size": {"type": "percent_equity", "value": 10.0},
            "stop_loss": {"type": "percent", "value": 0.05},
        },
        trading_config=TradingConfig(
            broker="alpaca",
            mode="paper",
            execution_model=ExecutionModel.CONTINUOUS,
            max_position_pct=10.0,
        ),
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def trading_bot(bot_config, mock_broker):
    """Create a trading bot instance."""
    return TradingBot(config=bot_config, broker=mock_broker)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the bot registry before each test."""
    BotRegistry.reset()
    yield
    BotRegistry.reset()


# TradingBot Tests


@pytest.mark.asyncio
async def test_bot_start(trading_bot, mock_broker):
    """Test starting a bot."""
    assert trading_bot.status == "stopped"
    assert not mock_broker._connected

    await trading_bot.start()

    assert trading_bot.status == "running"
    assert mock_broker._connected
    assert trading_bot._start_time is not None
    assert trading_bot._task is not None

    # Cleanup
    await trading_bot.stop()


@pytest.mark.asyncio
async def test_bot_start_already_running(trading_bot):
    """Test starting a bot that's already running raises error."""
    await trading_bot.start()

    with pytest.raises(RuntimeError, match="already running"):
        await trading_bot.start()

    # Cleanup
    await trading_bot.stop()


@pytest.mark.asyncio
async def test_bot_pause(trading_bot):
    """Test pausing a running bot."""
    await trading_bot.start()
    assert trading_bot.status == "running"

    await trading_bot.pause()
    assert trading_bot.status == "paused"

    # Cleanup
    await trading_bot.stop()


@pytest.mark.asyncio
async def test_bot_pause_not_running(trading_bot):
    """Test pausing a stopped bot raises error."""
    with pytest.raises(RuntimeError, match="Can only pause a running bot"):
        await trading_bot.pause()


@pytest.mark.asyncio
async def test_bot_resume(trading_bot):
    """Test resuming a paused bot."""
    await trading_bot.start()
    await trading_bot.pause()
    assert trading_bot.status == "paused"

    await trading_bot.resume()
    assert trading_bot.status == "running"

    # Cleanup
    await trading_bot.stop()


@pytest.mark.asyncio
async def test_bot_resume_not_paused(trading_bot):
    """Test resuming a non-paused bot raises error."""
    with pytest.raises(RuntimeError, match="Can only resume a paused bot"):
        await trading_bot.resume()


@pytest.mark.asyncio
async def test_bot_stop(trading_bot, mock_broker):
    """Test stopping a bot."""
    await trading_bot.start()
    assert trading_bot.status == "running"

    await trading_bot.stop()

    assert trading_bot.status == "stopped"
    assert not mock_broker._connected


@pytest.mark.asyncio
async def test_bot_stop_with_close_positions(trading_bot, mock_broker):
    """Test stopping a bot and closing positions."""
    # Add a mock position
    mock_broker._positions = [
        Position(
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            market_value=15500.0,
        )
    ]

    await trading_bot.start()
    trading_bot._positions = mock_broker._positions.copy()

    await trading_bot.stop(close_positions=True)

    assert trading_bot.status == "stopped"
    assert len(mock_broker._positions) == 0


@pytest.mark.asyncio
async def test_bot_get_deployed_bot_state(trading_bot):
    """Test getting bot state as DeployedBot."""
    await trading_bot.start()

    state = trading_bot.get_deployed_bot_state()

    assert state.id == trading_bot.id
    assert state.config == trading_bot.config
    assert state.status == "running"
    assert state.broker_connected is True
    assert state.start_time is not None

    # Cleanup
    await trading_bot.stop()


@pytest.mark.asyncio
async def test_bot_run_loop_paused(trading_bot):
    """Test that paused bot doesn't execute trades."""
    await trading_bot.start()
    await trading_bot.pause()

    # Sleep a bit to ensure loop runs
    await asyncio.sleep(0.1)

    # Bot should still be paused
    assert trading_bot.status == "paused"

    # Cleanup
    await trading_bot.stop()


# Kill Switch Tests (daily-loss enforcement, TradingConfig.max_daily_loss_pct)


def _bot_with_daily_loss_limit(mock_broker, max_daily_loss_pct: float | None = 5.0):
    config = BotConfig(
        id="kill_switch_bot",
        name="Kill Switch Bot",
        strategy_name="test_strategy",
        strategy_config={
            "name": "test_strategy",
            "symbols": ["SPY"],
            "entry_rules": [
                {
                    "conditions": [
                        {"left": "close", "comparison": "crosses_above", "right": "sma_20"}
                    ]
                }
            ],
        },
        trading_config=TradingConfig(
            broker="alpaca",
            mode="paper",
            execution_model=ExecutionModel.CONTINUOUS,
            max_daily_loss_pct=max_daily_loss_pct,
        ),
        created_at=datetime.utcnow(),
    )
    return TradingBot(config=config, broker=mock_broker)


@pytest.mark.asyncio
async def test_kill_switch_noop_without_limit(mock_broker):
    """No max_daily_loss_pct configured means the kill switch never trips."""
    bot = _bot_with_daily_loss_limit(mock_broker, max_daily_loss_pct=None)

    tripped = await bot._check_kill_switch(50_000.0)  # 50% "loss" from nothing set yet

    assert tripped is False
    assert bot.status != "halted"


@pytest.mark.asyncio
async def test_kill_switch_noop_within_limit(mock_broker):
    """Equity dipping less than the configured limit should not halt the bot."""
    bot = _bot_with_daily_loss_limit(mock_broker, max_daily_loss_pct=5.0)

    await bot._check_kill_switch(100_000.0)  # establishes today's baseline
    tripped = await bot._check_kill_switch(97_000.0)  # 3% down, under the 5% limit

    assert tripped is False
    assert bot.status != "halted"


@pytest.mark.asyncio
async def test_kill_switch_trips_and_closes_positions(mock_broker):
    """Breaching max_daily_loss_pct halts the bot and flattens positions."""
    bot = _bot_with_daily_loss_limit(mock_broker, max_daily_loss_pct=5.0)
    mock_broker._positions = [
        Position(
            symbol="SPY",
            qty=10,
            side="long",
            entry_price=400.0,
            current_price=380.0,
            unrealized_pnl=-200.0,
            market_value=3800.0,
        )
    ]

    await bot._check_kill_switch(100_000.0)  # establishes today's baseline
    tripped = await bot._check_kill_switch(94_000.0)  # 6% down, breaches the 5% limit

    assert tripped is True
    assert bot.status == "halted"
    assert "daily loss" in bot._halt_reason
    assert mock_broker._positions == []  # close_all_positions was called


@pytest.mark.asyncio
async def test_kill_switch_resets_baseline_on_new_day(mock_broker):
    """A new UTC day resets the daily-loss baseline instead of halting forever."""
    bot = _bot_with_daily_loss_limit(mock_broker, max_daily_loss_pct=5.0)

    await bot._check_kill_switch(100_000.0)
    bot._daily_start_date -= timedelta(days=1)  # simulate yesterday's baseline

    tripped = await bot._check_kill_switch(94_000.0)  # would have breached yesterday's baseline

    assert tripped is False
    assert bot._daily_start_equity == 94_000.0  # rebaselined to today's equity


@pytest.mark.asyncio
async def test_kill_switch_halted_bot_cannot_resume(mock_broker):
    """A halted bot is not resumable the way a paused bot is - it needs a fresh deploy."""
    bot = _bot_with_daily_loss_limit(mock_broker, max_daily_loss_pct=5.0)
    await bot._check_kill_switch(100_000.0)
    await bot._check_kill_switch(90_000.0)
    assert bot.status == "halted"

    with pytest.raises(RuntimeError, match="Can only resume a paused bot"):
        await bot.resume()


# BotRegistry Tests


def test_registry_singleton():
    """Test that BotRegistry is a singleton."""
    registry1 = BotRegistry()
    registry2 = BotRegistry()
    assert registry1 is registry2


def test_registry_register(trading_bot):
    """Test registering a bot."""
    registry = BotRegistry()
    registry.register(trading_bot)

    assert registry.get(trading_bot.id) == trading_bot
    assert trading_bot in registry.list_all()


def test_registry_register_duplicate(trading_bot):
    """Test registering duplicate bot raises error."""
    registry = BotRegistry()
    registry.register(trading_bot)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(trading_bot)


def test_registry_unregister(trading_bot):
    """Test unregistering a bot."""
    registry = BotRegistry()
    registry.register(trading_bot)

    bot = registry.unregister(trading_bot.id)

    assert bot == trading_bot
    assert registry.get(trading_bot.id) is None
    assert trading_bot not in registry.list_all()


def test_registry_unregister_nonexistent():
    """Test unregistering a nonexistent bot returns None."""
    registry = BotRegistry()
    bot = registry.unregister("nonexistent")
    assert bot is None


def test_registry_list_all(bot_config, mock_broker):
    """Test listing all bots."""
    registry = BotRegistry()

    bot1 = TradingBot(config=bot_config, broker=mock_broker)
    bot2_config = bot_config.model_copy()
    bot2_config.id = "test_bot_002"
    bot2 = TradingBot(config=bot2_config, broker=mock_broker)

    registry.register(bot1)
    registry.register(bot2)

    all_bots = registry.list_all()
    assert len(all_bots) == 2
    assert bot1 in all_bots
    assert bot2 in all_bots


@pytest.mark.asyncio
async def test_registry_list_by_status(bot_config, mock_broker):
    """Test filtering bots by status."""
    registry = BotRegistry()

    bot1 = TradingBot(config=bot_config, broker=mock_broker)
    bot2_config = bot_config.model_copy()
    bot2_config.id = "test_bot_002"
    bot2 = TradingBot(config=bot2_config, broker=mock_broker)

    registry.register(bot1)
    registry.register(bot2)

    # Start bot1
    await bot1.start()

    running_bots = registry.list_by_status("running")
    stopped_bots = registry.list_by_status("stopped")

    assert len(running_bots) == 1
    assert bot1 in running_bots
    assert len(stopped_bots) == 1
    assert bot2 in stopped_bots

    # Cleanup
    await bot1.stop()


def test_registry_listeners(trading_bot):
    """Test registry event listeners."""
    registry = BotRegistry()
    events = []

    def listener(event: str, bot: TradingBot):
        events.append((event, bot.id))

    registry.add_listener(listener)
    registry.register(trading_bot)
    registry.unregister(trading_bot.id)

    assert len(events) == 2
    assert events[0] == ("registered", trading_bot.id)
    assert events[1] == ("unregistered", trading_bot.id)


def test_registry_listener_error_handling(trading_bot):
    """Test that listener errors don't break registry."""
    registry = BotRegistry()

    def bad_listener(event: str, bot: TradingBot):
        raise ValueError("Listener error")

    registry.add_listener(bad_listener)

    # Should not raise
    registry.register(trading_bot)


# OrderExecutor Tests


@pytest.mark.asyncio
async def test_executor_execute_signal(mock_broker):
    """Test executing a trading signal."""
    config = TradingConfig(
        broker="alpaca",
        mode="paper",
        execution_model=ExecutionModel.CONTINUOUS,
        order_type="market",
    )
    executor = OrderExecutor(broker=mock_broker, config=config)

    await mock_broker.connect()
    order = await executor.execute_signal(
        symbol="AAPL", side="buy", quantity=100.0, reason="Test signal"
    )

    assert order.symbol == "AAPL"
    assert order.qty == 100.0
    assert order.side == "buy"
    assert order.order_type == "market"


@pytest.mark.asyncio
async def test_executor_close_position(mock_broker):
    """Test closing a position."""
    config = TradingConfig(broker="alpaca", mode="paper", execution_model=ExecutionModel.CONTINUOUS)
    executor = OrderExecutor(broker=mock_broker, config=config)

    await mock_broker.connect()
    order = await executor.close_position("AAPL")

    assert order.symbol == "AAPL"
    assert order.side == "sell"


@pytest.mark.asyncio
async def test_executor_close_all_positions(mock_broker):
    """Test closing all positions."""
    config = TradingConfig(broker="alpaca", mode="paper", execution_model=ExecutionModel.CONTINUOUS)
    executor = OrderExecutor(broker=mock_broker, config=config)

    await mock_broker.connect()
    orders = await executor.close_all_positions()

    assert isinstance(orders, list)


# PositionMonitor Tests


@pytest.mark.asyncio
async def test_monitor_refresh_positions(mock_broker):
    """Test refreshing positions from broker."""
    mock_broker._positions = [
        Position(
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            market_value=15500.0,
        )
    ]

    monitor = PositionMonitor(broker=mock_broker)
    await mock_broker.connect()

    positions = await monitor.refresh_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert monitor.positions == positions


def test_monitor_unrealized_pnl():
    """Test calculating unrealized P&L."""
    mock_broker = MockBroker()
    monitor = PositionMonitor(broker=mock_broker)

    monitor._positions = [
        Position(
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            market_value=15500.0,
        ),
        Position(
            symbol="GOOGL",
            qty=50.0,
            side="long",
            entry_price=2800.0,
            current_price=2850.0,
            unrealized_pnl=2500.0,
            market_value=142500.0,
        ),
    ]

    assert monitor.unrealized_pnl == 3000.0


def test_monitor_total_exposure():
    """Test calculating total market exposure."""
    mock_broker = MockBroker()
    monitor = PositionMonitor(broker=mock_broker)

    monitor._positions = [
        Position(
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            market_value=15500.0,
        ),
        Position(
            symbol="GOOGL",
            qty=50.0,
            side="long",
            entry_price=2800.0,
            current_price=2850.0,
            unrealized_pnl=2500.0,
            market_value=142500.0,
        ),
    ]

    assert monitor.total_exposure == 158000.0


def test_monitor_record_trade_pnl():
    """Test recording trade P&L."""
    mock_broker = MockBroker()
    monitor = PositionMonitor(broker=mock_broker)

    assert monitor._realized_pnl == 0.0

    monitor.record_trade_pnl(500.0)
    assert monitor._realized_pnl == 500.0

    monitor.record_trade_pnl(-200.0)
    assert monitor._realized_pnl == 300.0


def test_monitor_update_peak_equity():
    """Test updating peak equity."""
    mock_broker = MockBroker()
    monitor = PositionMonitor(broker=mock_broker)

    assert monitor._peak_equity == 0.0

    monitor.update_peak_equity(100000.0)
    assert monitor._peak_equity == 100000.0

    monitor.update_peak_equity(95000.0)  # Lower, should not update
    assert monitor._peak_equity == 100000.0

    monitor.update_peak_equity(105000.0)  # Higher, should update
    assert monitor._peak_equity == 105000.0


def test_monitor_drawdown():
    """Test calculating drawdown."""
    mock_broker = MockBroker()
    monitor = PositionMonitor(broker=mock_broker)

    # No peak equity yet
    assert monitor.drawdown == 0.0

    # Set peak equity
    monitor.update_peak_equity(100000.0)

    # Current market value is lower
    monitor._positions = [
        Position(
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
            current_price=145.0,
            unrealized_pnl=-500.0,
            market_value=90000.0,
        )
    ]

    expected_drawdown = (100000.0 - 90000.0) / 100000.0
    assert monitor.drawdown == expected_drawdown


# Risk Scoring Tests


def test_risk_score_low():
    """Test low risk configuration."""
    config = BotConfig(
        id="test",
        name="Test",
        strategy_name="test",
        strategy_config={"stop_loss": {"type": "percent", "value": 0.05}},
        trading_config=TradingConfig(
            broker="alpaca",
            mode="paper",
            execution_model=ExecutionModel.CONTINUOUS,
            max_position_pct=10.0,
            max_positions=5,
            max_daily_loss_pct=5.0,
        ),
        created_at=datetime.utcnow(),
    )

    risk_level, warnings = calculate_risk_score(config)

    assert risk_level == "low"
    assert len(warnings) == 0


def test_risk_score_medium():
    """Test medium risk configuration."""
    config = BotConfig(
        id="test",
        name="Test",
        strategy_name="test",
        strategy_config={"stop_loss": {"type": "percent", "value": 0.05}},
        trading_config=TradingConfig(
            broker="alpaca",
            mode="paper",
            execution_model=ExecutionModel.CONTINUOUS,
            max_position_pct=10.0,
            max_daily_loss_pct=None,  # No daily loss limit (+1)
            max_positions=100,  # No position limit (+1)
        ),
        created_at=datetime.utcnow(),
    )

    risk_level, warnings = calculate_risk_score(config)

    assert risk_level == "medium"
    assert any("No daily loss limit" in w for w in warnings)
    assert any("No position limit" in w for w in warnings)


def test_risk_score_high():
    """Test high risk configuration."""
    config = BotConfig(
        id="test",
        name="Test",
        strategy_name="test",
        strategy_config={},  # No stop loss (+2)
        trading_config=TradingConfig(
            broker="alpaca",
            mode="paper",
            execution_model=ExecutionModel.CONTINUOUS,
            max_position_pct=60.0,  # Large position (+2)
            max_daily_loss_pct=5.0,  # Has daily limit (0)
            max_positions=5,  # Has position limit (0)
        ),
        created_at=datetime.utcnow(),
    )

    risk_level, warnings = calculate_risk_score(config)

    assert risk_level == "high"
    assert any("Large position size" in w for w in warnings)
    assert any("No stop loss" in w for w in warnings)


def test_risk_score_extreme():
    """Test extreme risk configuration."""
    config = BotConfig(
        id="test",
        name="Test",
        strategy_name="test",
        strategy_config={},  # No stop loss
        trading_config=TradingConfig(
            broker="alpaca",
            mode="live",  # Live trading
            execution_model=ExecutionModel.CONTINUOUS,
            max_position_pct=95.0,  # Extreme position size
        ),
        created_at=datetime.utcnow(),
    )

    risk_level, warnings = calculate_risk_score(config)

    assert risk_level == "extreme"
    assert any("Extreme position size" in w for w in warnings)
    assert any("LIVE TRADING" in w for w in warnings)


def test_risk_score_all_warnings():
    """Test that all risk warnings are detected."""
    config = BotConfig(
        id="test",
        name="Test",
        strategy_name="test",
        strategy_config={},  # No stop loss
        trading_config=TradingConfig(
            broker="alpaca",
            mode="live",
            execution_model=ExecutionModel.CONTINUOUS,
            max_position_pct=95.0,
            max_positions=100,
            max_daily_loss_pct=None,
        ),
        created_at=datetime.utcnow(),
    )

    risk_level, warnings = calculate_risk_score(config)

    assert risk_level == "extreme"
    # Should have all warnings
    warning_text = " ".join(warnings)
    assert "Extreme position size" in warning_text
    assert "No stop loss" in warning_text
    assert "No daily loss limit" in warning_text
    assert "LIVE TRADING" in warning_text
    assert "No position limit" in warning_text


def test_should_require_acknowledgment():
    """Test acknowledgment requirement based on risk level."""
    assert should_require_acknowledgment("low") is False
    assert should_require_acknowledgment("medium") is False
    assert should_require_acknowledgment("high") is True
    assert should_require_acknowledgment("extreme") is True
