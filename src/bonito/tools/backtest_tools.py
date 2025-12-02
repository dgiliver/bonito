"""Backtesting tools for the agent."""

from datetime import datetime
from typing import Any

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import StrategyConfig
from bonito.data.store import MarketDataStore
from bonito.tools.base import Tool, ToolResult


class BacktestRunTool(Tool):
    """Run a backtest for a strategy configuration."""

    @property
    def name(self) -> str:
        return "backtest_run"

    @property
    def description(self) -> str:
        return """Run a backtest for a trading strategy.

Takes a strategy configuration and returns performance metrics including:
- Total and annualized returns
- Sharpe ratio and Sortino ratio
- Maximum drawdown
- Win rate and profit factor
- List of all trades

Use this to evaluate how a strategy would have performed historically."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "object",
                    "description": "The strategy configuration to backtest",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "initial_capital": {
                    "type": "number",
                    "description": "Starting capital (default: 100000)",
                    "default": 100000,
                },
            },
            "required": ["strategy", "start_date", "end_date"],
        }

    async def execute(
        self,
        strategy: dict,
        start_date: str,
        end_date: str,
        initial_capital: float = 100_000,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the backtest."""
        try:
            # Parse strategy config
            strategy_config = StrategyConfig(**strategy)

            # Parse dates
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            # Get data
            store = MarketDataStore()
            symbol = strategy_config.symbols[0]  # MVP: single symbol
            data = store.get_bars(symbol, start, end, strategy_config.timeframe)

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
            engine = BacktestEngine(config)
            result = engine.run(strategy_config, data)

            # Return summary data (not full equity curve to save tokens)
            return ToolResult(
                success=True,
                data={
                    "strategy_name": result.strategy_name,
                    "symbol": result.symbol,
                    "period": f"{start_date} to {end_date}",
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
                error=f"Backtest failed: {str(e)}",
            )


class BacktestExplainTool(Tool):
    """Explain why specific trades were taken."""

    @property
    def name(self) -> str:
        return "backtest_explain"

    @property
    def description(self) -> str:
        return """Explain the reasoning behind trades in a backtest.

Provides detailed information about:
- Which indicators triggered entry/exit
- The state of all indicators at trade time
- Why stop losses or take profits were hit

Use this to understand and debug strategy behavior."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "object",
                    "description": "The strategy configuration",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "max_trades": {
                    "type": "integer",
                    "description": "Maximum number of trades to explain (default: 5)",
                    "default": 5,
                },
            },
            "required": ["strategy", "start_date", "end_date"],
        }

    async def execute(
        self,
        strategy: dict,
        start_date: str,
        end_date: str,
        max_trades: int = 5,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the explanation."""
        # TODO: Implement detailed trade explanation
        # For MVP, this returns a simplified version

        try:
            strategy_config = StrategyConfig(**strategy)

            return ToolResult(
                success=True,
                data={
                    "message": "Trade explanation not yet fully implemented",
                    "strategy_description": strategy_config.to_prompt_description(),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Explanation failed: {str(e)}",
            )
