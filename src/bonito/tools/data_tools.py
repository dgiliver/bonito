"""Data access tools for the agent."""

from datetime import datetime
from typing import Any

from bonito.data.store import MarketDataStore
from bonito.tools.base import Tool, ToolResult


class GetBarsTool(Tool):
    """Get historical bar data."""

    @property
    def name(self) -> str:
        return "get_bars"

    @property
    def description(self) -> str:
        return """Get historical OHLCV bar data for a symbol.

Returns:
- Timestamps
- Open, High, Low, Close prices
- Volume

Use this to analyze price history or verify data availability."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., 'SPY', 'AAPL')",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "timeframe": {
                    "type": "string",
                    "description": "Bar timeframe: '1d', '1h', '15m', '5m', '1m'",
                    "default": "1d",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum bars to return (default: 100)",
                    "default": 100,
                },
            },
            "required": ["symbol", "start_date", "end_date"],
        }

    async def execute(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1d",
        limit: int = 100,
        **kwargs: Any,
    ) -> ToolResult:
        """Get bar data."""
        try:
            store = MarketDataStore()
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            data = store.get_bars(symbol, start, end, timeframe)

            if data is None:
                return ToolResult(
                    success=False,
                    error=f"No data found for {symbol}",
                )

            # Limit data for response size
            n = min(limit, len(data))

            return ToolResult(
                success=True,
                data={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "total_bars": len(data),
                    "returned_bars": n,
                    "date_range": {
                        "start": data.timestamps[0].isoformat(),
                        "end": data.timestamps[-1].isoformat(),
                    },
                    "summary": {
                        "min_close": round(min(data.closes), 2),
                        "max_close": round(max(data.closes), 2),
                        "avg_volume": round(sum(data.volumes) / len(data.volumes), 0),
                    },
                    "last_bars": [
                        {
                            "date": data.timestamps[-i].isoformat(),
                            "open": round(data.opens[-i], 2),
                            "high": round(data.highs[-i], 2),
                            "low": round(data.lows[-i], 2),
                            "close": round(data.closes[-i], 2),
                        }
                        for i in range(1, min(6, n + 1))
                    ],
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to get bars: {str(e)}",
            )


class ListSymbolsTool(Tool):
    """List available symbols in the data store."""

    @property
    def name(self) -> str:
        return "list_symbols"

    @property
    def description(self) -> str:
        return """List all symbols available in the data store.

Returns a list of ticker symbols that have historical data loaded.
Use this to see what symbols are available for backtesting."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """List symbols."""
        try:
            store = MarketDataStore()
            symbols = store.list_symbols()

            # Get date ranges for each symbol
            symbol_info = []
            for symbol in symbols:
                date_range = store.get_date_range(symbol)
                if date_range:
                    symbol_info.append(
                        {
                            "symbol": symbol,
                            "start": date_range[0].isoformat(),
                            "end": date_range[1].isoformat(),
                        }
                    )

            return ToolResult(
                success=True,
                data={
                    "symbols": symbols,
                    "count": len(symbols),
                    "details": symbol_info,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to list symbols: {str(e)}",
            )
