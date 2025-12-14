# Trade & Backtest Integration with OOP Indicator Architecture

**Status**: Critical design decision for Phase 0+
**Goal**: Ensure seamless integration between indicators, strategy signals, trade execution, and chart visualization

---

## Current State Analysis

### How It Works Now

1. **Backend Backtest Flow**:
   ```
   StrategyConfig (with IndicatorConfig[])
   → compute_indicators() (backend)
   → evaluate_rules() (uses indicator values)
   → simulate() (generates trades)
   → BacktestResult (with trades[])
   ```

2. **Frontend Display Flow**:
   ```
   BacktestResult.trades[]
   → createTradeMarkers() (IntelligentChart.tsx)
   → SeriesMarker[] (on chart)
   → TradeDetails panel (when clicked)
   ```

3. **Agent Integration**:
   - Agent creates `StrategyConfig` with `IndicatorConfig[]`
   - Agent runs backtest → gets `BacktestResult`
   - Agent can see chart context (indicators active)
   - Agent can control chart (add indicators, navigate)

### The Gap

**Problem**: Indicators are now encapsulated in classes, but:
- Strategy creation still uses `IndicatorConfig` (good ✅)
- Backtest execution uses backend `compute_indicators()` (good ✅)
- **BUT**: Frontend indicator classes don't know about strategy signals
- **BUT**: Trade markers don't show which indicator triggered the signal
- **BUT**: Agent can't see the relationship between indicator values and trade execution

---

## Proposed Architecture: Strategy Signal Integration

### Core Principle

**Indicators → Signals → Trades → Visualization** should be a unified flow where:
1. Indicators calculate values
2. Strategy rules evaluate against indicator values (backend)
3. Trades are generated from signals
4. Frontend shows trades with indicator context
5. Agent understands the full chain

### Design: `StrategySignal` Class

Create a new class that bridges indicators, signals, and trades:

```typescript
// web/src/components/analysis/indicators/strategy/StrategySignal.ts

export interface SignalPoint {
  timestamp: number;
  indicator: string;  // Indicator name that triggered
  indicatorValue: number;
  rule: string;  // Rule that was satisfied (e.g., "rsi_14 > 70")
  type: "entry" | "exit";
  strength: number;  // 0-100, how strong the signal is
}

export class StrategySignal {
  private signals: SignalPoint[] = [];
  private trades: Trade[] = [];

  /**
   * Link backend backtest result to frontend indicators
   * Maps trade execution to indicator values at that time
   */
  linkTradesToIndicators(
    trades: Trade[],
    indicatorRegistry: IndicatorRegistry,
    candleData: CandlestickData<Time>[]
  ): void {
    // For each trade, find indicator values at entry/exit
    this.trades = trades;
    this.signals = trades.flatMap(trade => {
      const entrySignals = this.findSignalsAtTime(
        trade.entry_time,
        indicatorRegistry,
        candleData,
        "entry"
      );
      const exitSignals = this.findSignalsAtTime(
        trade.exit_time,
        indicatorRegistry,
        candleData,
        "exit"
      );
      return [...entrySignals, ...exitSignals];
    });
  }

  /**
   * Get signals that triggered a specific trade
   */
  getSignalsForTrade(tradeId: string): SignalPoint[] {
    const trade = this.trades.find(t => t.id === tradeId);
    if (!trade) return [];

    return this.signals.filter(s =>
      (s.type === "entry" && this.isSameTime(s.timestamp, trade.entry_time)) ||
      (s.type === "exit" && this.isSameTime(s.timestamp, trade.exit_time))
    );
  }

  /**
   * Get all entry signals (for visualization)
   */
  getEntrySignals(): SignalPoint[] {
    return this.signals.filter(s => s.type === "entry");
  }
}
```

### Design: Enhanced Trade Markers

