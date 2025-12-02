"""Data models for market data."""

from datetime import datetime
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field


class Bar(BaseModel):
    """Single OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    model_config = {"frozen": True}


class BarData(BaseModel):
    """Collection of OHLCV bars for efficient vectorized operations."""

    symbol: str
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1d"

    # Stored as lists for JSON serialization, convert to numpy for computation
    timestamps: list[datetime]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]

    def __len__(self) -> int:
        return len(self.timestamps)

    @property
    def open(self) -> np.ndarray:
        """Open prices as numpy array."""
        return np.array(self.opens)

    @property
    def high(self) -> np.ndarray:
        """High prices as numpy array."""
        return np.array(self.highs)

    @property
    def low(self) -> np.ndarray:
        """Low prices as numpy array."""
        return np.array(self.lows)

    @property
    def close(self) -> np.ndarray:
        """Close prices as numpy array."""
        return np.array(self.closes)

    @property
    def volume(self) -> np.ndarray:
        """Volume as numpy array."""
        return np.array(self.volumes)


class DataRequest(BaseModel):
    """Request for market data."""

    symbol: str = Field(..., description="Ticker symbol")
    start: datetime = Field(..., description="Start datetime")
    end: datetime = Field(..., description="End datetime")
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Field(
        default="1d", description="Bar timeframe"
    )
