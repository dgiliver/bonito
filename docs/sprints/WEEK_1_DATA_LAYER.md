# Week 1 Sprint: Data Layer

**Goal**: A working data pipeline where you can ingest market data and query it for backtesting.

**End State**: Running `quant ingest SPY AAPL --start 2020-01-01` downloads data and `quant data info SPY` shows what's available.

---

## Prerequisites (Do These First)

### P1: Environment Setup
**Time**: 15-30 minutes

```bash
# 1. Navigate to project
cd /Users/dgiliver/personal_projects/name_tbd

# 2. Create virtual environment (using uv is faster, but venv works)
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Verify installation
python -c "from quant_agent.data import MarketDataStore; print('✓ Import works')"

# 5. Set up pre-commit hooks (optional but recommended)
pre-commit install

# 6. Create your .env file
cp env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (not needed for Week 1, but good to have)
```

### P2: Verify Dependencies
```bash
# Check DuckDB works
python -c "import duckdb; print(f'DuckDB {duckdb.__version__}')"

# Check yfinance works
python -c "import yfinance as yf; print(f'yfinance {yf.__version__}')"

# Check pandas/numpy
python -c "import pandas as pd; import numpy as np; print(f'pandas {pd.__version__}, numpy {np.__version__}')"
```

---

## Tickets

### Ticket 1: Fix and Test MarketDataStore
**Priority**: P0 (Start Here)
**Estimate**: 2-3 hours
**File**: `src/quant_agent/data/store.py`

#### Description
The `MarketDataStore` class has been scaffolded but needs testing and bug fixes. Make it production-ready.

#### Tasks

- [ ] **1.1** Create a test file for the data store
- [ ] **1.2** Test database initialization (schema creation)
- [ ] **1.3** Test Yahoo Finance ingestion with a single symbol
- [ ] **1.4** Test data retrieval with `get_bars()`
- [ ] **1.5** Fix any bugs found during testing
- [ ] **1.6** Add error handling for network failures
- [ ] **1.7** Add logging

#### Implementation Steps

**Step 1**: Create the test file

```python
# tests/test_data_store.py
import pytest
from datetime import datetime
from pathlib import Path
import tempfile

from quant_agent.data.store import MarketDataStore


@pytest.fixture
def temp_store():
    """Create a temporary data store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        store = MarketDataStore(db_path)
        yield store
        store.close()


class TestMarketDataStore:
    def test_init_creates_schema(self, temp_store):
        """Test that initialization creates the bars table."""
        result = temp_store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bars'"
        ).fetchone()
        # DuckDB uses different catalog query
        tables = temp_store.conn.execute("SHOW TABLES").fetchall()
        assert any("bars" in str(t) for t in tables)

    def test_list_symbols_empty(self, temp_store):
        """Test listing symbols on empty database."""
        symbols = temp_store.list_symbols()
        assert symbols == []

    def test_ingest_and_retrieve(self, temp_store):
        """Test ingesting data from Yahoo and retrieving it."""
        # Ingest a small date range
        count = temp_store.ingest_from_yahoo(
            symbol="SPY",
            start="2024-01-01",
            end="2024-01-31",
            timeframe="1d"
        )

        assert count > 0, "Should have ingested some bars"

        # Retrieve the data
        data = temp_store.get_bars(
            symbol="SPY",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
            timeframe="1d"
        )

        assert data is not None
        assert len(data) > 0
        assert data.symbol == "SPY"

    def test_get_bars_no_data(self, temp_store):
        """Test retrieving data for non-existent symbol."""
        data = temp_store.get_bars(
            symbol="NOTREAL",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
        )
        assert data is None
```

**Step 2**: Run the test and fix issues

```bash
pytest tests/test_data_store.py -v
```

**Step 3**: Common issues to fix in `store.py`:

1. **Timezone handling** - yfinance returns timezone-aware datetimes, DuckDB expects naive
2. **Column name case sensitivity** - yfinance uses Title Case, we need lowercase
3. **Date vs Datetime column** - daily bars use "Date", intraday uses "Datetime"

#### Acceptance Criteria
- [ ] All tests pass
- [ ] Can ingest SPY data for 2020-2024
- [ ] Can retrieve data as `BarData` object
- [ ] Handles network errors gracefully
- [ ] Logs ingestion progress

