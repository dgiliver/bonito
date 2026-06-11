"""Lightweight real-time quote fetch via yfinance.

Used by the intraday stop sweep (`bonito live sweep`) where only the
latest trade price is needed — full bar ingestion stays in MarketDataStore.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_latest_quotes(symbols: list[str]) -> dict[str, float]:
    """Latest trade price per symbol.

    Symbols whose quote fails or comes back non-positive are OMITTED, never
    guessed — downstream stop checks hold those positions and warn.
    """
    quotes: dict[str, float] = {}
    for symbol in symbols:
        try:
            price = float(yf.Ticker(symbol).fast_info["last_price"])
        except Exception:
            logger.warning(f"No quote for {symbol}", exc_info=True)
            continue
        if price > 0:
            quotes[symbol.upper()] = price
        else:
            logger.warning(f"Discarding non-positive quote for {symbol}: {price}")
    return quotes
