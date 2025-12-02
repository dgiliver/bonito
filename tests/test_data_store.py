"""Tests for MarketDataStore."""

import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from quant_agent.data.models import BarData
from quant_agent.data.store import MarketDataStore


@pytest.fixture
def temp_store():
    """Create a temporary data store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        store = MarketDataStore(db_path)
        yield store
        store.close()


class TestMarketDataStoreInit:
    """Tests for store initialization."""
    
    def test_creates_database_file(self):
        """Test that initialization creates the database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            store = MarketDataStore(db_path)
            
            assert db_path.exists()
            store.close()
    
    def test_creates_bars_table(self, temp_store):
        """Test that initialization creates the bars table."""
        tables = temp_store.conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "bars" in table_names
    
    def test_creates_parent_directories(self):
        """Test that missing parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nested" / "dirs" / "test.duckdb"
            store = MarketDataStore(db_path)
            
            assert db_path.parent.exists()
            store.close()


class TestListSymbols:
    """Tests for list_symbols method."""
    
    def test_empty_database(self, temp_store):
        """Test listing symbols on empty database."""
        symbols = temp_store.list_symbols()
        assert symbols == []
    
    def test_returns_sorted_symbols(self, temp_store):
        """Test that symbols are returned sorted."""
        # Insert some test data directly
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('ZZZ', '1d', '2024-01-01', 100, 101, 99, 100, 1000),
            ('AAA', '1d', '2024-01-01', 100, 101, 99, 100, 1000),
            ('MMM', '1d', '2024-01-01', 100, 101, 99, 100, 1000)
        """)
        
        symbols = temp_store.list_symbols()
        assert symbols == ["AAA", "MMM", "ZZZ"]


class TestGetBars:
    """Tests for get_bars method."""
    
    def test_no_data_returns_none(self, temp_store):
        """Test that get_bars returns None for missing symbol."""
        result = temp_store.get_bars(
            symbol="NOTREAL",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
        )
        assert result is None
    
    def test_returns_bar_data(self, temp_store):
        """Test that get_bars returns BarData object."""
        # Insert test data
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-02', 100, 102, 99, 101, 1000000),
            ('TEST', '1d', '2024-01-03', 101, 103, 100, 102, 1100000),
            ('TEST', '1d', '2024-01-04', 102, 104, 101, 103, 1200000)
        """)
        
        result = temp_store.get_bars(
            symbol="TEST",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
        )
        
        assert result is not None
        assert isinstance(result, BarData)
        assert result.symbol == "TEST"
        assert len(result) == 3
    
    def test_filters_by_date_range(self, temp_store):
        """Test that get_bars respects date range."""
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-01', 100, 101, 99, 100, 1000),
            ('TEST', '1d', '2024-01-15', 100, 101, 99, 100, 1000),
            ('TEST', '1d', '2024-01-31', 100, 101, 99, 100, 1000)
        """)
        
        result = temp_store.get_bars(
            symbol="TEST",
            start=datetime(2024, 1, 10),
            end=datetime(2024, 1, 20),
        )
        
        assert result is not None
        assert len(result) == 1
    
    def test_bar_data_numpy_conversion(self, temp_store):
        """Test that BarData provides numpy arrays."""
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-02', 100, 102, 99, 101, 1000000)
        """)
        
        result = temp_store.get_bars(
            symbol="TEST",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
        )
        
        assert isinstance(result.close, np.ndarray)
        assert isinstance(result.open, np.ndarray)
        assert isinstance(result.high, np.ndarray)
        assert isinstance(result.low, np.ndarray)
        assert isinstance(result.volume, np.ndarray)


class TestGetDateRange:
    """Tests for get_date_range method."""
    
    def test_no_data_returns_none(self, temp_store):
        """Test that get_date_range returns None for missing symbol."""
        result = temp_store.get_date_range("NOTREAL")
        assert result is None
    
    def test_returns_correct_range(self, temp_store):
        """Test that get_date_range returns correct min/max dates."""
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-15', 100, 101, 99, 100, 1000),
            ('TEST', '1d', '2024-01-01', 100, 101, 99, 100, 1000),
            ('TEST', '1d', '2024-01-31', 100, 101, 99, 100, 1000)
        """)
        
        result = temp_store.get_date_range("TEST")
        
        assert result is not None
        start, end = result
        assert start.day == 1
        assert end.day == 31


