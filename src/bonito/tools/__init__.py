"""Tool layer for agent interactions."""

from bonito.tools.backtest_tools import BacktestExplainTool, BacktestRunTool
from bonito.tools.base import Tool, ToolRegistry, ToolResult
from bonito.tools.data_tools import GetBarsTool, ListSymbolsTool
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

    return registry