```typescript
// In IntelligentChart.tsx

function createTradeMarkers(
  trades: Trade[],
  candleData: CandlestickData<Time>[],
  selectedTradeId?: string | null,
  strategySignals?: StrategySignal  // NEW
): SeriesMarker<Time>[] {
  // ... existing code ...

  for (const trade of trades) {
    const isSelected = trade.id === selectedTradeId;

    // Get signals that triggered this trade
    const entrySignals = strategySignals?.getSignalsForTrade(trade.id)
      .filter(s => s.type === "entry") || [];

    // Enhanced marker text with indicator context
    const signalText = entrySignals.length > 0
      ? ` (${entrySignals.map(s => s.indicator).join(", ")})`
      : "";

    markers.push({
      time: entryTime,
      position: "belowBar",
      color: isSelected ? "#fbbf24" : trade.side === "long" ? "#22c55e" : "#ef4444",
      shape: isSelected ? "circle" : "arrowUp",
      size: isSelected ? 3 : 1,
      text: isSelected
        ? `★ ENTRY $${trade.entry_price.toFixed(2)}${signalText}`
        : `Entry $${trade.entry_price.toFixed(2)}${signalText}`,
      id: `entry-${trade.id}`,
    });
  }
}
```

### Design: Trade Details Panel Enhancement

```typescript
// In TradeDetails component

function TradeDetails({ trade, strategySignals }: Props) {
  const signals = strategySignals?.getSignalsForTrade(trade.id) || [];

  return (
    <div>
      {/* Existing trade info */}
      <TradeInfo trade={trade} />

      {/* NEW: Signal breakdown */}
      <div className="mt-4">
        <h3>Entry Signals</h3>
        {signals.filter(s => s.type === "entry").map(signal => (
          <div key={signal.timestamp}>
            <span>{signal.indicator}</span>
            <span>{signal.rule}</span>
            <span>Value: {signal.indicatorValue.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Backend Integration Points

### 1. Strategy Rule → Indicator Field Mapping

**Current**: Backend `compute_indicators()` returns dict like:
```python
{
  "rsi_14": np.array([...]),
  "sma_20": np.array([...]),
  ...
}
```

**Frontend**: Indicator classes provide `getStrategyFields()`:
```typescript
class RSIIndicator {
  getStrategyFields(): string[] {
    return ["rsi_14"];  // Must match backend output name
  }
}
```

**Critical**: Frontend indicator field names MUST match backend output names.

### 2. Signal Detection (Future Enhancement)

**Current**: Backend evaluates rules, generates signals, executes trades.

**Future**: Backend could return signal metadata:
```python
class BacktestResult:
    trades: list[Trade]
    signals: list[Signal]  # NEW: Which indicator triggered which rule
    # Signal structure:
    # {
    #   "timestamp": 1234567890,
    #   "indicator": "rsi_14",
    #   "value": 75.5,
    #   "rule": "rsi_14 > 70",
    #   "type": "entry"
    # }
```

---

## Agent Integration

### Enhanced Chart Context

```typescript
interface ChartContextPayload {
  // ... existing fields ...

  // NEW: Strategy context
  activeStrategy: {
    name: string;
    indicators: IndicatorContext[];  // Full context from registry
    recentSignals: SignalPoint[];  // Recent entry/exit signals
    trades: Trade[];  // Recent trades
  } | null;

