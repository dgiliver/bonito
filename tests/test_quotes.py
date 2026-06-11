"""Tests for the yfinance quote fetcher (bonito.data.quotes)."""

import bonito.data.quotes as quotes_mod
from bonito.data.quotes import fetch_latest_quotes


class FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    @property
    def fast_info(self):
        if self.symbol == "BOOM":
            raise RuntimeError("no data")
        prices = {"AAA": 101.5, "bbb": 42.0, "ZERO": 0.0}
        return {"last_price": prices[self.symbol]}


def test_fetch_latest_quotes(monkeypatch):
    monkeypatch.setattr(quotes_mod.yf, "Ticker", FakeTicker)

    quotes = fetch_latest_quotes(["AAA", "bbb", "ZERO", "BOOM"])

    # Failures and non-positive prices omitted; keys uppercased.
    assert quotes == {"AAA": 101.5, "BBB": 42.0}
