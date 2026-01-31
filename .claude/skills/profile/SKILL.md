---
name: profile
description: Profile code performance and identify bottlenecks. Use when backtest is slow.
allowed-tools: Bash, Read, Grep
---

# Profile Skill

Identify and measure performance bottlenecks.

## Usage

```bash
/profile backtest
/profile frontend
/profile api
```

## Backend Profiling

### CPU Time (cProfile)
```bash
python -m cProfile -s cumtime -c "
from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.data.store import DataStore
from datetime import datetime

config = BacktestConfig(
    start_date=datetime(2020, 1, 1),
    end_date=datetime(2024, 1, 1),
    initial_capital=100000,
)
engine = BacktestEngine(config)
store = DataStore()
data = store.get_bars('SPY', '1d', config.start_date, config.end_date)
# ... run backtest
" 2>&1 | head -30
```

### Memory Profiling
```bash
pip install memory_profiler
python -m memory_profiler src/bonito/backtest/engine.py
```

### Line-by-Line
```bash
pip install line_profiler
# Add @profile decorator to functions
kernprof -l -v src/bonito/backtest/engine.py
```

## Frontend Profiling

### Bundle Size
```bash
cd web && npm run build
npx source-map-explorer .next/static/chunks/*.js
```

### React Profiler
Open DevTools > Profiler > Record while interacting

### Lighthouse
```bash
npx lighthouse http://localhost:3000 --view
```

## Quick Benchmarks

### Backtest Speed
```bash
time pytest tests/test_backtest_engine.py -k "test_momentum" -v
```

### API Response Time
```bash
curl -w "\nTime: %{time_total}s\n" -X POST \
  http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"strategy": {...}}'
```

## Target Metrics

| Operation | Target | Current |
|-----------|--------|---------|
| 1-year backtest | <100ms | ? |
| Chart load | <200ms | ? |
| API response | <100ms | ? |

## Common Optimizations

### Vectorize Loops
```python
# SLOW
for i in range(len(data)):
    if close[i] > sma[i]:
        signal[i] = True

# FAST
signal = close > sma
```

### Pre-compute Indicators
```python
# Compute once, reuse
indicators = compute_indicators(data, config)
# Don't recompute in loop
```

### Batch Database Queries
```python
# SLOW: N queries
for symbol in symbols:
    data = store.get_bars(symbol, ...)

# FAST: 1 query
data = store.get_bars_batch(symbols, ...)
```