class TestValidateBars:
    """Tests for validate_bars method."""
    
    def test_valid_data(self, temp_store):
        """Test validation passes for valid data."""
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-02', 100, 102, 99, 101, 1000000)
        """)
        
        result = temp_store.validate_bars("TEST")
        
        assert result["valid"] is True
        assert result["issues"] == []
    
    def test_detects_invalid_ohlc(self, temp_store):
        """Test that invalid OHLC relationships are detected."""
        # High < Low is invalid
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-02', 100, 98, 102, 101, 1000000)
        """)
        
        result = temp_store.validate_bars("TEST")
        
        assert result["valid"] is False
        assert any("OHLC" in issue for issue in result["issues"])
    
    def test_detects_zero_prices(self, temp_store):
        """Test that zero prices are detected."""
        temp_store.conn.execute("""
            INSERT INTO bars VALUES 
            ('TEST', '1d', '2024-01-02', 0, 102, 99, 101, 1000000)
        """)
        
        result = temp_store.validate_bars("TEST")
        
        assert result["valid"] is False
        assert any("zero" in issue.lower() or "negative" in issue.lower() for issue in result["issues"])


@pytest.mark.slow
class TestYahooIngestion:
    """Integration tests for Yahoo Finance ingestion.
    
    These tests require network access and are marked slow.
    Run with: pytest -m slow
    """
    
    def test_ingest_spy_daily(self, temp_store):
        """Test ingesting SPY daily data."""
        count = temp_store.ingest_from_yahoo(
            symbol="SPY",
            start="2024-01-01",
            end="2024-01-31",
            timeframe="1d",
        )
        
        # Should have ~20 trading days in January
        assert count > 15
        assert count < 25
        
        # Verify we can retrieve it
        symbols = temp_store.list_symbols()
        assert "SPY" in symbols
    
    def test_ingest_multiple_symbols(self, temp_store):
        """Test ingesting multiple symbols."""
        for symbol in ["SPY", "QQQ"]:
            temp_store.ingest_from_yahoo(
                symbol=symbol,
                start="2024-06-01",
                end="2024-06-30",
                timeframe="1d",
            )
        
        symbols = temp_store.list_symbols()
        assert "SPY" in symbols
        assert "QQQ" in symbols
    
    def test_ingest_preserves_ohlc_relationships(self, temp_store):
        """Test that ingested data has valid OHLC relationships."""
        temp_store.ingest_from_yahoo(
            symbol="AAPL",
            start="2024-01-01",
            end="2024-01-31",
            timeframe="1d",
        )
        
        result = temp_store.validate_bars("AAPL")
        assert result["valid"] is True, f"Validation issues: {result['issues']}"


class TestDataPersistence:
    """Tests for data persistence across sessions."""
    
    def test_data_persists(self):
        """Test that data persists when store is closed and reopened."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "persist.duckdb"
            
            # Create store and add data
            store1 = MarketDataStore(db_path)
            store1.conn.execute("""
                INSERT INTO bars VALUES 
                ('PERSIST', '1d', '2024-01-02', 100, 102, 99, 101, 1000000)
            """)
            store1.close()
            
            # Reopen and verify
            store2 = MarketDataStore(db_path)
            symbols = store2.list_symbols()
            assert "PERSIST" in symbols
            
            data = store2.get_bars("PERSIST", datetime(2024, 1, 1), datetime(2024, 1, 31))
            assert data is not None
            assert len(data) == 1
            store2.close()

