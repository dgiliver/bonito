"""Chart API routes for OHLCV data and indicators."""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from bonito.data.store import MarketDataStore

router = APIRouter(prefix="/chart", tags=["chart"])


class OHLCVBar(BaseModel):
    """Single OHLCV bar for charting."""

    time: int  # Unix timestamp in seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


class OHLCVResponse(BaseModel):
    """OHLCV data response."""

    symbol: str
    interval: str
    bars: list[OHLCVBar]
    source: str = "database"  # "database" or "live"
    message: str | None = None


class SymbolInfo(BaseModel):
    """Symbol information for search results."""

    symbol: str
    name: str | None = None
    type: str = "stock"


class SymbolSearchResponse(BaseModel):
    """Symbol search response."""

    results: list[SymbolInfo]


class SymbolIntervalsResponse(BaseModel):
    """Available intervals for a symbol."""

    symbol: str
    intervals: list[str]
    can_fetch_intraday: bool = True  # Can fetch from Yahoo on-demand


# Time range mappings
RANGE_DAYS = {
    "1D": 1,
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "YTD": None,
    "1Y": 365,
    "2Y": 730,
    "5Y": 1825,
    "ALL": None,
}

# Intraday intervals that can be fetched on-demand (Yahoo limit: ~60 days)
INTRADAY_INTERVALS = ["1m", "5m", "15m", "1h", "4h"]


