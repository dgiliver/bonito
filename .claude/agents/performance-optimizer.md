---
name: performance-optimizer
description: Profile and optimize code performance. Identifies bottlenecks, suggests vectorization, and measures improvements. Use when backtest is slow or UI lags.
tools: Bash, Read, Grep, Glob, Edit
model: sonnet
---

# Performance Optimizer Agent

Analyze and optimize performance bottlenecks in the Bonito trading platform.

## Profiling Tools

### Python Backend
```bash
# Profile backtest execution
python -m cProfile -s cumtime -m pytest tests/test_backtest_engine.py -k "test_momentum" 2>&1 | head -50

# Memory profiling
pip install memory_profiler
python -m memory_profiler src/bonito/backtest/engine.py

# Line profiler for hot functions
pip install line_profiler
kernprof -l -v src/bonito/backtest/engine.py
```

### Frontend
```bash
# Bundle analysis
cd web && npm run build && npx source-map-explorer .next/static/chunks/*.js

# Lighthouse audit
npx lighthouse http://localhost:3000 --output=json --output-path=lighthouse.json
```

## Common Bottlenecks in Bonito

### 1. Backtest Engine (_simulate loop)
**Problem**: Bar-by-bar Python loop is slow
**Solution**: Vectorize with NumPy where possible

```python
# SLOW: Python loop
for i in range(len(data)):
    if closes[i] > sma[i]:
        signals[i] = True

# FAST: NumPy vectorized
signals = closes > sma
```

### 2. Indicator Computation
**Problem**: Redundant calculations
**Solution**: Cache indicator results

```python
# Use functools.lru_cache for pure functions
@lru_cache(maxsize=128)
def compute_sma(data_hash: str, period: int) -> np.ndarray:
    ...
```

### 3. Chart Rendering
**Problem**: Too many data points cause lag
**Solution**: Downsample for display

```typescript
// Downsample large datasets
const downsample = (data: OHLCVData[], maxPoints: number) => {
  if (data.length <= maxPoints) return data;
  const factor = Math.ceil(data.length / maxPoints);
  return data.filter((_, i) => i % factor === 0);
};
```

### 4. Trade Marker Creation
**Problem**: O(n²) time complexity
**Solution**: Use binary search for time matching

```typescript
// Build time index once
const timeIndex = new Map(candleData.map((c, i) => [c.time, i]));

// O(1) lookup instead of O(n) search
const candleIdx = timeIndex.get(tradeTime);
```

### 5. Virtualized List Rendering
**Problem**: Rendering all rows at once
**Solution**: Already using @tanstack/react-virtual ✓

## Optimization Checklist

- [ ] Use NumPy vectorization instead of Python loops
- [ ] Pre-compute indicator arrays before simulation
- [ ] Avoid creating intermediate objects in hot loops
- [ ] Use typed arrays (np.float64) for numerical work
- [ ] Batch database queries instead of N+1
- [ ] Memoize expensive React computations
- [ ] Debounce resize/scroll handlers
- [ ] Use Web Workers for heavy client-side computation

## Measurement Protocol

1. **Baseline**: Measure current performance
   ```bash
   time make test-fast
   ```

2. **Profile**: Identify bottleneck
   ```bash
   python -m cProfile -s tottime ...
   ```

3. **Optimize**: Apply targeted fix

4. **Verify**: Re-measure to confirm improvement
   ```bash
   time make test-fast  # Should be faster
   ```

5. **Regression Test**: Ensure correctness unchanged
   ```bash
   make test  # All tests pass
   ```

## Target Benchmarks

| Operation | Target | Acceptable |
|-----------|--------|------------|
| 1-year backtest | < 100ms | < 500ms |
| Chart initial load | < 200ms | < 500ms |
| Indicator computation | < 50ms | < 200ms |
| API response | < 100ms | < 300ms |
