"""Trading tools for agent-assisted bot management."""

import uuid
from datetime import UTC, datetime
from typing import Any

from bonito.config import settings
from bonito.tools.base import Tool, ToolResult
from bonito.trading.alpaca_broker import AlpacaBroker
from bonito.trading.bot import TradingBot
from bonito.trading.bot_registry import BotRegistry
from bonito.trading.credential_store import CredentialStore, get_credential_password
from bonito.trading.models import BotConfig, ExecutionModel, TradingConfig
from bonito.trading.risk import calculate_risk_score, should_require_acknowledgment

_credential_store = CredentialStore()


class DeployBotTool(Tool):
    """Deploy a validated strategy as a trading bot."""

    @property
    def name(self) -> str:
        return "deploy_bot"

    @property
    def description(self) -> str:
        return """Deploy a backtested strategy to paper or live trading.

IMPORTANT: This will execute real trades. Review the risk warnings carefully.
User must acknowledge risks before deployment.

Args:
    strategy_name: Name of the strategy to deploy
    strategy_config: Strategy configuration dict
    mode: Trading mode - "paper" or "live" (default: paper)
    execution_model: "scheduled", "continuous", or "event_driven"
    schedule: Cron expression for scheduled execution (optional)
    max_position_pct: Maximum position size as % of portfolio (default: 10)
    max_daily_loss_pct: Daily loss limit as % to auto-stop (optional)
    acknowledge_risks: Must be true if the computed risk score is high/extreme

Returns:
    Bot ID and deployment status with risk warnings"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_name": {
                    "type": "string",
                    "description": "Name of the strategy",
                },
                "strategy_config": {
                    "type": "object",
                    "description": "Strategy configuration",
                },
                "mode": {
                    "type": "string",
                    "enum": ["paper", "live"],
                    "default": "paper",
                    "description": "Trading mode",
                },
                "execution_model": {
                    "type": "string",
                    "enum": ["scheduled", "continuous", "event_driven"],
                    "description": "Execution model for the bot",
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron expression for scheduled mode",
                },
                "max_position_pct": {
                    "type": "number",
                    "default": 10.0,
                    "description": "Maximum position size as % of portfolio",
                },
                "max_daily_loss_pct": {
                    "type": "number",
                    "description": "Optional circuit breaker for daily losses",
                },
                "acknowledge_risks": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true to deploy a bot with high/extreme risk score",
                },
            },
            "required": ["strategy_name", "strategy_config", "execution_model"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            mode = kwargs.get("mode", "paper")
            if mode == "live" and not settings.alpaca_live_trading_enabled:
                return ToolResult(
                    success=False,
                    error="Live trading is disabled. An operator must set "
                    "ALPACA_LIVE_TRADING_ENABLED=true in the environment before "
                    "real-money bots can be deployed.",
                )

            # Load credentials from store
            if not _credential_store.has_credentials():
                return ToolResult(
                    success=False,
                    error="No credentials linked. Please link your Alpaca account first using the /api/trading/account/link endpoint.",
                )
            credentials = _credential_store.load_credentials(get_credential_password())
            if not credentials:
                return ToolResult(
                    success=False,
                    error="No credentials linked. Please link your Alpaca account first using the /api/trading/account/link endpoint.",
                )

            # Create trading config
            trading_config = TradingConfig(
                mode=mode,
                execution_model=ExecutionModel(kwargs["execution_model"]),
                schedule=kwargs.get("schedule"),
                max_position_pct=kwargs.get("max_position_pct", 10.0),
                max_daily_loss_pct=kwargs.get("max_daily_loss_pct"),
            )

            # Create bot config
            bot_config = BotConfig(
                id=str(uuid.uuid4()),
                name=f"{kwargs['strategy_name']}_bot",
                strategy_name=kwargs["strategy_name"],
                strategy_config=kwargs["strategy_config"],
                trading_config=trading_config,
                created_at=datetime.now(UTC),
            )

            # Calculate risk score
            risk_score, warnings = calculate_risk_score(bot_config)
            bot_config.risk_score = risk_score
            bot_config.risk_warnings = warnings

            if should_require_acknowledgment(risk_score) and not kwargs.get(
                "acknowledge_risks", False
            ):
                return ToolResult(
                    success=False,
                    error=f"Risk acknowledgment required (risk_score={risk_score}). "
                    f"Warnings: {'; '.join(warnings)}. Pass acknowledge_risks=true to proceed.",
                )

            # Create broker with real credentials
            broker = AlpacaBroker(
                api_key=credentials.api_key.get_secret_value(),
                secret_key=credentials.secret_key.get_secret_value(),
                mode=trading_config.mode,
            )

            # Create and register bot
            bot = TradingBot(bot_config, broker)
            registry = BotRegistry()
            registry.register(bot)

            # Start the bot
            await bot.start()

            return ToolResult(
                success=True,
                data={
                    "bot_id": bot_config.id,
                    "name": bot_config.name,
                    "status": bot.status,
                    "mode": trading_config.mode,
                    "risk_score": risk_score,
                    "risk_warnings": warnings,
                    "message": f"Bot deployed successfully. Risk level: {risk_score.upper()}",
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListBotsTool(Tool):
    """List all deployed trading bots."""

    @property
    def name(self) -> str:
        return "list_bots"

    @property
    def description(self) -> str:
        return """List all deployed trading bots with their current status.

