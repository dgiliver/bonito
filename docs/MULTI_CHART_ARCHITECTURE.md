# Multi-Chart Architecture for Bonito

## Problem Statement

The current single-chart approach using Lightweight Charts has fundamental limitations:
1. **Single right-side scale** - Cannot show different value ranges (price vs RSI 0-100) simultaneously
2. **Overlay scales don't render labels** - Custom priceScaleIds share visual space but don't show scale values
3. **Margin conflicts** - Trying to stack panels via scaleMargins creates visual artifacts

## Proposed Solution: Separate Chart Instances

Each panel (price, RSI, MACD, Stochastic, etc.) is its own Lightweight Charts instance with:
- Its own right-side scale showing appropriate values
- Shared time axis (synchronized)
- Synchronized crosshair position
- Independent auto-scaling

```
┌─────────────────────────────────────────────────────────────────┐
│                    IntelligentChart (Container)                  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │                    PriceChartPanel                        │     │
│  │  ┌─────────────────────────────────────┐  ┌───────────┐  │     │
│  │  │   Candlesticks + Volume + Overlays  │  │  Price    │  │     │
│  │  │   (SMA, EMA, Bollinger Bands)       │  │  Scale    │  │     │
│  │  │   OHLCV legend in top-left          │  │  (right)  │  │     │
│  │  └─────────────────────────────────────┘  └───────────┘  │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │                     RSIPanelChart                         │     │
│  │  ┌─────────────────────────────────────┐  ┌───────────┐  │     │
│  │  │   RSI Line + Threshold zones        │  │  RSI      │  │     │
│  │  │   "RSI(14) 53.87" in top-left       │  │  Scale    │  │     │
│  │  │                                     │  │  (0-100)  │  │     │
│  │  └─────────────────────────────────────┘  └───────────┘  │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │                    MACDPanelChart                         │     │
│  │  ┌─────────────────────────────────────┐  ┌───────────┐  │     │
│  │  │   MACD + Signal + Histogram         │  │  MACD     │  │     │
│  │  │   Values in top-left                │  │  Scale    │  │     │
│  │  └─────────────────────────────────────┘  └───────────┘  │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                   │
│                    ← Shared Time Axis →                          │
└─────────────────────────────────────────────────────────────────┘
```

## Component Hierarchy

```typescript
// Container manages layout and synchronization
interface ChartContainerProps {
  symbol: string;
  interval: string;
  range: string;
  data: OHLCVData[];
  indicators: IndicatorConfig[];
  trades?: Trade[];
}

// Base class for all chart panels
abstract class BaseChartPanel {
  protected chart: IChartApi;
  protected container: HTMLDivElement;

  abstract render(data: any[]): void;
  abstract cleanup(): void;

  // Shared functionality
  syncTimeScale(visibleRange: LogicalRange): void;
  syncCrosshair(time: number): void;
  getVisibleRange(): LogicalRange;
}

// Price chart with candlesticks, volume, overlays
class PriceChartPanel extends BaseChartPanel {
  private candleSeries: ISeriesApi<"Candlestick">;
  private volumeSeries: ISeriesApi<"Histogram">;
  private overlayIndicators: Map<string, ISeriesApi<"Line">>;
}

// Panel indicator (RSI, MACD, Stochastic, ADX, etc.)
class PanelChartPanel extends BaseChartPanel {
  private indicatorType: string;
  private mainSeries: ISeriesApi<"Line">;
  private thresholdLines?: ISeriesApi<"Line">[];
}
```

## Synchronization System

### Time Axis Sync
All charts share the same visible time range:
```typescript
// When any chart's time range changes
chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
  otherCharts.forEach(c => c.timeScale().setVisibleLogicalRange(range));
});
```

### Crosshair Sync
When crosshair moves in one chart, sync to others:
```typescript
// Master chart emits crosshair position
chart.subscribeCrosshairMove((param) => {
  const time = param.time;
  otherCharts.forEach(c => c.setCrosshairPosition(time));
});
```