---

### Ticket 2: Implement CLI Data Commands
**Priority**: P0
**Estimate**: 2-3 hours
**File**: `src/quant_agent/cli.py`
**Depends on**: Ticket 1

#### Description
Implement the CLI commands for data management:
- `quant ingest` - Download and store market data
- `quant data list` - Show available symbols
- `quant data info` - Show details about a symbol's data

#### Tasks

- [ ] **2.1** Implement `ingest` command fully
- [ ] **2.2** Add `data list` subcommand
- [ ] **2.3** Add `data info <symbol>` subcommand
- [ ] **2.4** Add progress indicators
- [ ] **2.5** Add error handling and user-friendly messages

#### Implementation

```python
# src/quant_agent/cli.py - Updated version

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from datetime import datetime

from quant_agent.data.store import MarketDataStore

app = typer.Typer(
    name="quant",
    help="AI-native algorithmic trading platform",
    no_args_is_help=True,
)
data_app = typer.Typer(help="Data management commands")
app.add_typer(data_app, name="data")

console = Console()


@app.command()
def ingest(
    symbols: list[str] = typer.Argument(..., help="Symbols to download (e.g., SPY AAPL QQQ)"),
    start: str = typer.Option("2020-01-01", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(None, help="End date (YYYY-MM-DD), defaults to today"),
    timeframe: str = typer.Option("1d", help="Timeframe: 1d, 1h, 15m, 5m, 1m"),
) -> None:
    """Download historical market data from Yahoo Finance."""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    store = MarketDataStore()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for symbol in symbols:
            task = progress.add_task(f"Downloading {symbol}...", total=None)
            try:
                count = store.ingest_from_yahoo(
                    symbol=symbol,
                    start=start,
                    end=end,
                    timeframe=timeframe,
                )
                progress.update(task, description=f"[green]✓[/green] {symbol}: {count} bars")
            except Exception as e:
                progress.update(task, description=f"[red]✗[/red] {symbol}: {str(e)}")

    store.close()
    console.print(f"\n[green]Data stored in[/green] {store.db_path}")


@data_app.command("list")
def data_list() -> None:
    """List all symbols with available data."""
    store = MarketDataStore()
    symbols = store.list_symbols()

    if not symbols:
        console.print("[yellow]No data found. Run 'quant ingest' first.[/yellow]")
        return

    table = Table(title="Available Symbols")
    table.add_column("Symbol", style="cyan")
    table.add_column("Start Date")
    table.add_column("End Date")
    table.add_column("Bars")

    for symbol in symbols:
        date_range = store.get_date_range(symbol)
        if date_range:
            # Get bar count
            count = store.conn.execute(
                "SELECT COUNT(*) FROM bars WHERE symbol = ?", [symbol]
            ).fetchone()[0]
            table.add_row(
                symbol,
                date_range[0].strftime("%Y-%m-%d"),
                date_range[1].strftime("%Y-%m-%d"),
                str(count),
            )

    store.close()
    console.print(table)


@data_app.command("info")
def data_info(
    symbol: str = typer.Argument(..., help="Symbol to get info for"),
) -> None:
    """Show detailed information about a symbol's data."""
    store = MarketDataStore()

    date_range = store.get_date_range(symbol)
    if not date_range:
        console.print(f"[red]No data found for {symbol}[/red]")
        return

    # Get statistics
    stats = store.conn.execute("""
        SELECT
            COUNT(*) as bars,
            MIN(close) as min_price,
            MAX(close) as max_price,
            AVG(volume) as avg_volume
        FROM bars
        WHERE symbol = ?
    """, [symbol]).fetchone()

    console.print(f"\n[bold cyan]{symbol}[/bold cyan] Data Summary")
    console.print(f"  Date Range: {date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}")
    console.print(f"  Total Bars: {stats[0]:,}")
    console.print(f"  Price Range: ${stats[1]:.2f} - ${stats[2]:.2f}")
    console.print(f"  Avg Volume: {stats[3]:,.0f}")

    store.close()
```

