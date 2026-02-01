"""Agent tools for strategy development and backtesting."""

from datetime import datetime
from typing import Any

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import (
    Comparison,
    IndicatorConfig,
    IndicatorType,
    PositionSizeConfig,
    PositionSizeType,
    Rule,
    RuleCondition,
    StopLossConfig,
    StopLossType,
    StrategyConfig,
    TakeProfitConfig,
    TakeProfitType,
)
from bonito.data.store import MarketDataStore
from bonito.tools.base import Tool, ToolRegistry, ToolResult


class CreateStrategyTool(Tool):
    """Tool for creating trading strategies."""

    def __init__(self, strategy_store: dict[str, StrategyConfig]):
        self._strategies = strategy_store

    @property
    def name(self) -> str:
        return "create_strategy"

    @property
    def description(self) -> str:
        return """Create a new trading strategy with indicators and rules.

Built-in indicator types: sma, ema, rsi, macd, atr, bbands, stoch
Extended indicators (pandas-ta): adx, vwap, obv, supertrend, donchian, cci, mfi, roc, and 130+ more

Available comparisons: gt, gte, lt, lte, eq, crosses_above, crosses_below

Example indicators:
- {"type": "ema", "name": "fast_ema", "params": {"period": 12}}
- {"type": "rsi", "name": "rsi_14", "params": {"period": 14}}
- {"type": "adx", "name": "adx", "params": {"length": 14}}  # Returns adx_adx, adx_dmp, adx_dmn
- {"type": "vwap", "name": "vwap"}
- {"type": "donchian", "name": "dc", "params": {"lower_length": 20, "upper_length": 20}}

Example conditions:
- {"left": "fast_ema", "comparison": "crosses_above", "right": "slow_ema"}
- {"left": "rsi_14", "comparison": "lt", "right": 30}
- {"left": "adx_adx", "comparison": "gt", "right": 25}  # ADX value > 25 (trending)
- {"left": "close", "comparison": "gt", "right": "vwap"}"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique strategy name (snake_case)",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of the strategy",
                },
                "indicators": {
                    "type": "array",
                    "description": "List of indicators to compute. Built-in: sma, ema, rsi, macd, atr, bbands, stoch. Extended: adx, vwap, obv, supertrend, donchian, cci, mfi, roc, etc.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Indicator type (e.g., sma, ema, rsi, adx, vwap)",
                            },
                            "name": {"type": "string"},
                            "params": {"type": "object"},
                        },
                        "required": ["type", "name"],
                    },
                },
                "entry_conditions": {
                    "type": "array",
                    "description": "Conditions that trigger entry (combined with AND)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "left": {
                                "type": "string",
                                "description": "Indicator name or 'close', 'open', 'high', 'low'",
                            },
                            "comparison": {
                                "type": "string",
                                "enum": [
                                    "gt",
                                    "gte",
                                    "lt",
                                    "lte",
                                    "eq",
                                    "crosses_above",
                                    "crosses_below",
                                ],
                            },
                            "right": {
                                "oneOf": [{"type": "string"}, {"type": "number"}],
                                "description": "Indicator name or numeric value",
                            },
                        },
                        "required": ["left", "comparison", "right"],
                    },
                },
                "exit_conditions": {
                    "type": "array",
                    "description": "Conditions that trigger exit (combined with AND). Optional.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "left": {"type": "string"},
                            "comparison": {"type": "string"},
                            "right": {"oneOf": [{"type": "string"}, {"type": "number"}]},
                        },
                    },
                },
                "stop_loss_pct": {
                    "type": "number",
                    "description": "Fixed stop loss as percentage (e.g., 0.05 for 5%). Use this OR trailing_stop_pct, not both.",
                },
                "trailing_stop_pct": {
                    "type": "number",
                    "description": "Trailing stop as percentage (e.g., 0.05 for 5%). Follows price up, protects gains. Better for trending strategies.",
                },
                "trailing_atr_multiple": {
                    "type": "number",
                    "description": "Trailing stop as ATR multiple (e.g., 2.0 for 2x ATR). Adapts to volatility.",
                },
                "atr_period": {
                    "type": "integer",
                    "description": "ATR period for trailing ATR stop (default: 14)",
                    "default": 14,
                },
                "take_profit_pct": {
                    "type": "number",
                    "description": "Take profit as percentage (e.g., 0.10 for 10%)",
                },
                "position_size_pct": {
                    "type": "number",
                    "description": "Position size as % of equity (default: 95)",
                    "default": 95,
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                    "description": "Bar timeframe (default: 1d). Use smaller timeframes for intraday strategies.",
                    "default": "1d",
                },
            },
            "required": ["name", "description", "indicators", "entry_conditions"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            # Parse indicators - support both IndicatorType enum and string (for pandas-ta)
            indicators = []
            for ind in kwargs.get("indicators", []):
                ind_type_str = ind["type"].lower()
                # Try to convert to IndicatorType enum, otherwise use string
                try:
                    ind_type = IndicatorType(ind_type_str)
                except ValueError:
                    # Not a built-in type - use string for pandas-ta indicator
                    ind_type = ind_type_str

                indicators.append(
                    IndicatorConfig(
                        type=ind_type,
                        name=ind["name"],
                        params=ind.get("params", {}),
                    )
                )

            # Parse entry conditions
            entry_conditions = []
            for cond in kwargs.get("entry_conditions", []):
                entry_conditions.append(
                    RuleCondition(
                        left=cond["left"],
                        comparison=Comparison(cond["comparison"]),
                        right=cond["right"],
                    )
                )

            # Parse exit conditions
            exit_conditions = []
            for cond in kwargs.get("exit_conditions", []):
                exit_conditions.append(
                    RuleCondition(
                        left=cond["left"],
                        comparison=Comparison(cond["comparison"]),
                        right=cond["right"],
                    )
                )

            # Build stop loss config
            stop_loss_config = None
            if kwargs.get("trailing_stop_pct"):
                # Trailing percent stop
                stop_loss_config = StopLossConfig(
                    type=StopLossType.TRAILING_PERCENT,
                    value=kwargs["trailing_stop_pct"],
                )
            elif kwargs.get("trailing_atr_multiple"):
                # Trailing ATR stop
                stop_loss_config = StopLossConfig(
                    type=StopLossType.TRAILING_ATR,
                    value=kwargs["trailing_atr_multiple"],
                    atr_period=kwargs.get("atr_period", 14),
                )
            elif kwargs.get("stop_loss_pct"):
                # Fixed percent stop
                stop_loss_config = StopLossConfig(
                    type=StopLossType.PERCENT,
                    value=kwargs["stop_loss_pct"],
                )

            # Build strategy config
            timeframe = kwargs.get("timeframe", "1d")
            strategy = StrategyConfig(
                name=kwargs["name"],
                description=kwargs.get("description", ""),
                symbols=["SPY"],  # Default, can be overridden in backtest
                timeframe=timeframe,  # type: ignore
                indicators=indicators,
                entry_rules=[Rule(conditions=entry_conditions)] if entry_conditions else [],
                exit_rules=[Rule(conditions=exit_conditions)] if exit_conditions else [],
                position_size=PositionSizeConfig(
                    type=PositionSizeType.PERCENT_EQUITY,
                    value=kwargs.get("position_size_pct", 95),
                ),
                stop_loss=stop_loss_config,
                take_profit=TakeProfitConfig(
                    type=TakeProfitType.PERCENT,
                    value=kwargs["take_profit_pct"],
                )
                if kwargs.get("take_profit_pct")
                else None,
            )

            # Store strategy
            self._strategies[strategy.name] = strategy

            return ToolResult(
                success=True,
                data={
                    "strategy_name": strategy.name,
                    "description": strategy.description,
                    "timeframe": strategy.timeframe,
                    "indicators": [i.name for i in strategy.indicators],
                    "entry_rules": len(strategy.entry_rules),
                    "has_stop_loss": strategy.stop_loss is not None,
                    "has_take_profit": strategy.take_profit is not None,
                    "message": f"Strategy '{strategy.name}' created successfully.",
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to create strategy: {e!s}",
            )


class RunBacktestTool(Tool):
    """Tool for running backtests."""

    def __init__(
        self,
        strategy_store: dict[str, StrategyConfig],
        result_store: dict[str, dict[str, Any]],
    ):
        self._strategies = strategy_store
        self._results = result_store

    @property
    def name(self) -> str:
        return "run_backtest"

    @property
    def description(self) -> str:
        return """Run a backtest on a previously created strategy.
