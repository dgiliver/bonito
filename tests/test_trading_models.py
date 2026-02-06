"""Tests for trading infrastructure models."""

from datetime import datetime, timedelta

from bonito.trading.models import (
    AccountInfo,
    BotConfig,
    DeployedBot,
    ExecutionModel,
    Order,
    Position,
    TradingConfig,
)


class TestTradingConfig:
    """Test TradingConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TradingConfig(execution_model=ExecutionModel.SCHEDULED)
        assert config.broker == "alpaca"
        assert config.mode == "paper"
        assert config.order_type == "market"
        assert config.limit_offset_pct == 0.001
        assert config.max_position_pct == 100.0
        assert config.max_positions == 100
        assert config.max_daily_loss_pct is None
        assert config.schedule is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = TradingConfig(
            execution_model=ExecutionModel.CONTINUOUS,
            mode="live",
            order_type="limit",
            max_position_pct=10.0,
            max_positions=5,
            max_daily_loss_pct=5.0,
        )
        assert config.mode == "live"
        assert config.execution_model == ExecutionModel.CONTINUOUS
        assert config.order_type == "limit"
        assert config.max_position_pct == 10.0
        assert config.max_positions == 5
        assert config.max_daily_loss_pct == 5.0

    def test_scheduled_with_cron(self):
        """Test scheduled execution with cron expression."""
        config = TradingConfig(
            execution_model=ExecutionModel.SCHEDULED,
            schedule="0 9 * * MON-FRI",  # 9 AM weekdays
        )
        assert config.execution_model == ExecutionModel.SCHEDULED
        assert config.schedule == "0 9 * * MON-FRI"

    def test_execution_model_enum(self):
        """Test ExecutionModel enum values."""
        assert ExecutionModel.SCHEDULED == "scheduled"
        assert ExecutionModel.CONTINUOUS == "continuous"
        assert ExecutionModel.EVENT_DRIVEN == "event_driven"


class TestPosition:
    """Test Position model."""

    def test_long_position(self):
        """Test long position with profit."""
        pos = Position(
            symbol="SPY",
            qty=100,
            side="long",
            entry_price=450.0,
            current_price=455.0,
            unrealized_pnl=500.0,
            market_value=45500.0,
        )
        assert pos.symbol == "SPY"
        assert pos.qty == 100
        assert pos.side == "long"
        assert pos.entry_price == 450.0
        assert pos.current_price == 455.0
        assert pos.unrealized_pnl == 500.0
        assert pos.market_value == 45500.0

    def test_short_position(self):
        """Test short position with profit."""
        pos = Position(
            symbol="QQQ",
            qty=50,
            side="short",
            entry_price=380.0,
            current_price=375.0,
            unrealized_pnl=250.0,
            market_value=-18750.0,
        )
        assert pos.side == "short"
        assert pos.unrealized_pnl == 250.0

    def test_losing_position(self):
        """Test position with loss."""
        pos = Position(
            symbol="AAPL",
            qty=200,
            side="long",
            entry_price=180.0,
            current_price=175.0,
            unrealized_pnl=-1000.0,
            market_value=35000.0,
        )
        assert pos.unrealized_pnl == -1000.0


class TestOrder:
    """Test Order model."""

    def test_pending_order(self):
        """Test pending order creation."""
        now = datetime.now()
        order = Order(
            id="order_123",
            symbol="TSLA",
            qty=10,
            side="buy",
            order_type="market",
            status="pending",
            created_at=now,
        )
        assert order.id == "order_123"
        assert order.symbol == "TSLA"
        assert order.qty == 10
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.status == "pending"
        assert order.filled_price is None
        assert order.filled_at is None

    def test_filled_order(self):
        """Test filled order."""
        now = datetime.now()
        filled_time = now + timedelta(seconds=5)
        order = Order(
            id="order_456",
            symbol="NVDA",
            qty=5,
            side="sell",
            order_type="limit",
            status="filled",
            filled_price=850.50,
            created_at=now,
            filled_at=filled_time,
        )
        assert order.status == "filled"
        assert order.filled_price == 850.50
        assert order.filled_at == filled_time

    def test_cancelled_order(self):
        """Test cancelled order."""
        order = Order(
            id="order_789",
            symbol="SPY",
            qty=100,
            side="buy",
            order_type="market",
            status="cancelled",
            created_at=datetime.now(),
        )
        assert order.status == "cancelled"

    def test_order_types(self):
        """Test different order types."""
        for order_type in ["market", "limit", "stop", "trailing_stop"]:
            order = Order(
                id=f"order_{order_type}",
                symbol="SPY",
                qty=1,
                side="buy",
                order_type=order_type,  # type: ignore
                status="pending",
                created_at=datetime.now(),
            )
            assert order.order_type == order_type


class TestBotConfig:
    """Test BotConfig model."""

    def test_minimal_bot_config(self):
        """Test minimal bot configuration."""
        now = datetime.now()
        config = BotConfig(
            id="bot_001",
            name="Test Bot",
            strategy_name="SMA Crossover",
            strategy_config={"indicators": [{"type": "sma", "name": "sma_20"}]},
            trading_config=TradingConfig(execution_model=ExecutionModel.SCHEDULED),
            created_at=now,
        )
        assert config.id == "bot_001"
        assert config.name == "Test Bot"
        assert config.strategy_name == "SMA Crossover"
        assert config.risk_score == "low"
        assert config.risk_warnings == []
        assert config.created_by is None

    def test_high_risk_bot_config(self):
        """Test high-risk bot configuration."""
        config = BotConfig(
            id="bot_002",
            name="Aggressive Trader",
            strategy_name="High Frequency",
            strategy_config={"max_positions": 50},
            trading_config=TradingConfig(
                execution_model=ExecutionModel.CONTINUOUS,
                mode="live",
                max_position_pct=50.0,
            ),
            created_at=datetime.now(),
            created_by="user@example.com",
            risk_score="high",
            risk_warnings=[
                "Uses 50% position sizing",
                "Live trading mode enabled",
            ],
        )
        assert config.risk_score == "high"
        assert len(config.risk_warnings) == 2
        assert config.created_by == "user@example.com"

    def test_risk_score_levels(self):
        """Test all risk score levels."""
        for risk_level in ["low", "medium", "high", "extreme"]:
            config = BotConfig(
                id=f"bot_{risk_level}",
                name=f"{risk_level.title()} Risk Bot",
                strategy_name="Test",
                strategy_config={},
                trading_config=TradingConfig(execution_model=ExecutionModel.SCHEDULED),
                created_at=datetime.now(),
                risk_score=risk_level,  # type: ignore
            )
            assert config.risk_score == risk_level


class TestDeployedBot:
    """Test DeployedBot model."""

    def test_new_deployed_bot(self):
        """Test newly deployed bot."""
        bot_config = BotConfig(
            id="bot_001",
            name="Test Bot",
            strategy_name="SMA Crossover",
            strategy_config={},
            trading_config=TradingConfig(execution_model=ExecutionModel.SCHEDULED),
            created_at=datetime.now(),
        )
        start_time = datetime.now()

        bot = DeployedBot(
            id="deployed_001",
            config=bot_config,
            status="running",
            start_time=start_time,
        )

        assert bot.id == "deployed_001"
        assert bot.config == bot_config
        assert bot.status == "running"
        assert bot.broker_connected is False
        assert bot.open_positions == []
        assert bot.pending_orders == []
        assert bot.total_trades == 0
        assert bot.realized_pnl == 0.0
        assert bot.unrealized_pnl == 0.0
        assert bot.peak_equity == 0.0
        assert bot.current_equity == 0.0
        assert bot.daily_pnl == 0.0

    def test_active_bot_with_positions(self):
        """Test bot with active positions."""
        bot_config = BotConfig(
            id="bot_002",
            name="Active Bot",
            strategy_name="RSI",
            strategy_config={},
            trading_config=TradingConfig(execution_model=ExecutionModel.CONTINUOUS),
            created_at=datetime.now(),
        )

        positions = [
            Position(
                symbol="SPY",
                qty=100,
                side="long",
                entry_price=450.0,
                current_price=455.0,
                unrealized_pnl=500.0,
                market_value=45500.0,
            ),
            Position(
                symbol="QQQ",
                qty=50,
                side="long",
                entry_price=380.0,
                current_price=385.0,
                unrealized_pnl=250.0,
                market_value=19250.0,
            ),
        ]

        orders = [
            Order(
                id="order_1",
                symbol="AAPL",
                qty=10,
                side="buy",
                order_type="limit",
                status="pending",
                created_at=datetime.now(),
            )
        ]

        bot = DeployedBot(
            id="deployed_002",
            config=bot_config,
            status="running",
            broker_connected=True,
            open_positions=positions,
            pending_orders=orders,
            start_time=datetime.now(),
            total_trades=15,
            realized_pnl=1500.0,
            unrealized_pnl=750.0,
            peak_equity=105000.0,
            current_equity=102250.0,
            daily_pnl=250.0,
        )

        assert bot.broker_connected is True
        assert len(bot.open_positions) == 2
        assert len(bot.pending_orders) == 1
        assert bot.total_trades == 15
        assert bot.realized_pnl == 1500.0
        assert bot.unrealized_pnl == 750.0
        assert bot.peak_equity == 105000.0
        assert bot.current_equity == 102250.0
        assert bot.daily_pnl == 250.0

    def test_bot_status_transitions(self):
        """Test bot status values."""
        bot_config = BotConfig(
            id="bot_003",
            name="Status Test Bot",
            strategy_name="Test",
            strategy_config={},
            trading_config=TradingConfig(execution_model=ExecutionModel.SCHEDULED),
            created_at=datetime.now(),
        )

        for status in ["running", "paused", "stopped", "error"]:
            bot = DeployedBot(
                id=f"bot_{status}",
                config=bot_config,
                status=status,  # type: ignore
                start_time=datetime.now(),
            )
            assert bot.status == status

    def test_paused_bot(self):
        """Test paused bot retains positions."""
        bot_config = BotConfig(
            id="bot_004",
            name="Paused Bot",
            strategy_name="Test",
            strategy_config={},
            trading_config=TradingConfig(execution_model=ExecutionModel.SCHEDULED),
            created_at=datetime.now(),
        )

        positions = [
            Position(
                symbol="SPY",
                qty=100,
                side="long",
                entry_price=450.0,
                current_price=455.0,
                unrealized_pnl=500.0,
                market_value=45500.0,
            )
        ]

        bot = DeployedBot(
            id="deployed_004",
            config=bot_config,
            status="paused",
            open_positions=positions,
            start_time=datetime.now(),
            total_trades=5,
            realized_pnl=500.0,
        )

        assert bot.status == "paused"
        assert len(bot.open_positions) == 1
        assert bot.total_trades == 5


class TestAccountInfo:
    """Test AccountInfo model."""

    def test_account_info(self):
        """Test account info creation."""
        account = AccountInfo(
            account_id="ACC123456",
            buying_power=50000.0,
            cash=25000.0,
            portfolio_value=100000.0,
            equity=100000.0,
        )
        assert account.account_id == "ACC123456"
        assert account.buying_power == 50000.0
        assert account.cash == 25000.0
        assert account.portfolio_value == 100000.0
        assert account.equity == 100000.0

    def test_paper_account(self):
        """Test paper trading account."""
        account = AccountInfo(
            account_id="PAPER_ACCOUNT",
            buying_power=100000.0,
            cash=100000.0,
            portfolio_value=100000.0,
            equity=100000.0,
        )
        assert account.account_id == "PAPER_ACCOUNT"
        assert account.cash == account.equity

    def test_margin_account(self):
        """Test margin account with buying power > cash."""
        account = AccountInfo(
            account_id="MARGIN_ACCOUNT",
            buying_power=200000.0,  # 2x leverage
            cash=100000.0,
            portfolio_value=150000.0,
            equity=150000.0,
        )
        assert account.buying_power > account.cash
        assert account.buying_power == 200000.0