Returns a list of all bots with their ID, name, status, and performance summary."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "running", "paused", "stopped"],
                    "default": "all",
                    "description": "Filter bots by status",
                }
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            registry = BotRegistry()
            status_filter = kwargs.get("status_filter", "all")

            if status_filter == "all":
                bots = registry.list_all()
            else:
                bots = registry.list_by_status(status_filter)

            bot_summaries = []
            for bot in bots:
                state = bot.get_deployed_bot_state()
                bot_summaries.append(
                    {
                        "id": state.id,
                        "name": state.config.name,
                        "status": state.status,
                        "mode": state.config.trading_config.mode,
                        "strategy": state.config.strategy_name,
                        "total_trades": state.total_trades,
                        "realized_pnl": state.realized_pnl,
                        "unrealized_pnl": state.unrealized_pnl,
                    }
                )

            return ToolResult(
                success=True, data={"total": len(bot_summaries), "bots": bot_summaries}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BotStatusTool(Tool):
    """Get detailed status of a specific bot."""

    @property
    def name(self) -> str:
        return "bot_status"

    @property
    def description(self) -> str:
        return """Get detailed status of a trading bot including positions, P&L, and trade history.

Args:
    bot_id: The ID of the bot to check"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"bot_id": {"type": "string", "description": "ID of the bot"}},
            "required": ["bot_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            registry = BotRegistry()
            bot = registry.get(kwargs["bot_id"])

            if not bot:
                return ToolResult(success=False, error=f"Bot {kwargs['bot_id']} not found")

            state = bot.get_deployed_bot_state()

            return ToolResult(
                success=True,
                data={
                    "id": state.id,
                    "name": state.config.name,
                    "status": state.status,
                    "mode": state.config.trading_config.mode,
                    "strategy": state.config.strategy_name,
                    "broker_connected": state.broker_connected,
                    "start_time": state.start_time.isoformat(),
                    "positions": [p.model_dump() for p in state.open_positions],
                    "pending_orders": [o.model_dump() for o in state.pending_orders],
                    "performance": {
                        "total_trades": state.total_trades,
                        "realized_pnl": state.realized_pnl,
                        "unrealized_pnl": state.unrealized_pnl,
                        "daily_pnl": state.daily_pnl,
                        "current_equity": state.current_equity,
                    },
                    "risk": {
                        "score": state.config.risk_score,
                        "warnings": state.config.risk_warnings,
                    },
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PauseBotTool(Tool):
    """Pause a running bot."""

    @property
    def name(self) -> str:
        return "pause_bot"

    @property
    def description(self) -> str:
        return """Pause a running trading bot. The bot will stop making new trades but keep existing positions.

Args:
    bot_id: The ID of the bot to pause"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"bot_id": {"type": "string", "description": "ID of the bot"}},
            "required": ["bot_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            registry = BotRegistry()
            bot = registry.get(kwargs["bot_id"])

            if not bot:
                return ToolResult(success=False, error=f"Bot {kwargs['bot_id']} not found")

            await bot.pause()

            return ToolResult(
                success=True,
                data={
                    "bot_id": kwargs["bot_id"],
                    "status": bot.status,
                    "message": "Bot paused successfully",
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ResumeBotTool(Tool):
    """Resume a paused bot."""

    @property
    def name(self) -> str:
        return "resume_bot"

    @property
    def description(self) -> str:
        return """Resume a paused trading bot.

Args:
    bot_id: The ID of the bot to resume"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"bot_id": {"type": "string", "description": "ID of the bot"}},
            "required": ["bot_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            registry = BotRegistry()
            bot = registry.get(kwargs["bot_id"])

            if not bot:
                return ToolResult(success=False, error=f"Bot {kwargs['bot_id']} not found")

            await bot.resume()

            return ToolResult(
                success=True,
                data={
                    "bot_id": kwargs["bot_id"],
                    "status": bot.status,
                    "message": "Bot resumed successfully",
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class StopBotTool(Tool):
    """Stop a bot and optionally close positions."""

    @property
    def name(self) -> str:
        return "stop_bot"

    @property
    def description(self) -> str:
        return """Stop a trading bot completely. Optionally close all open positions.

Args:
    bot_id: The ID of the bot to stop
    close_positions: Whether to close all positions (default: False)"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bot_id": {"type": "string", "description": "ID of the bot"},
                "close_positions": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to close all positions",
                },
            },
            "required": ["bot_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            registry = BotRegistry()
            bot = registry.get(kwargs["bot_id"])

            if not bot:
                return ToolResult(success=False, error=f"Bot {kwargs['bot_id']} not found")

            close_positions = kwargs.get("close_positions", False)
            await bot.stop(close_positions=close_positions)

            # Unregister from registry
            registry.unregister(kwargs["bot_id"])

            return ToolResult(
                success=True,
                data={
                    "bot_id": kwargs["bot_id"],
                    "status": bot.status,
                    "positions_closed": close_positions,
                    "message": "Bot stopped successfully",
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ModifyBotTool(Tool):
    """Modify a running bot's configuration."""

    @property
    def name(self) -> str:
        return "modify_bot"

    @property
    def description(self) -> str:
        return """Modify a running bot's trading configuration.

Args:
    bot_id: The ID of the bot to modify
    max_position_pct: New maximum position size (optional)
    max_daily_loss_pct: New daily loss limit (optional)"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bot_id": {"type": "string", "description": "ID of the bot"},
                "max_position_pct": {
                    "type": "number",
                    "description": "New maximum position size",
                },
                "max_daily_loss_pct": {
                    "type": "number",
                    "description": "New daily loss limit",
                },
            },
            "required": ["bot_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            registry = BotRegistry()
            bot = registry.get(kwargs["bot_id"])

            if not bot:
                return ToolResult(success=False, error=f"Bot {kwargs['bot_id']} not found")

            modified = []
            if "max_position_pct" in kwargs:
                bot.config.trading_config.max_position_pct = kwargs["max_position_pct"]
                modified.append("max_position_pct")

            if "max_daily_loss_pct" in kwargs:
                bot.config.trading_config.max_daily_loss_pct = kwargs["max_daily_loss_pct"]
                modified.append("max_daily_loss_pct")

            # Recalculate risk score
            risk_score, warnings = calculate_risk_score(bot.config)
            bot.config.risk_score = risk_score
            bot.config.risk_warnings = warnings

            return ToolResult(
                success=True,
                data={
                    "bot_id": kwargs["bot_id"],
                    "modified": modified,
                    "new_risk_score": risk_score,
                    "message": f"Bot configuration updated: {', '.join(modified)}",
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# Export all tools
TRADING_TOOLS = [
    DeployBotTool(),
    ListBotsTool(),
    BotStatusTool(),
    PauseBotTool(),
    ResumeBotTool(),
    StopBotTool(),
    ModifyBotTool(),
]
