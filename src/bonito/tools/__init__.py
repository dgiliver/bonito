"""Tool layer for agent interactions."""

from bonito.tools.backtest_tools import BacktestExplainTool, BacktestRunTool
from bonito.tools.base import Tool, ToolRegistry, ToolResult
from bonito.tools.data_tools import GetBarsTool, ListSymbolsTool
from bonito.tools.plugin_tools import PluginBacktestTool, PluginListTool, PluginParamsTool
from bonito.tools.strategy_tools import ValidateStrategyTool
from bonito.tools.trading_tools import (
    BotStatusTool,
    DeployBotTool,
    ListBotsTool,
    ModifyBotTool,
    PauseBotTool,
    ResumeBotTool,
    StopBotTool,
)

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "BacktestRunTool",
    "BacktestExplainTool",
    "GetBarsTool",
    "ListSymbolsTool",
    "ValidateStrategyTool",
    "PluginListTool",
    "PluginParamsTool",
    "PluginBacktestTool",
    "DeployBotTool",
    "ListBotsTool",
    "BotStatusTool",
    "PauseBotTool",
    "ResumeBotTool",
    "StopBotTool",
    "ModifyBotTool",
]


def create_default_registry() -> ToolRegistry:
    """Create a registry with all default tools."""
    registry = ToolRegistry()

    # Register all tools
    registry.register(BacktestRunTool())
    registry.register(BacktestExplainTool())
    registry.register(GetBarsTool())
    registry.register(ListSymbolsTool())
    registry.register(ValidateStrategyTool())

    # Plugin tools (F002)
    registry.register(PluginListTool())
    registry.register(PluginParamsTool())
    registry.register(PluginBacktestTool())

    # Trading tools (Phase 4)
    registry.register(DeployBotTool())
    registry.register(ListBotsTool())
    registry.register(BotStatusTool())
    registry.register(PauseBotTool())
    registry.register(ResumeBotTool())
    registry.register(StopBotTool())
    registry.register(ModifyBotTool())

    return registry