  // NEW: Trade-indicator relationships
  tradeSignals: Record<string, SignalPoint[]>;  // tradeId -> signals
}
```

### Agent Capabilities

1. **"Why did this trade execute?"**
   - Agent can see indicator values at trade entry
   - Agent can see which rules were satisfied
   - Agent can explain the signal chain

2. **"Show me where RSI triggered entries"**
   - Agent can highlight trades where RSI > 70 (or whatever rule)
   - Agent can add annotations to chart

3. **"What would happen if I changed RSI period to 21?"**
   - Agent can create new strategy with modified indicator
   - Agent can run backtest and compare

---

## Implementation Phases

### Phase 0 (Current): Foundation ✅
- Indicator classes with `getStrategyFields()`
- Registry pattern
- Basic trade markers

### Phase 0.5 (Next): Signal Linking
- Create `StrategySignal` class
- Link trades to indicator values at execution time
- Enhance trade markers with signal context

### Phase 1: Backend Signal Metadata
- Modify `BacktestResult` to include signal metadata
- Return which indicator triggered which rule
- Frontend consumes this metadata

### Phase 2: Visual Signal Indicators
- Show signal points on chart (small markers)
- Color-code by indicator type
- Click signal → show which rule triggered

### Phase 3: Agent Signal Analysis
- Agent can analyze signal quality
- Agent can suggest rule improvements
- Agent can explain trade execution

---

## Critical Considerations

### 1. Field Name Consistency

**MUST**: Frontend `getStrategyFields()` names match backend `compute_indicators()` output names.

**Example**:
- Backend: `"rsi_14"` (from pandas-ta output cleaning)
- Frontend: `RSIIndicator.getStrategyFields()` returns `["rsi_14"]` ✅
- Strategy rule: `"rsi_14 > 70"` ✅

**Validation**: Add test to ensure consistency:
```typescript
// Test: Indicator field names match backend
test("RSI field name matches backend", () => {
  const indicator = new RSIIndicator(config);
  const fields = indicator.getStrategyFields();
  expect(fields).toContain("rsi_14");  // Must match backend
});
```

### 2. Indicator Calculation Consistency

**MUST**: Frontend indicator calculation matches backend calculation.

**Current**:
- Backend uses `pandas-ta` or custom implementations
- Frontend uses custom TypeScript implementations

**Risk**: Discrepancies could cause confusion.

**Solution**:
- Document calculation methods
- Add validation tests comparing frontend/backend outputs
- Consider using same calculation library (if possible)

### 3. Trade-Indicator Synchronization

**Challenge**: Trades are generated from backend indicator values, but frontend shows its own calculated values.

**Solution**:
- Frontend indicators are for **visualization only**
- Strategy execution uses **backend indicators** (source of truth)
- Frontend can show "approximate" indicator values for context
- Trade markers link to backend indicator values (via signal metadata)

### 4. Agent Understanding

**Critical**: Agent must understand:
- Which indicators are active on chart
- Which indicators were used in strategy
- How indicator values relate to trade execution
- How to modify indicators to improve strategy

**Solution**: Enhanced `ChartContextPayload` with full indicator context + signal metadata.

---

## Recommended Next Steps

1. **Immediate (Phase 0.5)**:
   - Create `StrategySignal` class
   - Link trades to indicator values (frontend calculation for visualization)
   - Enhance trade markers with indicator context
   - Update TradeDetails panel to show signals

2. **Short-term (Phase 1)**:
   - Modify backend to return signal metadata
   - Update `BacktestResult` model
   - Frontend consumes signal metadata

3. **Medium-term (Phase 2)**:
   - Visual signal indicators on chart
   - Signal quality analysis
   - Agent signal explanation

---

## Testing Strategy

### Unit Tests
- `StrategySignal.linkTradesToIndicators()` correctly maps trades to signals
- `getSignalsForTrade()` returns correct signals
- Field name consistency (frontend ↔ backend)

### Integration Tests
- Trade markers show correct indicator context
- TradeDetails panel displays signals
- Agent can see trade-indicator relationships

### E2E Tests
- Run backtest → Trades appear → Click trade → See signals
- Agent asks "Why did this trade execute?" → Gets correct answer
- Agent modifies indicator → Runs new backtest → Sees different trades

---

## Summary

**The plan DOES cover strategy integration** (see lines 227-265 in plan), but **trade visualization and signal linking need to be added**.

**Key Addition Needed**: `StrategySignal` class to bridge:
- Backend trade execution (from indicator values)
- Frontend indicator visualization
- Agent comprehension
- Trade details display

This ensures the full chain: **Indicators → Signals → Trades → Visualization → Agent Understanding** is seamless.
