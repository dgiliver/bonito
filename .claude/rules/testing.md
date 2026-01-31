# Testing Rules

## Python (pytest)
- Test files: `tests/test_*.py`
- Use descriptive test names: `test_backtest_calculates_sharpe_ratio_correctly`
- Mark slow tests with `@pytest.mark.slow`
- Use fixtures for common setup (conftest.py)
- Test edge cases: empty data, invalid inputs, boundary conditions

## Test Structure
```python
def test_something():
    # Arrange
    data = create_test_data()

    # Act
    result = function_under_test(data)

    # Assert
    assert result.value == expected
```

## Frontend (Vitest)
- Test files: `*.test.ts` or `*.test.tsx`
- Use React Testing Library for component tests
- Test user interactions, not implementation details
- Mock API calls with MSW or vi.mock

## What to Test
- Indicator calculations (exact values matter)
- Strategy validation (DSL edge cases)
- Backtest P&L calculations (critical for correctness)
- Tool execution (success and error paths)
- Component rendering (key UI states)

## What NOT to Test
- Third-party library internals
- Simple getters/setters
- CSS styling (unless critical)
- Private implementation details
