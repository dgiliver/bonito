"""Tests for trading agent tools."""

import os

import pytest

from bonito.tools.trading_tools import (
    TRADING_TOOLS,
    BotStatusTool,
    DeployBotTool,
    ListBotsTool,
    ModifyBotTool,
    PauseBotTool,
    ResumeBotTool,
    StopBotTool,
)
from bonito.trading.bot_registry import BotRegistry
from bonito.trading.credential_store import CredentialStore
from bonito.trading.credentials import AlpacaCredentials

# Minimal valid strategy configs for testing
VALID_STRATEGY_CONFIG = {
    "name": "test_strategy",
    "symbols": ["SPY"],
    "entry_rules": [
        {"conditions": [{"left": "close", "comparison": "crosses_above", "right": "sma_20"}]}
    ],
}

STRATEGY_WITH_STOP_LOSS = {
    **VALID_STRATEGY_CONFIG,
    "stop_loss": {"type": "percent", "value": 0.02},
}


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset bot registry before each test."""
    BotRegistry.reset()
    yield
    BotRegistry.reset()


@pytest.fixture(autouse=True)
def setup_credentials(credential_password):
    """Setup mock credentials for all tests."""
    os.environ["BONITO_USE_MOCK_ALPACA_API"] = "true"

    # Create and store credentials
    store = CredentialStore()
    credentials = AlpacaCredentials(
        api_key="PKABCDEFGHIJ12345678ABCD",
        secret_key="A" * 44,
        is_paper=True,
    )
    store.store_credentials(credentials, os.environ["BONITO_CREDENTIAL_PASSWORD"])

    yield

    # Clean up
    store.delete_credentials()
    del os.environ["BONITO_USE_MOCK_ALPACA_API"]


class TestDeployBotTool:
    @pytest.mark.asyncio
    async def test_deploy_paper_bot(self):
        tool = DeployBotTool()
        result = await tool.execute(
            strategy_name="momentum",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
            mode="paper",
        )

        assert result.success is True
        assert "bot_id" in result.data
        assert result.data["mode"] == "paper"
        assert result.data["status"] == "running"

    @pytest.mark.asyncio
    async def test_deploy_with_risk_warnings(self):
        tool = DeployBotTool()
        result = await tool.execute(
            strategy_name="risky_strategy",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="continuous",
            mode="paper",
            max_position_pct=95.0,
            acknowledge_risks=True,
        )

        assert result.success is True
        assert result.data["risk_score"] in ["high", "extreme"]
        assert len(result.data["risk_warnings"]) > 0

    @pytest.mark.asyncio
    async def test_deploy_with_custom_position_size(self):
        tool = DeployBotTool()
        result = await tool.execute(
            strategy_name="conservative",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
            max_position_pct=5.0,
            max_daily_loss_pct=2.0,  # Add daily loss limit to get low risk
        )

        assert result.success is True
        assert result.data["risk_score"] == "low"

    @pytest.mark.asyncio
    async def test_deploy_with_daily_loss_limit(self):
        tool = DeployBotTool()
        result = await tool.execute(
            strategy_name="protected",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="event_driven",
            max_daily_loss_pct=3.0,
        )

        assert result.success is True
        assert "bot_id" in result.data

    @pytest.mark.asyncio
    async def test_deploy_live_blocked_by_default(self):
        """Live trading requires an operator to set ALPACA_LIVE_TRADING_ENABLED."""
        tool = DeployBotTool()
        result = await tool.execute(
            strategy_name="risky",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="continuous",
            mode="live",
            acknowledge_risks=True,
        )

        assert result.success is False
        assert "Live trading is disabled" in result.error

    @pytest.mark.asyncio
    async def test_deploy_live_allowed_when_enabled(self, monkeypatch):
        from bonito.tools import trading_tools

        monkeypatch.setattr(trading_tools.settings, "alpaca_live_trading_enabled", True)

        tool = DeployBotTool()
        result = await tool.execute(
            strategy_name="risky",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="continuous",
            mode="live",
            acknowledge_risks=True,
        )

        assert result.success is True
        assert result.data["mode"] == "live"


class TestListBotsTool:
    @pytest.mark.asyncio
    async def test_list_empty(self):
        tool = ListBotsTool()
        result = await tool.execute()

        assert result.success is True
        assert result.data["total"] == 0
        assert result.data["bots"] == []

    @pytest.mark.asyncio
    async def test_list_with_bots(self):
        # Deploy a bot first
        deploy = DeployBotTool()
        await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )

        # List bots
        tool = ListBotsTool()
        result = await tool.execute()

        assert result.success is True
        assert result.data["total"] == 1
        assert len(result.data["bots"]) == 1
        assert result.data["bots"][0]["strategy"] == "test"

    @pytest.mark.asyncio
    async def test_list_with_multiple_bots(self):
        # Deploy multiple bots
        deploy = DeployBotTool()
        for i in range(3):
            await deploy.execute(
                strategy_name=f"strategy_{i}",
                strategy_config=STRATEGY_WITH_STOP_LOSS,
                execution_model="scheduled",
            )

        # List all
        tool = ListBotsTool()
        result = await tool.execute()

        assert result.success is True
        assert result.data["total"] == 3

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self):
        # Deploy and pause a bot
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test1",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        pause = PauseBotTool()
        await pause.execute(bot_id=bot_id)

        # List only paused
        tool = ListBotsTool()
        result = await tool.execute(status_filter="paused")

        assert result.success is True
        assert result.data["total"] == 1
        assert result.data["bots"][0]["status"] == "paused"

    @pytest.mark.asyncio
    async def test_list_filter_running(self):
        # Deploy two bots, pause one
        deploy = DeployBotTool()
        result1 = await deploy.execute(
            strategy_name="test1",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        await deploy.execute(
            strategy_name="test2",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )

        pause = PauseBotTool()
        await pause.execute(bot_id=result1.data["bot_id"])

        # List only running
        tool = ListBotsTool()
        result = await tool.execute(status_filter="running")

        assert result.success is True
        assert result.data["total"] == 1


class TestBotStatusTool:
    @pytest.mark.asyncio
    async def test_status_not_found(self):
        tool = BotStatusTool()
        result = await tool.execute(bot_id="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_status_existing_bot(self):
        # Deploy first
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Get status
        tool = BotStatusTool()
        result = await tool.execute(bot_id=bot_id)

        assert result.success is True
        assert result.data["id"] == bot_id
        assert "performance" in result.data
        assert "risk" in result.data
        assert "positions" in result.data
        assert "pending_orders" in result.data

    @pytest.mark.asyncio
    async def test_status_includes_risk_info(self):
        # Deploy with high risk
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="risky",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="continuous",
            mode="paper",
            max_position_pct=80.0,
            acknowledge_risks=True,
        )
        bot_id = deploy_result.data["bot_id"]

        # Get status
        tool = BotStatusTool()
        result = await tool.execute(bot_id=bot_id)

        assert result.success is True
        assert result.data["risk"]["score"] in ["high", "extreme"]
        assert len(result.data["risk"]["warnings"]) > 0


class TestPauseBotTool:
    @pytest.mark.asyncio
    async def test_pause_not_found(self):
        tool = PauseBotTool()
        result = await tool.execute(bot_id="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_pause_running_bot(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Pause
        tool = PauseBotTool()
        result = await tool.execute(bot_id=bot_id)

        assert result.success is True
        assert result.data["status"] == "paused"
        assert "message" in result.data

    @pytest.mark.asyncio
    async def test_pause_already_paused_fails(self):
        # Deploy and pause
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        pause = PauseBotTool()
        await pause.execute(bot_id=bot_id)

        # Try to pause again
        result = await pause.execute(bot_id=bot_id)

        assert result.success is False


class TestResumeBotTool:
    @pytest.mark.asyncio
    async def test_resume_not_found(self):
        tool = ResumeBotTool()
        result = await tool.execute(bot_id="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resume_paused_bot(self):
        # Deploy and pause
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        pause = PauseBotTool()
        await pause.execute(bot_id=bot_id)

        # Resume
        tool = ResumeBotTool()
        result = await tool.execute(bot_id=bot_id)

        assert result.success is True
        assert result.data["status"] == "running"

    @pytest.mark.asyncio
    async def test_resume_running_bot_fails(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Try to resume running bot
        tool = ResumeBotTool()
        result = await tool.execute(bot_id=bot_id)

        assert result.success is False


class TestStopBotTool:
    @pytest.mark.asyncio
    async def test_stop_not_found(self):
        tool = StopBotTool()
        result = await tool.execute(bot_id="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_stop_bot(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Stop
        tool = StopBotTool()
        result = await tool.execute(bot_id=bot_id)

        assert result.success is True
        assert result.data["status"] == "stopped"

        # Verify unregistered
        list_tool = ListBotsTool()
        list_result = await list_tool.execute()
        assert list_result.data["total"] == 0

    @pytest.mark.asyncio
    async def test_stop_with_close_positions(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Stop with close_positions
        tool = StopBotTool()
        result = await tool.execute(bot_id=bot_id, close_positions=True)

        assert result.success is True
        assert result.data["positions_closed"] is True

    @pytest.mark.asyncio
    async def test_stop_without_close_positions(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Stop without closing
        tool = StopBotTool()
        result = await tool.execute(bot_id=bot_id, close_positions=False)

        assert result.success is True
        assert result.data["positions_closed"] is False


class TestModifyBotTool:
    @pytest.mark.asyncio
    async def test_modify_not_found(self):
        tool = ModifyBotTool()
        result = await tool.execute(bot_id="nonexistent", max_position_pct=5.0)

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_modify_position_size(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
            max_position_pct=10.0,
        )
        bot_id = deploy_result.data["bot_id"]

        # Modify
        tool = ModifyBotTool()
        result = await tool.execute(bot_id=bot_id, max_position_pct=5.0)

        assert result.success is True
        assert "max_position_pct" in result.data["modified"]
        assert "new_risk_score" in result.data

    @pytest.mark.asyncio
    async def test_modify_daily_loss_limit(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Modify
        tool = ModifyBotTool()
        result = await tool.execute(bot_id=bot_id, max_daily_loss_pct=2.0)

        assert result.success is True
        assert "max_daily_loss_pct" in result.data["modified"]

    @pytest.mark.asyncio
    async def test_modify_both_params(self):
        # Deploy
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
        )
        bot_id = deploy_result.data["bot_id"]

        # Modify both
        tool = ModifyBotTool()
        result = await tool.execute(bot_id=bot_id, max_position_pct=8.0, max_daily_loss_pct=3.0)

        assert result.success is True
        assert len(result.data["modified"]) == 2
        assert "max_position_pct" in result.data["modified"]
        assert "max_daily_loss_pct" in result.data["modified"]

    @pytest.mark.asyncio
    async def test_modify_recalculates_risk(self):
        # Deploy with low risk
        deploy = DeployBotTool()
        deploy_result = await deploy.execute(
            strategy_name="test",
            strategy_config=STRATEGY_WITH_STOP_LOSS,
            execution_model="scheduled",
            max_position_pct=10.0,
        )
        bot_id = deploy_result.data["bot_id"]

        # Modify to high risk
        tool = ModifyBotTool()
        result = await tool.execute(bot_id=bot_id, max_position_pct=95.0)

        assert result.success is True
        assert result.data["new_risk_score"] in ["high", "extreme"]


class TestTradingToolsExport:
    def test_all_tools_exported(self):
        assert len(TRADING_TOOLS) == 7
        tool_names = [t.name for t in TRADING_TOOLS]
        assert "deploy_bot" in tool_names
        assert "list_bots" in tool_names
        assert "bot_status" in tool_names
        assert "pause_bot" in tool_names
        assert "resume_bot" in tool_names
        assert "stop_bot" in tool_names
        assert "modify_bot" in tool_names

    def test_tool_descriptions_not_empty(self):
        for tool in TRADING_TOOLS:
            assert len(tool.description) > 0
            assert tool.name
            assert tool.parameters

    def test_tool_parameters_valid_json_schema(self):
        for tool in TRADING_TOOLS:
            params = tool.parameters
            assert "type" in params
            assert params["type"] == "object"
            assert "properties" in params
