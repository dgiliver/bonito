"""Tool layer for agent interactions."""

from bonito.tools.backtest_tools import BacktestExplainTool, BacktestRunTool
from bonito.tools.base import Tool, ToolRegistry, ToolResult
from bonito.tools.data_tools import GetBarsTool, ListSymbolsTool
from bonito.tools.plugin_tools import PluginBacktestTool, PluginListTool, PluginParamsTool
from bonito.tools.strategy_tools import ValidateStrategyTool

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

    return registry