def fetch_from_yahoo(symbol: str, interval: str, days: int = 60) -> list[OHLCVBar]:
    """Fetch data directly from Yahoo Finance."""
    import yfinance as yf

    end = datetime.now()
    start = end - timedelta(days=days)

    # Yahoo interval mapping
    yf_interval = interval
    if interval == "4h":
        yf_interval = "1h"  # Fetch 1h and we'll aggregate later (simplified for now)

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, interval=yf_interval)

    if df.empty:
        return []

    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else "Datetime"

    bars = []
    for _, row in df.iterrows():
        ts = row[date_col]
        if hasattr(ts, "timestamp"):
            time_val = int(ts.timestamp())
        else:
            time_val = int(datetime.fromisoformat(str(ts)).timestamp())

        bars.append(
            OHLCVBar(
                time=time_val,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
        )

    return bars


def refresh_stale_data(store: MarketDataStore, symbol: str, interval: str) -> int:
    """Check if data is stale and fetch missing bars. Returns number of new bars added."""
    import yfinance as yf

    # Get the latest timestamp in DB
    result = store.conn.execute(
        "SELECT MAX(timestamp) FROM bars WHERE symbol = ? AND timeframe = ?", [symbol, interval]
    ).fetchone()

    if not result or not result[0]:
        return 0  # No data to refresh

    last_timestamp = result[0]
    if isinstance(last_timestamp, str):
        last_date = datetime.fromisoformat(last_timestamp.replace("Z", ""))
    else:
        last_date = last_timestamp

    # Check if data is stale (more than 1 day old for daily, 1 hour for intraday)
    now = datetime.now()
    staleness_threshold = timedelta(days=1) if interval == "1d" else timedelta(hours=2)

    if now - last_date < staleness_threshold:
        return 0  # Data is fresh enough

    # Fetch new data from the last date
    start = last_date + timedelta(days=1) if interval == "1d" else last_date + timedelta(hours=1)

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=now, interval=interval)

    if df.empty:
        return 0

    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else "Datetime"

    # Convert timezone-aware datetime to naive UTC
    if df[date_col].dt.tz is not None:
        df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)

    df["symbol"] = symbol
    df["timeframe"] = interval

    # Rename columns to match our schema
    df = df.rename(
        columns={
            date_col: "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    # Select only needed columns
    df = df[["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]]
    df = df.dropna()

    if len(df) == 0:
        return 0

    # Insert new bars
    store.conn.execute("INSERT OR REPLACE INTO bars SELECT * FROM df")

    return len(df)


@router.get("/ohlcv", response_model=OHLCVResponse)
async def get_ohlcv(
    symbol: str = Query(..., description="Stock symbol"),
    interval: str = Query("1d", description="Bar interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    range: str = Query("1Y", description="Time range (1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y, ALL)"),
) -> OHLCVResponse:
    """Get OHLCV data for charting. Fetches on-demand for intraday if not in DB."""
    store = MarketDataStore()
    try:
        symbol = symbol.upper()

        # Calculate date range
        end_date = datetime.now()
        if range == "YTD":
            start_date = datetime(end_date.year, 1, 1)
        elif range == "ALL":
            start_date = datetime(2000, 1, 1)
        else:
            days = RANGE_DAYS.get(range, 365)
            start_date = end_date - timedelta(days=days) if days else datetime(2000, 1, 1)

        # Check if we have data in DB for this interval
        available_intervals = store.conn.execute(
            "SELECT DISTINCT timeframe FROM bars WHERE symbol = ?", [symbol]
        ).fetchall()
        available = [r[0] for r in available_intervals]

        # If interval is available in DB, use it
        if interval in available:
            # Auto-refresh stale data
            new_bars = refresh_stale_data(store, symbol, interval)
            refreshed = new_bars > 0

            data = store.get_bars(symbol, start_date, end_date, interval)
            if data is None or len(data.timestamps) == 0:
                raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

            bars = []
            for i, ts in enumerate(data.timestamps):
                if isinstance(ts, datetime):
                    bar_date = ts
                elif isinstance(ts, str):
                    try:
                        bar_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        bar_date = datetime.fromisoformat(ts.split("+")[0].replace("Z", ""))
                else:
                    bar_date = (
                        datetime.fromtimestamp(ts.timestamp()) if hasattr(ts, "timestamp") else ts
                    )

                bars.append(
                    OHLCVBar(
                        time=int(bar_date.timestamp()),
                        open=float(data.opens[i]),
                        high=float(data.highs[i]),
                        low=float(data.lows[i]),
                        close=float(data.closes[i]),
                        volume=float(data.volumes[i]),
                    )
                )

            return OHLCVResponse(
                symbol=symbol,
                interval=interval,
                bars=bars,
                source="database",
                message=f"Added {new_bars} new bars" if refreshed else None,
            )

        # If intraday interval, try to fetch from Yahoo on-demand
        if interval in INTRADAY_INTERVALS:
            # Limit range for intraday (Yahoo only has ~60 days, use 55 to be safe)
            max_days = 7 if interval == "1m" else 55

            bars = fetch_from_yahoo(symbol, interval, days=max_days)

            if not bars:
                raise HTTPException(
                    status_code=404,
                    detail=f"Could not fetch {interval} data for {symbol} from Yahoo Finance",
                )

            return OHLCVResponse(
                symbol=symbol,
                interval=interval,
                bars=bars,
                source="live",
                message=f"Live data from Yahoo Finance ({len(bars)} bars)",
            )

        # No data available
        raise HTTPException(
            status_code=404,
            detail=f"No {interval} data for {symbol}. Available in DB: {', '.join(available) if available else 'none'}",
        )

    finally:
        store.close()


@router.get("/symbols", response_model=SymbolSearchResponse)
async def list_symbols() -> SymbolSearchResponse:
    """List all available symbols."""
    store = MarketDataStore()
    try:
        symbols = store.list_symbols()
        results = [SymbolInfo(symbol=s) for s in symbols]
        return SymbolSearchResponse(results=results)
    finally:
        store.close()


@router.get("/search", response_model=SymbolSearchResponse)
async def search_symbols(
    q: str = Query(..., min_length=1, description="Search query"),
) -> SymbolSearchResponse:
    """Search for symbols by name or ticker."""
    store = MarketDataStore()
    try:
        symbols = store.list_symbols()
        query = q.upper()

        results = [SymbolInfo(symbol=s) for s in symbols if query in s.upper()]
        return SymbolSearchResponse(results=results)
    finally:
        store.close()


@router.get("/intervals/{symbol}", response_model=SymbolIntervalsResponse)
async def get_symbol_intervals(symbol: str) -> SymbolIntervalsResponse:
    """Get available intervals for a symbol."""
    store = MarketDataStore()
    try:
        symbol = symbol.upper()
        # All intervals are available - intraday can be fetched on-demand from Yahoo
        all_intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]

        return SymbolIntervalsResponse(
            symbol=symbol,
            intervals=all_intervals,
            can_fetch_intraday=True,
        )
    finally:
        store.close()
