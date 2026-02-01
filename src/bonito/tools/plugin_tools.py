"""Plugin tools for the agent - Allow agent to discover and use strategy plugins."""

from datetime import datetime
from typing import Any

from bonito.backtest.models import BacktestConfig
from bonito.backtest.plugin_adapter import PluginAdapter
from bonito.backtest.plugin_registry import get_plugin_registry
from bonito.data.store import MarketDataStore
from bonito.tools.base import Tool, ToolResult


class PluginListTool(Tool):
    """List all available strategy plugins."""

    @property
    def name(self) -> str:
        return "plugin_list"

    @property
    def description(self) -> str:
        return """List all available strategy plugins.

Returns information about each plugin including:
- Name: unique identifier
- Description: what the plugin does
- Parameters: configurable settings with types and defaults

Use this to discover what plugins are available before running backtests."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """List all available plugins."""
        try:
            registry = get_plugin_registry()
            plugins = registry.get_all_info()

            if not plugins:
                return ToolResult(
                    success=True,
                    data={
                        "plugins": [],
                        "message": "No plugins found. Plugins should be placed in strategies/plugins/",
                    },
                )

            return ToolResult(
                success=True,
                data={
                    "plugins": plugins,
                    "count": len(plugins),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to list plugins: {e!s}",
            )


class PluginParamsTool(Tool):
    """Get detailed parameter information for a specific plugin."""

    @property
    def name(self) -> str:
        return "plugin_params"

    @property
    def description(self) -> str:
        return """Get detailed parameter information for a specific plugin.

Returns the parameter schema including:
- Type (int, float, str, bool)
- Default value
- Min/max constraints (for numeric parameters)
- Description

Use this to understand what parameters a plugin accepts before running it."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "Name of the plugin to get parameters for",
                },
            },
            "required": ["plugin_name"],
        }

    async def execute(self, plugin_name: str, **kwargs: Any) -> ToolResult:
        """Get parameters for a specific plugin."""
        try:
            registry = get_plugin_registry()
            info = registry.get_plugin_info(plugin_name)

            if info is None:
                available = registry.list_names()
                return ToolResult(
                    success=False,
                    error=f"Plugin '{plugin_name}' not found. Available plugins: {available}",
                )

            return ToolResult(
                success=True,
                data=info,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to get plugin parameters: {e!s}",
            )


class PluginBacktestTool(Tool):
    """Run a backtest using a strategy plugin."""

    @property
    def name(self) -> str:
        return "plugin_backtest"

    @property
    def description(self) -> str:
        return """Run a backtest using a strategy plugin.

Executes the plugin's signal generation logic and simulates trades.
Returns the same metrics as a regular backtest:
- Total and annualized returns
- Sharpe/Sortino ratios
- Maximum drawdown
- Win rate and profit factor
- Trade list

Parameters can be customized to tune the strategy.
Optional stop loss and take profit can be added."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "Name of the plugin to run",
                },
                "symbol": {
                    "type": "string",
                    "description": "Symbol to backtest on (e.g., 'SPY', 'AAPL')",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "params": {
                    "type": "object",
                    "description": "Plugin parameters (uses defaults if not specified)",
                    "default": {},
                },
                "position_size_pct": {
                    "type": "number",
                    "description": "Position size as percentage of equity (default: 100)",
                    "default": 100,
                },
                "stop_loss_pct": {
                    "type": "number",
                    "description": "Optional stop loss percentage (e.g., 0.05 for 5%)",
                },
                "take_profit_pct": {
                    "type": "number",
                    "description": "Optional take profit percentage (e.g., 0.10 for 10%)",
                },
                "initial_capital": {
                    "type": "number",
                    "description": "Starting capital (default: 100000)",
                    "default": 100000,
                },
            },
            "required": ["plugin_name", "symbol", "start_date", "end_date"],
        }

    async def execute(
        self,
        plugin_name: str,
        symbol: str,
        start_date: str,
        end_date: str,
        params: dict | None = None,
        position_size_pct: float = 100.0,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        initial_capital: float = 100_000,
        **kwargs: Any,
    ) -> ToolResult:
        """Run a backtest with a plugin."""
        try:
            # Get the plugin
            registry = get_plugin_registry()
            plugin = registry.get(plugin_name)

            if plugin is None:
                available = registry.list_names()
                return ToolResult(
                    success=False,
                    error=f"Plugin '{plugin_name}' not found. Available plugins: {available}",
                )

            # Parse dates
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            # Get data
            store = MarketDataStore()
            data = store.get_bars(symbol, start, end, "1d")

            if data is None:
                return ToolResult(
                    success=False,
                    error=f"No data found for {symbol}. Please ingest data first.",
                )

            # Run backtest
            config = BacktestConfig(
                start_date=start,
                end_date=end,
                initial_capital=initial_capital,
            )
            adapter = PluginAdapter(config)

            result = adapter.run(
                plugin=plugin,
                data=data,
                params=params or {},
                position_size_pct=position_size_pct,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
            )

            # Return summary data
            return ToolResult(
                success=True,
                data={
                    "strategy_name": result.strategy_name,
                    "symbol": result.symbol,
                    "period": f"{start_date} to {end_date}",
                    "params_used": plugin.validate_params(params or {}),
                    "initial_capital": result.initial_capital,
                    "final_capital": round(result.final_capital, 2),
                    "metrics": {
                        "total_return": round(result.metrics.total_return * 100, 2),
                        "annualized_return": round(result.metrics.annualized_return * 100, 2),
                        "sharpe_ratio": round(result.metrics.sharpe_ratio, 2),
                        "sortino_ratio": round(result.metrics.sortino_ratio, 2),
                        "max_drawdown": round(result.metrics.max_drawdown * 100, 2),
                        "total_trades": result.metrics.total_trades,
                        "win_rate": round(result.metrics.win_rate * 100, 1),
                        "profit_factor": round(result.metrics.profit_factor, 2),
                        "avg_win": round(result.metrics.average_win * 100, 2),
                        "avg_loss": round(result.metrics.average_loss * 100, 2),
                    },
                    "trade_count": len(result.trades),
                    "summary": result.summary(),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Plugin backtest failed: {e!s}",
            )
