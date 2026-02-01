---
name: indicator-builder
description: Create new technical indicators following Bonito patterns. Use for implementing RSI variants, custom oscillators, overlay indicators, or pandas-ta integrations.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---

# Indicator Builder Agent

Specialized agent for creating new technical indicators in Bonito's architecture.

## Architecture Overview

Bonito has a dual-layer indicator system:
1. **Backend indicators** (`src/bonito/backtest/indicators.py`) - NumPy-based calculations for backtesting
2. **Frontend indicators** (`web/src/components/analysis/indicators/`) - TypeScript visualization

## Creating a Backend Indicator

### Pattern: NumPy Vectorized Calculation

```python
# src/bonito/backtest/indicators.py

def calculate_my_indicator(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculate my custom indicator.

    Args:
        closes: Array of close prices
        period: Lookback period

    Returns:
        Array of indicator values (same length as input)
    """
    result = np.zeros(len(closes))
    # Vectorized calculation (NO loops over bars)
    result[period:] = some_vectorized_operation(closes, period)
    return result
```

### Integration Points

1. **Register in INDICATOR_FUNCTIONS** dict:
```python
INDICATOR_FUNCTIONS = {
    "sma": calculate_sma,
    "rsi": calculate_rsi,
    "my_indicator": calculate_my_indicator,  # Add here
}
```

2. **Add to Strategy DSL** (if needed for conditions):
```python
# In strategy.py IndicatorType enum
class IndicatorType(str, Enum):
    MY_INDICATOR = "my_indicator"
```

## Creating a Frontend Panel Indicator

### File Structure
```
web/src/components/analysis/
├── panels/
│   ├── RSIPanel.tsx       # Example to follow
│   ├── MACDPanel.tsx
│   └── MyIndicatorPanel.tsx  # Create this
├── indicators/
│   └── panel/
│       └── RSIPanelImpl.ts   # Calculation logic
```

### Panel Component Pattern

```tsx
// MyIndicatorPanel.tsx
export const MyIndicatorPanel = forwardRef<
  MyIndicatorPanelRef,
  MyIndicatorPanelProps
>(({ height, config, showTimeScale }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<MyIndicatorPanelImpl | null>(null);
  const [currentValue, setCurrentValue] = useState<number | null>(null);

  // Create impl when height changes
  useEffect(() => {
    panelRef.current = new MyIndicatorPanelImpl(height, config, showTimeScale);
    return () => panelRef.current?.cleanup();
  }, [height, config, showTimeScale]);

  // Initialize chart when container ready
  useEffect(() => {
    if (containerRef.current && panelRef.current) {
      panelRef.current.initialize(containerRef.current);
    }
  }, [height, config]);

  // Expose methods via ref
  useImperativeHandle(ref, () => ({
    calculateAndUpdate: (data) => panelRef.current?.calculateAndUpdate(data),
    syncCrosshair: (data) => {
      panelRef.current?.syncCrosshair(data);
      // Update state for legend
      if (data.time && panelRef.current) {
        const legendData = panelRef.current.getLegendData(data.time);
        setCurrentValue(legendData.value);
      }
    },
    // ... other methods
  }), []);

  return (
    <div ref={containerRef} style={{ height }}>
      <div className="indicator-label">
        MyIndicator({config.period}): {currentValue?.toFixed(2) ?? '—'}
      </div>
    </div>
  );
});
```

### Critical: State Management for Crosshair

**ALWAYS** use React state for values that update on crosshair:
```tsx
const [currentValue, setCurrentValue] = useState<number | null>(null);

// In syncCrosshair:
if (data.time && panelRef.current) {
  const legendData = panelRef.current.getLegendData(data.time);
  setCurrentValue(legendData.value);
}
```

This prevents the panel data from disappearing during cursor movement.

## Integration in ChartContainer

After creating a panel, register in `ChartContainer.tsx`:

1. Add ref: `const myIndicatorPanelRef = useRef<MyIndicatorPanelRef>(null);`
2. Add to `activePanels.map()` switch statement
3. Add to sync manager registration
4. Add to `updatePanels` effect

## Testing Checklist

```bash
# Backend tests
pytest tests/test_indicators.py -k "my_indicator" -v

# Frontend build
cd web && npm run build

# Visual verification
/explore-ui  # Use UI explorer to verify panel renders
```

## pandas-ta Integration

For complex indicators, leverage pandas-ta:

```python
def calculate_complex_indicator(df: pd.DataFrame, **params) -> np.ndarray:
    """Use pandas-ta for complex calculations."""
    import pandas_ta as ta

    result = ta.my_indicator(df["close"], **params)
    # Always return .values for NumPy array
    return result.values if hasattr(result, 'values') else result
```

## Common Pitfalls

1. **Loop-based calculations** - Always use vectorized NumPy operations
2. **Missing NaN handling** - First `period` values should be NaN or 0
3. **Frontend state** - Must use React state for crosshair-updated values
4. **Initialize deps** - Use `[height, config]` not `[]` for initialize useEffect

## Example: Building ADX Panel

```bash
# 1. Check backend indicator exists
grep "adx" src/bonito/backtest/indicators.py

# 2. Create panel implementation
# Follow RSIPanelImpl.ts pattern

# 3. Create panel component
# Follow RSIPanel.tsx pattern with state management

# 4. Register in ChartContainer
# Add to activePanels.map() switch

# 5. Test
/panel-test "adx" --add-first --then-add "rsi"
```
