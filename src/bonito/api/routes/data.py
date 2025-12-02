"""Data management endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from bonito.data.store import MarketDataStore

router = APIRouter()


class IngestRequest(BaseModel):
    """Request body for data ingestion."""

    symbols: list[str]
    start: str  # YYYY-MM-DD
    end: str | None = None
    timeframe: str = "1d"


@router.get("/symbols")
async def list_symbols() -> dict[str, Any]:
    """List all available symbols with their data ranges."""
    store = MarketDataStore()
    try:
        symbols = store.list_symbols()

        data = []
        for symbol in symbols:
            date_range = store.get_date_range(symbol)
            bar_count = store.get_bar_count(symbol)

            if date_range:
                data.append(
                    {
                        "symbol": symbol,
                        "start": date_range[0].strftime("%Y-%m-%d"),
                        "end": date_range[1].strftime("%Y-%m-%d"),
                        "bars": bar_count,
                    }
                )

        return {"symbols": data, "count": len(data)}
    finally:
        store.close()


@router.get("/symbols/{symbol}")
async def get_symbol_info(
    symbol: str,
    timeframe: str = "1d",
    validate: bool = False,
) -> dict[str, Any]:
    """Get detailed info about a symbol's data."""
    store = MarketDataStore()
    try:
        symbol = symbol.upper()
        date_range = store.get_date_range(symbol, timeframe)

        if not date_range:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {symbol} ({timeframe})",
            )

        bar_count = store.get_bar_count(symbol, timeframe)

        result: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": date_range[0].strftime("%Y-%m-%d"),
            "end": date_range[1].strftime("%Y-%m-%d"),
            "bars": bar_count,
        }

        if validate:
            validation = store.validate_bars(symbol, timeframe)
            result["validation"] = validation

        return result
    finally:
        store.close()


@router.get("/symbols/{symbol}/bars")
async def get_bars(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    timeframe: str = "1d",
    limit: int = 100,
) -> dict[str, Any]:
    """Get bar data for a symbol.

    Args:
        symbol: Stock symbol
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        timeframe: Bar timeframe
        limit: Max bars to return
    """
    store = MarketDataStore()
    try:
        symbol = symbol.upper()

        # Parse dates
        start_dt = datetime.strptime(start, "%Y-%m-%d") if start else datetime(2020, 1, 1)
        end_dt = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()

        data = store.get_bars(symbol, start_dt, end_dt, timeframe)

        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {symbol}",
            )

        # Limit results
        n = min(limit, len(data))

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": n,
            "bars": [
                {
                    "timestamp": data.timestamps[i].isoformat(),
                    "open": float(data.open[i]),
                    "high": float(data.high[i]),
                    "low": float(data.low[i]),
                    "close": float(data.close[i]),
                    "volume": int(data.volume[i]),
                }
                for i in range(n)
            ],
        }
    finally:
        store.close()


@router.post("/ingest")
async def ingest_data(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Start data ingestion (runs in background).

    Note: For large date ranges, this runs asynchronously.
    """
    end = request.end or datetime.now().strftime("%Y-%m-%d")

    # For now, run synchronously (could make async for large requests)
    store = MarketDataStore()
    results = []

    try:
        for symbol in request.symbols:
            try:
                count = store.ingest_from_yahoo(
                    symbol=symbol.upper(),
                    start=request.start,
                    end=end,
                    timeframe=request.timeframe,  # type: ignore
                )
                results.append(
                    {
                        "symbol": symbol.upper(),
                        "bars": count,
                        "status": "success",
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "symbol": symbol.upper(),
                        "bars": 0,
                        "status": "error",
                        "error": str(e),
                    }
                )

        total_bars = sum(r["bars"] for r in results)
        return {
            "results": results,
            "total_bars": total_bars,
            "timeframe": request.timeframe,
        }
    finally:
        store.close()


@router.delete("/symbols/{symbol}")
async def delete_symbol_data(
    symbol: str,
    timeframe: str | None = None,
) -> dict[str, Any]:
    """Delete data for a symbol."""
    store = MarketDataStore()
    try:
        symbol = symbol.upper()
        deleted = store.delete_symbol(symbol, timeframe)

        if deleted == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {symbol}",
            )

        return {
            "symbol": symbol,
            "timeframe": timeframe or "all",
            "deleted_bars": deleted,
        }
    finally:
        store.close()