Returns performance metrics including total return, Sharpe ratio, max drawdown, and trade statistics."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_name": {
                    "type": "string",
                    "description": "Name of the strategy to backtest",
                },
                "symbol": {
                    "type": "string",
                    "description": "Symbol to backtest (default: SPY)",
                    "default": "SPY",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD), default: 2020-01-01",
                    "default": "2020-01-01",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD), default: 2024-01-01",
                    "default": "2024-01-01",
                },
                "initial_capital": {
                    "type": "number",
                    "description": "Starting capital (default: 100000)",
                    "default": 100000,
                },
            },
            "required": ["strategy_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        strategy_name = kwargs.get("strategy_name")
        symbol = kwargs.get("symbol", "SPY").upper()
        start_date = kwargs.get("start_date", "2020-01-01")
        end_date = kwargs.get("end_date", "2024-01-01")
        initial_capital = kwargs.get("initial_capital", 100000)

        # Get strategy
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            available = list(self._strategies.keys())
            return ToolResult(
                success=False,
                error=f"Strategy '{strategy_name}' not found. Available: {available}",
            )

        # Update symbol
        strategy = strategy.model_copy(update={"symbols": [symbol]})

        # Load data
        store = MarketDataStore()
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            data = store.get_bars(symbol, start_dt, end_dt, strategy.timeframe)
        finally:
            store.close()

        if data is None:
            return ToolResult(
                success=False,
                error=f"No data found for {symbol}. Run 'bonito ingest {symbol}' first.",
            )

        # Run backtest
        config = BacktestConfig(
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=initial_capital,
        )
        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Store result
        result_id = f"{strategy_name}_{symbol}_{start_date}"
        self._results[result_id] = {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "period": f"{start_date} to {end_date}",
            "metrics": result.metrics,
            "trades": result.trades,
        }

        # Calculate buy & hold for comparison
        buy_hold_return = 0.0
        if data.closes is not None and len(data.closes) > 1:
            first_price = data.closes[0]
            last_price = data.closes[-1]
            buy_hold_return = (last_price - first_price) / first_price

        # Format response
        m = result.metrics
        alpha = m.total_return - buy_hold_return  # Strategy outperformance
        return ToolResult(
            success=True,
            data={
                "result_id": result_id,
                "strategy_name": strategy_name,
                "symbol": symbol,
                "period": {"start": start_date, "end": end_date},
                "initial_capital": initial_capital,
                "final_capital": round(result.final_capital, 2),
                "performance": {
                    "total_return": m.total_return * 100,  # As percentage number
                    "sharpe_ratio": round(m.sharpe_ratio, 2),
                    "max_drawdown": m.max_drawdown * 100,  # As percentage number
                    "win_rate": m.win_rate * 100,  # As percentage number
                    "buy_hold_return": buy_hold_return * 100,  # As percentage number
                    "alpha": alpha * 100,  # Outperformance as percentage
                },
                "metrics": {
                    "total_return": f"{m.total_return:.2%}",
                    "annualized_return": f"{m.annualized_return:.2%}",
                    "sharpe_ratio": round(m.sharpe_ratio, 2),
                    "sortino_ratio": round(m.sortino_ratio, 2),
                    "max_drawdown": f"{m.max_drawdown:.2%}",
                    "total_trades": m.total_trades,
                    "win_rate": f"{m.win_rate:.1%}",
                    "profit_factor": round(m.profit_factor, 2),
                    "average_win": f"{m.average_win:.2%}",
                    "average_loss": f"{m.average_loss:.2%}",
                    "buy_hold_return": f"{buy_hold_return:.2%}",
                    "alpha": f"{alpha:.2%}",
                },
                # Full trades for chart markers
                "trades": [
                    {
                        "id": f"{strategy_name}_{i}",
                        "entry_time": t.entry_time.isoformat(),
                        "exit_time": t.exit_time.isoformat(),
                        "side": "long",  # TODO: support short
                        "entry_price": round(t.entry_price, 2),
                        "exit_price": round(t.exit_price, 2),
                        "quantity": t.quantity,
                        "pnl": round(t.pnl, 2),
                        "pnl_percent": round(t.pnl_percent * 100, 2),
                        "exit_reason": t.exit_reason,
                    }
                    for i, t in enumerate(result.trades)
                ],
                "recent_trades": [
                    {
                        "entry": t.entry_time.strftime("%Y-%m-%d"),
                        "exit": t.exit_time.strftime("%Y-%m-%d"),
                        "pnl": f"${t.pnl:,.2f}",
                        "return": f"{t.pnl_percent:.2%}",
                        "reason": t.exit_reason,
                    }
                    for t in result.trades[-5:]  # Last 5 trades for text display
                ],
            },
        )


class ListDataTool(Tool):
    """Tool for listing available market data."""

    @property
    def name(self) -> str:
        return "list_data"

    @property
    def description(self) -> str:
        return "List all available market data symbols and their date ranges."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        store = MarketDataStore()
        try:
            symbols = store.list_symbols()
            if not symbols:
                return ToolResult(
                    success=True,
                    data={
                        "symbols": [],
                        "message": "No data available. Use 'bonito ingest <SYMBOL>' to download data.",
                    },
                )

            data_info = []
            for symbol in symbols:
                date_range = store.get_date_range(symbol)
                bar_count = store.get_bar_count(symbol)
                if date_range:
                    data_info.append(
                        {
                            "symbol": symbol,
                            "start": date_range[0].strftime("%Y-%m-%d"),
                            "end": date_range[1].strftime("%Y-%m-%d"),
                            "bars": bar_count,
                        }
                    )

            return ToolResult(
                success=True,
                data={
                    "symbols": data_info,
                    "count": len(data_info),
                },
            )
        finally:
            store.close()


class ModifyStrategyTool(Tool):
    """Tool for modifying existing strategies."""

    def __init__(self, strategy_store: dict[str, StrategyConfig]):
        self._strategies = strategy_store

    @property
    def name(self) -> str:
        return "modify_strategy"

    @property
    def description(self) -> str:
        return """Modify an existing strategy's parameters.
Can change stop loss, take profit, position size, or indicator parameters."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_name": {
                    "type": "string",
                    "description": "Name of strategy to modify",
                },
                "stop_loss_pct": {
                    "type": "number",
                    "description": "New stop loss percentage (e.g., 0.03 for 3%)",
                },
                "take_profit_pct": {
                    "type": "number",
                    "description": "New take profit percentage",
                },
                "position_size_pct": {
                    "type": "number",
                    "description": "New position size percentage",
                },
            },
            "required": ["strategy_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        strategy_name = kwargs.get("strategy_name")
        strategy = self._strategies.get(strategy_name)

        if strategy is None:
            return ToolResult(
                success=False,
                error=f"Strategy '{strategy_name}' not found.",
            )

        updates = {}
        changes = []

        if "stop_loss_pct" in kwargs:
            updates["stop_loss"] = StopLossConfig(
                type=StopLossType.PERCENT,
                value=kwargs["stop_loss_pct"],
            )
            changes.append(f"stop_loss={kwargs['stop_loss_pct']:.1%}")

        if "take_profit_pct" in kwargs:
            updates["take_profit"] = TakeProfitConfig(
                type=TakeProfitType.PERCENT,
                value=kwargs["take_profit_pct"],
            )
            changes.append(f"take_profit={kwargs['take_profit_pct']:.1%}")

        if "position_size_pct" in kwargs:
            updates["position_size"] = PositionSizeConfig(
                type=PositionSizeType.PERCENT_EQUITY,
                value=kwargs["position_size_pct"],
            )
            changes.append(f"position_size={kwargs['position_size_pct']}%")

        if not updates:
            return ToolResult(
                success=False,
                error="No modifications specified.",
            )

        # Update strategy
        self._strategies[strategy_name] = strategy.model_copy(update=updates)

        return ToolResult(
            success=True,
            data={
                "strategy_name": strategy_name,
                "changes": changes,
                "message": f"Strategy '{strategy_name}' updated: {', '.join(changes)}",
            },
        )


class ListStrategiesTool(Tool):
    """Tool for listing created strategies."""

    def __init__(self, strategy_store: dict[str, StrategyConfig]):
        self._strategies = strategy_store

    @property
    def name(self) -> str:
        return "list_strategies"

    @property
    def description(self) -> str:
        return "List all strategies created in this session."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not self._strategies:
            return ToolResult(
                success=True,
                data={
                    "strategies": [],
                    "message": "No strategies created yet. Use create_strategy to create one.",
                },
            )

        strategies = []
        for name, strategy in self._strategies.items():
            strategies.append(
                {
                    "name": name,
                    "description": strategy.description,
                    "indicators": [i.name for i in strategy.indicators],
                    "has_stop_loss": strategy.stop_loss is not None,
                    "has_take_profit": strategy.take_profit is not None,
                }
            )

        return ToolResult(
            success=True,
            data={
                "strategies": strategies,
                "count": len(strategies),
            },
        )


class SaveStrategyTool(Tool):
    """Tool for saving strategies to disk."""

    def __init__(
        self,
        strategy_store: dict[str, StrategyConfig],
        result_store: dict[str, Any],
    ):
        self._strategies = strategy_store
        self._results = result_store

    @property
    def name(self) -> str:
        return "save_strategy"

    @property
    def description(self) -> str:
        return """Save a strategy to disk for later use.
Strategies are saved with their last backtest results for easy comparison."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_name": {
                    "type": "string",
                    "description": "Name of the strategy to save",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization (e.g., momentum, mean-reversion)",
                },
            },
            "required": ["strategy_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from bonito.storage.strategies import StrategyStore

        strategy_name = kwargs.get("strategy_name")
        tags = kwargs.get("tags", [])

        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            return ToolResult(
                success=False,
                error=f"Strategy '{strategy_name}' not found in session.",
            )

        store = StrategyStore()
        record = store.save(strategy, tags=tags)

        return ToolResult(
            success=True,
            data={
                "strategy_name": strategy_name,
                "id": record.id,
                "version": record.version,
                "tags": record.tags,
                "message": f"Strategy '{strategy_name}' saved to disk.",
            },
        )


class LoadStrategyTool(Tool):
    """Tool for loading saved strategies."""

    def __init__(self, strategy_store: dict[str, StrategyConfig]):
        self._strategies = strategy_store

    @property
    def name(self) -> str:
        return "load_strategy"

    @property
    def description(self) -> str:
        return """Load a previously saved strategy from disk into the current session.
Use list_saved_strategies first to see what's available."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_name": {
                    "type": "string",
                    "description": "Name of the strategy to load",
                },
            },
            "required": ["strategy_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from bonito.storage.strategies import StrategyStore

        strategy_name = kwargs.get("strategy_name")

        store = StrategyStore()
        record = store.load(strategy_name)

        if record is None:
            available = [s.name for s in store.list()]
            return ToolResult(
                success=False,
                error=f"Strategy '{strategy_name}' not found. Available: {available}",
            )

        # Add to session
        self._strategies[record.name] = record.config

        result_data: dict[str, Any] = {
            "strategy_name": record.name,
            "description": record.description,
            "version": record.version,
            "tags": record.tags,
            "indicators": [i.name for i in record.config.indicators],
            "message": f"Strategy '{record.name}' loaded into session.",
        }

        if record.last_backtest:
            result_data["last_performance"] = {
                "symbol": record.last_backtest.symbol,
                "period": record.last_backtest.period,
                "total_return": f"{record.last_backtest.total_return:.2%}",
                "sharpe_ratio": round(record.last_backtest.sharpe_ratio, 2),
                "max_drawdown": f"{record.last_backtest.max_drawdown:.2%}",
            }

        return ToolResult(success=True, data=result_data)


class ListSavedStrategiesTool(Tool):
    """Tool for listing strategies saved to disk."""

    @property
    def name(self) -> str:
        return "list_saved_strategies"

    @property
    def description(self) -> str:
        return "List all strategies that have been saved to disk, with their performance metrics."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from bonito.storage.strategies import StrategyStore

        tags = kwargs.get("tags")

        store = StrategyStore()
        strategies = store.list(tags=tags)

        if not strategies:
            return ToolResult(
                success=True,
                data={
                    "strategies": [],
                    "message": "No saved strategies found.",
                },
            )

        strategy_list = []
        for s in strategies:
            info: dict[str, Any] = {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "tags": s.tags,
                "updated": s.updated_at.strftime("%Y-%m-%d %H:%M"),
            }
            if s.last_backtest:
                info["performance"] = {
                    "return": f"{s.last_backtest.total_return:.2%}",
                    "sharpe": round(s.last_backtest.sharpe_ratio, 2),
                    "drawdown": f"{s.last_backtest.max_drawdown:.2%}",
                }
            strategy_list.append(info)

        return ToolResult(
            success=True,
            data={
                "strategies": strategy_list,
                "count": len(strategy_list),
            },
        )


class ChartControlTool(Tool):
    """Tool for controlling the chart display.

    This tool allows the agent to manipulate the chart:
    - Add/remove indicator overlays (SMA, EMA, RSI, etc.)
    - Add annotations (arrows, labels)
    - Highlight regions
    - Navigate to specific times
    - Clear overlays/annotations

    The tool returns chart "intents" that the frontend processes.
    """

    @property
    def name(self) -> str:
        return "chart_control"

    @property
    def description(self) -> str:
        return """Control the chart display to help explain analysis visually.

Actions:
- add_indicator: Add a technical indicator overlay
- remove_indicator: Remove an indicator overlay
- annotate: Add a visual annotation (arrow, label, marker)
- highlight: Highlight a time region on the chart
- navigate: Pan/zoom to a specific time or range
- clear: Clear annotations, indicators, or highlights

Use this to show users what you're explaining - point to candles, add indicators, highlight periods.

Examples:
- "Let me add RSI to show the oversold condition" → add_indicator
- "See this candle here" → annotate with arrow
- "The drawdown period from March to April" → highlight
- "Let's look at January" → navigate"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "add_indicator",
                        "remove_indicator",
                        "annotate",
                        "highlight",
                        "navigate",
                        "clear",
                    ],
                    "description": "The chart control action to perform",
                },
                # For add_indicator
                "indicator_type": {
                    "type": "string",
                    "description": "Indicator type: sma, ema, rsi, macd, bbands, vwap, atr",
                },
                "indicator_params": {
                    "type": "object",
                    "description": "Indicator parameters like {period: 14} or {fast: 12, slow: 26}",
                },
                # For remove_indicator
                "indicator_name": {
                    "type": "string",
                    "description": "Name of indicator to remove",
                },
                # For annotate
                "annotation_type": {
                    "type": "string",
                    "enum": ["arrow", "label", "marker"],
                    "description": "Type of annotation",
                },
                "annotation_text": {
                    "type": "string",
                    "description": "Text for label or marker",
                },
                "timestamp": {
                    "type": "string",
                    "description": "ISO date string (YYYY-MM-DD) for annotation position",
                },
                "price": {
                    "type": "number",
                    "description": "Price level for annotation (optional)",
                },
                # For highlight
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD) for highlight region",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD) for highlight region",
                },
                "highlight_color": {
                    "type": "string",
                    "description": "Color for highlight (e.g., 'red', 'green', '#22c55e')",
                    "default": "yellow",
                },
                # For clear
                "clear_type": {
                    "type": "string",
                    "enum": ["annotations", "indicators", "highlights", "all"],
                    "description": "What to clear from the chart",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action")

        try:
            if action == "add_indicator":
                ind_type = kwargs.get("indicator_type", "").lower()
                params = kwargs.get("indicator_params", {})

                if not ind_type:
                    return ToolResult(
                        success=False, error="indicator_type is required for add_indicator"
                    )

                # Build indicator name from type and params
                if ind_type in ("sma", "ema"):
                    period = params.get("period", 20)
                    name = f"{ind_type.upper()}({period})"
                elif ind_type == "rsi":
                    period = params.get("period", 14)
                    name = f"RSI({period})"
                elif ind_type == "macd":
                    fast = params.get("fastPeriod", 12)
                    slow = params.get("slowPeriod", 26)
                    signal = params.get("signalPeriod", 9)
                    name = f"MACD({fast},{slow},{signal})"
                    # Ensure params include MACD-specific fields for frontend
                    params = {"fastPeriod": fast, "slowPeriod": slow, "signalPeriod": signal}
                elif ind_type == "bbands":
                    period = params.get("period", 20)
                    name = f"BB({period})"
                elif ind_type == "vwap":
                    name = "VWAP"
                elif ind_type == "atr":
                    period = params.get("period", 14)
                    name = f"ATR({period})"
                else:
                    name = ind_type.upper()

                return ToolResult(
                    success=True,
                    data={
                        "intent": {
                            "type": "overlay",
                            "indicator": {
                                "type": ind_type,
                                "name": name,
                                "params": params,
                                "visible": True,
                            },
                        },
                        "message": f"Added {name} indicator to chart",
                    },
                )

            elif action == "remove_indicator":
                name = kwargs.get("indicator_name")
                if not name:
                    return ToolResult(
                        success=False, error="indicator_name is required for remove_indicator"
                    )

                return ToolResult(
                    success=True,
                    data={
                        "intent": {
                            "type": "clear",
                            "clearType": "indicators",
                            "indicatorName": name,
                        },
                        "message": f"Removed {name} from chart",
                    },
                )

            elif action == "annotate":
                ann_type = kwargs.get("annotation_type", "marker")
                text = kwargs.get("annotation_text", "")
                timestamp_str = kwargs.get("timestamp")

                if not timestamp_str:
                    return ToolResult(success=False, error="timestamp is required for annotate")

                # Convert date string to timestamp
                from datetime import datetime

                dt = datetime.strptime(timestamp_str, "%Y-%m-%d")
                timestamp = int(dt.timestamp())

                # Map annotation type to icon
                icon_map = {
                    "arrow": "signal",
                    "label": "info",
                    "marker": "signal",
                }

                return ToolResult(
                    success=True,
                    data={
                        "intent": {
                            "type": "annotate",
                            "annotation": {
                                "type": "marker" if ann_type == "arrow" else ann_type,
                                "timestamp": timestamp,
                                "text": text,
                                "icon": icon_map.get(ann_type, "signal"),
                                "price": kwargs.get("price"),
                            },
                        },
                        "message": f"Added {ann_type} annotation at {timestamp_str}",
                    },
                )

            elif action == "highlight":
                start_str = kwargs.get("start_date")
                end_str = kwargs.get("end_date")
                color = kwargs.get("highlight_color", "rgba(255, 193, 7, 0.2)")

                if not start_str or not end_str:
                    return ToolResult(
                        success=False,
                        error="start_date and end_date are required for highlight",
                    )

                from datetime import datetime

                start_dt = datetime.strptime(start_str, "%Y-%m-%d")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d")

                # Convert named colors to rgba
                color_map = {
                    "red": "rgba(239, 68, 68, 0.2)",
                    "green": "rgba(34, 197, 94, 0.2)",
                    "yellow": "rgba(255, 193, 7, 0.2)",
                    "blue": "rgba(59, 130, 246, 0.2)",
                }
                rgba_color = color_map.get(color.lower(), color)

                return ToolResult(
                    success=True,
                    data={
                        "intent": {
                            "type": "highlight",
                            "highlightRange": {
                                "start": int(start_dt.timestamp()),
                                "end": int(end_dt.timestamp()),
                                "color": rgba_color,
                            },
                        },
                        "message": f"Highlighted region from {start_str} to {end_str}",
                    },
                )

            elif action == "navigate":
                timestamp_str = kwargs.get("timestamp")
                start_str = kwargs.get("start_date")
                end_str = kwargs.get("end_date")

                from datetime import datetime

                if start_str and end_str:
                    # Navigate to range
                    start_ts = int(datetime.strptime(start_str, "%Y-%m-%d").timestamp())
                    end_ts = int(datetime.strptime(end_str, "%Y-%m-%d").timestamp())

                    return ToolResult(
                        success=True,
                        data={
                            "intent": {
                                "type": "navigate",
                                "range": {"start": start_ts, "end": end_ts},
                            },
                            "message": f"Navigated to {start_str} - {end_str}",
                        },
                    )
                elif timestamp_str:
                    # Navigate to timestamp
                    ts = int(datetime.strptime(timestamp_str, "%Y-%m-%d").timestamp())
                    return ToolResult(
                        success=True,
                        data={
                            "intent": {"type": "navigate", "timestamp": ts},
                            "message": f"Navigated to {timestamp_str}",
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        error="timestamp or start_date/end_date required for navigate",
                    )

            elif action == "clear":
                clear_type = kwargs.get("clear_type", "all")

                return ToolResult(
                    success=True,
                    data={
                        "intent": {"type": "clear", "clearType": clear_type},
                        "message": f"Cleared {clear_type} from chart",
                    },
                )

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=f"Chart control failed: {e!s}")


def get_agent_tools() -> tuple[ToolRegistry, dict[str, StrategyConfig], dict[str, Any]]:
    """Create and return agent tools with shared state.

    Returns:
        Tuple of (registry, strategy_store, result_store)
    """
    strategy_store: dict[str, StrategyConfig] = {}
    result_store: dict[str, Any] = {}

    registry = ToolRegistry()
    registry.register(CreateStrategyTool(strategy_store))
    registry.register(RunBacktestTool(strategy_store, result_store))
    registry.register(ModifyStrategyTool(strategy_store))
    registry.register(ListStrategiesTool(strategy_store))
    registry.register(ListDataTool())
    registry.register(SaveStrategyTool(strategy_store, result_store))
    registry.register(LoadStrategyTool(strategy_store))
    registry.register(ListSavedStrategiesTool())
    registry.register(ChartControlTool())  # NEW: Chart control for agent

    return registry, strategy_store, result_store