### Data Sync
All charts use the same time-indexed data:
```typescript
interface TimeIndexedData {
  [timestamp: number]: {
    ohlcv: OHLCVBar;
    indicators: {
      rsi?: number;
      macd?: { macd: number; signal: number; histogram: number };
      // ... other indicators
    };
  };
}
```

## Height Management

Dynamic height allocation based on active panels:
```typescript
interface PanelHeights {
  price: number;   // e.g., 60% when 1 panel, 50% when 2 panels
  panels: number;  // e.g., 40% / numPanels
}

// Height calculation
function calculateHeights(panelCount: number): PanelHeights {
  if (panelCount === 0) return { price: 100, panels: 0 };
  if (panelCount === 1) return { price: 70, panels: 30 };
  if (panelCount === 2) return { price: 55, panels: 22.5 };
  return { price: 45, panels: (55 / panelCount) };
}
```

## Implementation Plan

### Phase 1: Core Infrastructure (2-3 days)
- [ ] Create `BaseChartPanel` abstract class
- [ ] Implement time axis synchronization
- [ ] Implement crosshair synchronization
- [ ] Create `ChartContainer` component

### Phase 2: Price Chart Panel (1-2 days)
- [ ] Extract price chart logic into `PriceChartPanel`
- [ ] Integrate overlay indicators (SMA, EMA, Bollinger)
- [ ] OHLCV legend in top-left
- [ ] Trade markers integration

### Phase 3: Panel Indicators (2-3 days)
- [ ] Create `PanelChartPanel` class
- [ ] RSI implementation with thresholds
- [ ] MACD implementation with histogram
- [ ] Stochastic implementation
- [ ] Dynamic height adjustment

### Phase 4: Agent Integration (1 day)
- [ ] Update agent tools for multi-chart control
- [ ] Crosshair-based context for agent awareness
- [ ] Intent handling for panel add/remove

### Phase 5: Testing & Polish (1-2 days)
- [ ] Unit tests for each panel type
- [ ] Integration tests for synchronization
- [ ] Performance testing with multiple panels
- [ ] Visual regression tests

## Benefits

1. **Proper Scale Values**: Each panel shows its own scale (RSI: 0-100, MACD: actual values, Price: actual values)
2. **Clean Separation**: Each panel is self-contained, easy to test and maintain
3. **Extensibility**: Adding new panel types (ADX, ATR, Williams %R) is straightforward
4. **Professional UX**: Matches industry-standard platforms (TradingView, Robinhood Legend)
5. **Agent Integration**: Clear boundaries for agent awareness and control

## File Structure

```
web/src/components/analysis/
├── IntelligentChart.tsx          # Container + orchestration
├── charts/
│   ├── BaseChartPanel.ts         # Abstract base class
│   ├── PriceChartPanel.tsx       # Price + volume + overlays
│   ├── PanelChartPanel.tsx       # Generic panel indicator
│   └── CrosshairSync.ts          # Synchronization utilities
├── panels/
│   ├── RSIPanel.tsx              # RSI-specific config
│   ├── MACDPanel.tsx             # MACD-specific config
│   └── StochasticPanel.tsx       # Stochastic-specific config
└── indicators/                   # Existing indicator classes
    └── ...
```

## Migration Strategy

1. Keep existing `IntelligentChart.tsx` working during transition
2. Build new components in parallel (`charts/` folder)
3. Feature flag to switch between old and new architecture
4. Gradual migration with A/B testing
5. Remove old code once new architecture is stable

## Success Criteria

- [ ] RSI panel shows 0-100 scale on right side
- [ ] MACD panel shows actual MACD values on right side
- [ ] Crosshair syncs perfectly across all panels
- [ ] Time axis zoom/pan syncs across all panels
- [ ] Adding/removing panels is smooth with no flickering
- [ ] Agent can control all panels via intents
- [ ] Performance: <16ms frame time with 3+ panels