#### Acceptance Criteria
- [ ] `quant ingest SPY AAPL --start 2020-01-01` downloads data
- [ ] `quant data list` shows table of available symbols
- [ ] `quant data info SPY` shows summary statistics
- [ ] Progress indicators during download
- [ ] Clear error messages for invalid inputs

---

### Ticket 3: Add Data Validation and Quality Checks
**Priority**: P1
**Estimate**: 1-2 hours
**File**: `src/quant_agent/data/store.py`
**Depends on**: Ticket 1

#### Description
Add validation to ensure data quality:
- Detect and handle missing bars
- Validate OHLCV relationships (high >= low, etc.)
- Warn about suspicious data

#### Tasks

- [ ] **3.1** Add `validate_bars()` method to check data quality
- [ ] **3.2** Add option to fill missing bars (forward fill or skip)
- [ ] **3.3** Log warnings for suspicious data
- [ ] **3.4** Add `--validate` flag to ingest command

#### Implementation

```python
# Add to store.py

def validate_bars(self, symbol: str, timeframe: str = "1d") -> dict:
    """Validate data quality for a symbol.

    Returns:
        Dictionary with validation results
    """
    issues = []

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

    # Check for gaps (missing trading days for daily data)
    if timeframe == "1d":
        gap_check = self.conn.execute("""
            WITH dates AS (
                SELECT timestamp,
                       LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts
                FROM bars
                WHERE symbol = ? AND timeframe = ?
            )
            SELECT COUNT(*) FROM dates
            WHERE timestamp - prev_ts > INTERVAL 5 DAY
        """, [symbol, timeframe]).fetchone()[0]

        if gap_check > 0:
            issues.append(f"{gap_check} potential data gaps (>5 days)")

    return {
        "symbol": symbol,
        "valid": len(issues) == 0,
        "issues": issues,
    }
```

#### Acceptance Criteria
- [ ] `validate_bars()` detects common data issues
- [ ] Warnings logged for suspicious data
- [ ] No silent data corruption

---

### Ticket 4: Write Integration Test for Full Pipeline
**Priority**: P1
**Estimate**: 1-2 hours
**File**: `tests/test_data_integration.py`
**Depends on**: Tickets 1, 2

#### Description
Create an end-to-end test that validates the entire data pipeline works together.

#### Implementation

```python
# tests/test_data_integration.py
"""Integration tests for the data pipeline."""

import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from quant_agent.data.store import MarketDataStore
from quant_agent.data.models import BarData


class TestDataPipelineIntegration:
    """End-to-end tests for data ingestion and retrieval."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            store = MarketDataStore(db_path)
            yield store
            store.close()

    def test_full_pipeline_single_symbol(self, store):
        """Test complete pipeline: ingest → query → validate."""
        # 1. Ingest data
        count = store.ingest_from_yahoo(
            symbol="SPY",
            start="2023-01-01",
            end="2023-03-01",
            timeframe="1d"
        )
        assert count > 30, "Should have ~40 trading days"

        # 2. Verify it's in the database
        symbols = store.list_symbols()
        assert "SPY" in symbols

        # 3. Retrieve as BarData
        data = store.get_bars(
            symbol="SPY",
            start=datetime(2023, 1, 1),
            end=datetime(2023, 3, 1),
            timeframe="1d"
        )

        assert data is not None
        assert isinstance(data, BarData)
        assert len(data) > 30

        # 4. Validate data structure
        assert len(data.timestamps) == len(data.opens)
        assert len(data.timestamps) == len(data.closes)

        # 5. Validate data quality
        import numpy as np
        assert all(h >= l for h, l in zip(data.highs, data.lows)), "High should be >= Low"
        assert all(p > 0 for p in data.closes), "Prices should be positive"

        # 6. Test numpy array conversion
        close_arr = data.close
        assert isinstance(close_arr, np.ndarray)
        assert len(close_arr) == len(data)

    def test_multiple_symbols(self, store):
        """Test ingesting multiple symbols."""
        symbols = ["SPY", "QQQ"]

        for sym in symbols:
            store.ingest_from_yahoo(
                symbol=sym,
                start="2023-06-01",
                end="2023-06-30",
                timeframe="1d"
            )

        stored_symbols = store.list_symbols()
        assert set(symbols).issubset(set(stored_symbols))

    def test_data_persistence(self):
        """Test that data persists across store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "persist_test.duckdb"

            # Create store and add data
            store1 = MarketDataStore(db_path)
            store1.ingest_from_yahoo("AAPL", "2023-01-01", "2023-01-31", "1d")
            store1.close()

            # Create new store instance
            store2 = MarketDataStore(db_path)
            symbols = store2.list_symbols()
            assert "AAPL" in symbols

            data = store2.get_bars("AAPL", datetime(2023, 1, 1), datetime(2023, 1, 31))
            assert data is not None
            store2.close()


@pytest.mark.slow
class TestCLIIntegration:
    """Test CLI commands (requires network, marked slow)."""

    def test_ingest_command(self):
        """Test the ingest CLI command."""
        result = subprocess.run(
            ["python", "-m", "quant_agent.cli", "ingest", "SPY",
             "--start", "2023-12-01", "--end", "2023-12-15"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0 or "SPY" in result.stdout
```

