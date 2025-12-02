"""Market data storage using DuckDB."""

from datetime import datetime
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
import yfinance as yf

from quant_agent.config import settings
from quant_agent.data.models import BarData
from quant_agent.logging import get_logger

logger = get_logger("data.store")


class MarketDataStore:
    """DuckDB-backed market data store.
    
    Provides efficient storage and retrieval of OHLCV bar data.
    Uses DuckDB for fast analytical queries.
    
    Example:
        >>> store = MarketDataStore()
        >>> store.ingest_from_yahoo("SPY", "2020-01-01", "2024-01-01")
        >>> data = store.get_bars("SPY", datetime(2020, 1, 1), datetime(2024, 1, 1))
        >>> print(len(data))
        1000
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the data store.
        
        Args:
            db_path: Path to DuckDB database file. Defaults to data/market_data.duckdb
        """
        if db_path is None:
            db_path = settings.data_dir / "market_data.duckdb"
        
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        
        logger.debug(f"Connecting to database at {db_path}")
        self.conn = duckdb.connect(str(db_path))
        self._init_schema()
    
    def _init_schema(self) -> None:
        """Initialize database schema."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bars (
                symbol VARCHAR NOT NULL,
                timeframe VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open DOUBLE NOT NULL,
                high DOUBLE NOT NULL,
                low DOUBLE NOT NULL,
                close DOUBLE NOT NULL,
                volume DOUBLE NOT NULL,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)
        logger.debug("Database schema initialized")
    
    def ingest_from_yahoo(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1d",
    ) -> int:
        """Download and store data from Yahoo Finance.
        
        Args:
            symbol: Ticker symbol (e.g., "SPY", "AAPL")
            start: Start date (string "YYYY-MM-DD" or datetime)
            end: End date (string "YYYY-MM-DD" or datetime)
            timeframe: Bar timeframe (1d, 1h, etc.)
            
        Returns:
            Number of bars ingested
            
        Raises:
            ValueError: If no data is returned from Yahoo Finance
        """
        logger.info(f"Ingesting {symbol} from {start} to {end} ({timeframe})")
        
        # Map our timeframe to yfinance interval
        interval_map = {
            "1m": "1m",
            "5m": "5m", 
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        interval = interval_map.get(timeframe, "1d")
        
        # Download from Yahoo Finance
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval)
        
        if df.empty:
            logger.warning(f"No data returned from Yahoo Finance for {symbol}")
            return 0
        
        logger.debug(f"Downloaded {len(df)} bars from Yahoo Finance")
        
        # Prepare data for insertion
        df = df.reset_index()
        
        # Handle different column names from yfinance
        # Daily data has "Date" column, intraday has "Datetime"
        date_col = "Date" if "Date" in df.columns else "Datetime"
        
        # Convert timezone-aware datetime to naive UTC
        if df[date_col].dt.tz is not None:
            df[date_col] = df[date_col].dt.tz_convert("UTC").dt.tz_localize(None)
        
        df["symbol"] = symbol
        df["timeframe"] = timeframe
        
        # Rename columns to match our schema
        df = df.rename(columns={
            date_col: "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        
        # Select only needed columns in correct order
        df = df[["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]]
        
        # Remove any rows with NaN values
        initial_count = len(df)
        df = df.dropna()
        if len(df) < initial_count:
            logger.debug(f"Dropped {initial_count - len(df)} rows with NaN values")
        
        # Upsert data (INSERT OR REPLACE)
        self.conn.execute("""
            INSERT OR REPLACE INTO bars 
            SELECT * FROM df
        """)
        
        logger.info(f"Ingested {len(df)} bars for {symbol}")
        return len(df)
    
    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1d",
    ) -> BarData | None:
        """Retrieve bars from the store.
        
        Args:
            symbol: Ticker symbol
            start: Start datetime
            end: End datetime
            timeframe: Bar timeframe
            
        Returns:
            BarData object or None if no data found
        """
        logger.debug(f"Querying bars for {symbol} from {start} to {end}")
        
        result = self.conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM bars
            WHERE symbol = ?
              AND timeframe = ?
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp
        """, [symbol, timeframe, start, end]).fetchdf()
        
        if result.empty:
            logger.debug(f"No bars found for {symbol}")
            return None
        
        logger.debug(f"Retrieved {len(result)} bars for {symbol}")
        
        return BarData(
            symbol=symbol,
            timeframe=timeframe,  # type: ignore
            timestamps=result["timestamp"].tolist(),
            opens=result["open"].tolist(),
            highs=result["high"].tolist(),
            lows=result["low"].tolist(),
            closes=result["close"].tolist(),
            volumes=result["volume"].tolist(),
        )
    
    def list_symbols(self) -> list[str]:
        """List all symbols in the store.
        
        Returns:
            List of symbol strings, sorted alphabetically
        """
        result = self.conn.execute("""
            SELECT DISTINCT symbol FROM bars ORDER BY symbol
        """).fetchall()
        return [row[0] for row in result]
    
    def get_date_range(
        self, 
        symbol: str, 
        timeframe: str = "1d"
    ) -> tuple[datetime, datetime] | None:
        """Get the date range available for a symbol.
        
        Args:
            symbol: Ticker symbol
            timeframe: Bar timeframe
            
        Returns:
            Tuple of (start_date, end_date) or None if no data
        """
        result = self.conn.execute("""
            SELECT MIN(timestamp), MAX(timestamp)
            FROM bars
            WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        
        if result is None or result[0] is None:
            return None
        
        return result[0], result[1]
    
    def get_bar_count(self, symbol: str, timeframe: str = "1d") -> int:
        """Get the number of bars for a symbol.
        
        Args:
            symbol: Ticker symbol
            timeframe: Bar timeframe
            
        Returns:
            Number of bars stored
        """
        result = self.conn.execute("""
            SELECT COUNT(*) FROM bars
            WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        
        return result[0] if result else 0
    
    def validate_bars(
        self, 
        symbol: str, 
        timeframe: str = "1d"
    ) -> dict:
        """Validate data quality for a symbol.
        
        Checks:
        - OHLC relationships (high >= low, high >= open/close, etc.)
        - Zero/negative prices
        - Data gaps (for daily data)
        
        Args:
            symbol: Ticker symbol
            timeframe: Bar timeframe
            
        Returns:
            Dictionary with validation results
        """
        issues: list[str] = []
        
        # Check OHLC relationships
        invalid_ohlc = self.conn.execute("""
            SELECT COUNT(*) FROM bars 
            WHERE symbol = ? AND timeframe = ?
            AND (high < low OR high < open OR high < close 
                 OR low > open OR low > close)
        """, [symbol, timeframe]).fetchone()[0]
        
        if invalid_ohlc > 0:
            issues.append(f"{invalid_ohlc} bars with invalid OHLC relationships")
        
        # Check for zero/negative prices
        invalid_prices = self.conn.execute("""
            SELECT COUNT(*) FROM bars
            WHERE symbol = ? AND timeframe = ?
            AND (open <= 0 OR high <= 0 OR low <= 0 OR close <= 0)
        """, [symbol, timeframe]).fetchone()[0]
        
        if invalid_prices > 0:
            issues.append(f"{invalid_prices} bars with zero/negative prices")
        
        # Check for large gaps in daily data
        if timeframe == "1d":
            # Find gaps larger than 5 calendar days (accounting for weekends)
            gap_check = self.conn.execute("""
                WITH dates AS (
                    SELECT timestamp, 
                           LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts
                    FROM bars
                    WHERE symbol = ? AND timeframe = ?
                )
                SELECT COUNT(*) FROM dates
                WHERE prev_ts IS NOT NULL 
                AND timestamp - prev_ts > INTERVAL 5 DAY
            """, [symbol, timeframe]).fetchone()[0]
            
            if gap_check > 0:
                issues.append(f"{gap_check} potential data gaps (>5 calendar days)")
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "valid": len(issues) == 0,
            "issues": issues,
            "bar_count": self.get_bar_count(symbol, timeframe),
        }
    
    def delete_symbol(self, symbol: str, timeframe: str | None = None) -> int:
        """Delete data for a symbol.
        
        Args:
            symbol: Ticker symbol
            timeframe: Optional timeframe filter. If None, deletes all timeframes.
            
        Returns:
            Number of bars deleted
        """
        if timeframe:
            result = self.conn.execute("""
                DELETE FROM bars WHERE symbol = ? AND timeframe = ?
            """, [symbol, timeframe])
        else:
            result = self.conn.execute("""
                DELETE FROM bars WHERE symbol = ?
            """, [symbol])
        
        # Get rowcount
        deleted = result.fetchone()
        count = deleted[0] if deleted else 0
        logger.info(f"Deleted {count} bars for {symbol}")
        return count
    
    def close(self) -> None:
        """Close the database connection."""
        logger.debug("Closing database connection")
        self.conn.close()
