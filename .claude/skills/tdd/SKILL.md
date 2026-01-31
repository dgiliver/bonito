---
name: tdd
description: Implement a feature using Test-Driven Development. Write tests first, then code.
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# TDD Skill

Implement features with Test-Driven Development methodology.

## Usage

```bash
/tdd "implement short selling P&L calculation"
```

## The TDD Cycle

### 1. RED - Write Failing Test
```python
def test_short_profit_when_price_falls():
    """Short position should profit when price falls."""
    prices = [100, 100, 100, 95, 90]  # Price falls
    data = create_test_data(prices)
    strategy = create_short_strategy()

    result = engine.run(strategy, data)

    assert result.trades[0].pnl > 0  # Should profit
```

Run: `pytest tests/test_short_selling.py -v` → FAILS

### 2. GREEN - Minimal Implementation
Only write code to make the test pass:
```python
# In engine.py
if position["side"] == "short":
    pnl = (entry_price - exit_price) * quantity
else:
    pnl = (exit_price - entry_price) * quantity
```

Run: `pytest tests/test_short_selling.py -v` → PASSES

### 3. REFACTOR - Clean Up
- Remove duplication
- Improve naming
- Extract helpers
- Keep tests green

## Test File Structure

```
tests/
├── conftest.py           # Shared fixtures
├── test_backtest_engine.py
├── test_indicators.py
├── test_short_selling.py # New feature tests
└── test_api.py
```

## Fixture Example

```python
# conftest.py
@pytest.fixture
def backtest_config():
    return BacktestConfig(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 12, 31),
        initial_capital=10000,
        commission=0,
        slippage=0,
    )

@pytest.fixture
def engine(backtest_config):
    return BacktestEngine(backtest_config)
```

## Assertion Patterns

```python
# Exact equality
assert result.value == expected

# Approximate (for floats)
assert result.value == pytest.approx(expected, rel=0.01)

# Contains
assert "error" in result.message

# Exception expected
with pytest.raises(ValidationError):
    invalid_function()

# Multiple conditions
assert all(t.pnl > 0 for t in winning_trades)
```

## Running Tests

```bash
# All tests
make test

# Specific file
pytest tests/test_short_selling.py -v

# Specific test
pytest tests/test_short_selling.py::test_short_profit -v

# With coverage
pytest --cov=bonito tests/

# Stop on first failure
pytest -x tests/
```
