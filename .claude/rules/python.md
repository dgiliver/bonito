# Python Code Rules

## Typing
- Use Python 3.12+ syntax: `list[str]`, `dict[str, int]`, not `List`, `Dict`
- Use `|` for unions: `str | None`, not `Optional[str]`
- Use Pydantic v2 models for all data structures that cross boundaries
- Annotate all function parameters and return types

## Pydantic
- Inherit from `BaseModel` for data classes
- Use `Field()` for validation, defaults, descriptions
- Use `model_validator` for complex validation
- Prefer `model_dump()` over `dict()` (Pydantic v2)

## Async
- All I/O operations must be async
- Use `httpx` for HTTP requests (not `requests`)
- Use `asyncio.gather()` for concurrent operations
- Never use blocking calls in async functions

## Error Handling
- Use specific exceptions, not bare `except:`
- Return `ToolResult(success=False, error=...)` from tools, don't raise
- Log errors with context: `logger.error("Failed to X", exc_info=True)`

## NumPy/Pandas
- Prefer NumPy arrays for vectorized operations
- Avoid iterating over DataFrames row-by-row
- Use `.values` to extract NumPy arrays from pandas Series
- Watch for NaN handling in indicator calculations

## Imports
- Use absolute imports: `from bonito.backtest.engine import BacktestEngine`
- Group: stdlib, third-party, local (ruff handles this)
- Avoid circular imports - use TYPE_CHECKING for type-only imports