#### Acceptance Criteria
- [ ] Full pipeline test passes
- [ ] Multiple symbol test passes
- [ ] Data persists correctly
- [ ] CLI integration test works

---

### Ticket 5: Add Logging Infrastructure
**Priority**: P2
**Estimate**: 1 hour
**Files**: `src/quant_agent/logging.py`, various

#### Description
Set up proper logging so you can debug issues and track what's happening.

#### Implementation

```python
# src/quant_agent/logging.py
"""Logging configuration for quant-agent."""

import logging
import sys
from pathlib import Path

from quant_agent.config import settings


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
) -> None:
    """Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
    """
    handlers: list[logging.Handler] = []

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
    )
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )
        )
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module."""
    return logging.getLogger(f"quant_agent.{name}")
```

Then add to `store.py`:

```python
from quant_agent.logging import get_logger

logger = get_logger("data.store")

# In ingest_from_yahoo:
logger.info(f"Ingesting {symbol} from {start} to {end}")
logger.debug(f"Downloaded {len(df)} bars")
```

---

## Daily Breakdown

### Day 1: Setup + Ticket 1 (Part 1)
- [ ] Complete Prerequisites P1 and P2
- [ ] Create `tests/test_data_store.py`
- [ ] Run tests, identify failing tests
- [ ] Start fixing bugs in `store.py`

### Day 2: Ticket 1 (Part 2) + Ticket 2
- [ ] Finish fixing `store.py` bugs
- [ ] Implement full `ingest` command
- [ ] Implement `data list` and `data info` commands
- [ ] Manual testing with real data

### Day 3: Tickets 3 + 4
- [ ] Add data validation
- [ ] Write integration tests
- [ ] Fix any issues found
- [ ] Test CLI end-to-end

### Day 4: Ticket 5 + Polish
- [ ] Add logging infrastructure
- [ ] Add logging to all data components
- [ ] Final testing
- [ ] Document any gotchas

### Day 5: Buffer / Review
- [ ] Code review your own work
- [ ] Ensure all tests pass
- [ ] Update documentation if needed
- [ ] Prep for Week 2 (backtest engine)

---

## Commands Cheat Sheet

```bash
# Run all tests
pytest tests/ -v

# Run only data tests
pytest tests/test_data_store.py -v

# Run with coverage
pytest tests/ --cov=quant_agent --cov-report=html

# Run linting
ruff check src/

# Type checking
mypy src/

# Manual testing
python -m quant_agent.cli ingest SPY --start 2020-01-01
python -m quant_agent.cli data list
python -m quant_agent.cli data info SPY

# Quick Python REPL test
python -c "
from quant_agent.data.store import MarketDataStore
store = MarketDataStore()
store.ingest_from_yahoo('SPY', '2020-01-01', '2024-01-01')
print(store.list_symbols())
"
```

---

## Definition of Done (Week 1)

- [ ] `pytest tests/test_data*.py` - All tests pass
- [ ] `quant ingest SPY AAPL QQQ --start 2020-01-01` - Downloads data without errors
- [ ] `quant data list` - Shows all ingested symbols
- [ ] `quant data info SPY` - Shows date range, bar count, price stats
- [ ] Data persists between sessions
- [ ] Logs show what's happening
- [ ] No linting errors (`ruff check src/`)
