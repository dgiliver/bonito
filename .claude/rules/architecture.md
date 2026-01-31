# Architecture Rules

## Strategy as Data
- Strategies MUST be JSON configs, NOT Python code
- Never allow arbitrary code execution from strategies
- All strategy fields must be typed with Pydantic

## Vectorized Computation
- Use NumPy arrays for all numerical operations
- NEVER use Python loops for array operations
- Pre-compute indicators before simulation loop

## State Management
- AnalysisContext is single source of truth for frontend
- Use reducers for complex state transitions
- Agent intents are commands, not direct mutations

## API Design
- All endpoints return JSON with consistent structure
- Errors return `{ "detail": "message" }`
- Use Pydantic for request/response validation

## File Organization
```
src/bonito/
├── agent/     # LLM integration (isolated)
├── backtest/  # Core domain (no LLM deps)
├── data/      # Storage (no business logic)
├── tools/     # Agent tools (bridge layer)
├── api/       # HTTP layer (thin)
```

## Dependency Direction
```
api → tools → agent
         ↘ backtest ← data
```
Never import:
- `agent` from `backtest`
- `tools` from `data`
- `api` from anywhere except entry points
