---
name: add-indicator
description: Streamlined skill for adding technical indicators to charts. Handles both backend and frontend setup with proper testing.
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# Add Indicator Skill

Quickly add technical indicators to Bonito's charting system with proper patterns.

## Usage

```bash
/add-indicator <type> <name>
```

Where `<type>` is one of:
- `panel` - Separate panel below price chart (RSI, MACD, Stochastic, ADX)
- `overlay` - Drawn on price chart (SMA, EMA, Bollinger Bands)

## Examples

### Add Panel Indicator (e.g., CCI)
```bash
/add-indicator panel cci
```

### Add Overlay Indicator (e.g., VWAP)
```bash
/add-indicator overlay vwap
```

## Panel Indicator Workflow

### 1. Verify Backend Exists
```bash
grep -n "cci\|CCI" src/bonito/backtest/indicators.py
```

If missing, add to `INDICATOR_FUNCTIONS`:
```python
"cci": lambda df, period=20: ta.cci(df["high"], df["low"], df["close"], length=period).values,
```

### 2. Create Panel Implementation

Create `web/src/components/analysis/indicators/panel/CCIPanelImpl.ts`:
```typescript
import { createChart, IChartApi, ISeriesApi, LineSeries } from 'lightweight-charts';

export class CCIPanelImpl {
  private chart: IChartApi | null = null;
  private cciSeries: ISeriesApi<'Line'> | null = null;
  private cciData: { time: number; value: number }[] = [];

  constructor(
    private height: number,
    private config: { period: number },
    private showTimeScale: boolean
  ) {}

  initialize(container: HTMLElement): void {
    this.chart = createChart(container, {
      height: this.height,
      layout: { background: { color: '#1a1a1a' } },
      grid: { vertLines: { visible: false }, horzLines: { color: '#333' } },
      timeScale: { visible: this.showTimeScale },
      rightPriceScale: { borderVisible: false },
    });

    this.cciSeries = this.chart.addLineSeries({
      color: '#26a69a',
      lineWidth: 2,
    });

    // Add overbought/oversold reference lines
    // CCI typically uses +100/-100
  }

  calculateAndUpdate(candles: CandleData[]): void {
    // Calculate CCI from candle data
    const cci = this.calculateCCI(candles, this.config.period);
    this.cciData = candles.map((c, i) => ({
      time: c.time,
      value: cci[i] ?? 0,
    }));
    this.cciSeries?.setData(this.cciData);
  }

  getLegendData(time: number): { cci: number | null } {
    const point = this.cciData.find(d => d.time === time);
    return { cci: point?.value ?? null };
  }

  // ... rest of implementation
}
```

### 3. Create Panel Component

Create `web/src/components/analysis/panels/CCIPanel.tsx`:
```tsx
import { forwardRef, useRef, useState, useEffect, useImperativeHandle } from 'react';
import { CCIPanelImpl } from '../indicators/panel/CCIPanelImpl';

export const CCIPanel = forwardRef<CCIPanelRef, CCIPanelProps>(
  ({ height, config, showTimeScale }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const panelRef = useRef<CCIPanelImpl | null>(null);
    const [currentValue, setCurrentValue] = useState<number | null>(null);

    // CRITICAL: Recreate impl when height/config changes
    useEffect(() => {
      panelRef.current = new CCIPanelImpl(height, config, showTimeScale);
      return () => panelRef.current?.cleanup();
    }, [height, config, showTimeScale]);

    // CRITICAL: Initialize with deps, NOT []
    useEffect(() => {
      if (containerRef.current && panelRef.current) {
        panelRef.current.initialize(containerRef.current);
      }
    }, [height, config]);

    useImperativeHandle(ref, () => ({
      calculateAndUpdate: (data) => panelRef.current?.calculateAndUpdate(data),
      syncCrosshair: (data) => {
        panelRef.current?.syncCrosshair(data);
        // CRITICAL: Update state for legend persistence
        if (data.time && panelRef.current) {
          const legendData = panelRef.current.getLegendData(data.time);
          setCurrentValue(legendData.cci);
        } else {
          setCurrentValue(null);
        }
      },
      // ... other methods
    }), []);

    return (
      <div className="relative">
        <div className="absolute top-2 left-4 z-10 text-sm text-muted-foreground">
          CCI({config.period}): {currentValue?.toFixed(2) ?? '—'}
        </div>
        <div ref={containerRef} style={{ height }} />
      </div>
    );
  }
);
```

### 4. Register in ChartContainer

Edit `web/src/components/analysis/charts/ChartContainer.tsx`:

```typescript
// 1. Add ref
const cciPanelRef = useRef<CCIPanelRef>(null);

// 2. Add to activePanels.map() switch statement
case "cci":
  return (
    <CCIPanel
      key="cci"
      ref={cciPanelRef}
      height={panelHeight}
      config={panel.config}
      showTimeScale={showTimeScale}
    />
  );

// 3. Add to sync manager registration
if (hasCCI && cciPanelRef.current) {
  crosshairSync.registerPanel("cci", cciPanelRef.current);
}

// 4. Add to updatePanels effect
if (hasCCI && cciPanelRef.current) {
  cciPanelRef.current.calculateAndUpdate(candleData);
}
```

### 5. Add to Indicator Registry

Edit `web/src/components/analysis/indicators/registry/indicatorRegistry.ts`:
```typescript
{
  id: 'cci',
  name: 'Commodity Channel Index',
  category: 'panel',
  defaultConfig: { period: 20 },
  description: 'Momentum oscillator measuring price deviation from mean',
}
```

### 6. Test

```bash
# Build to catch type errors
cd web && npm run build

# Visual verification
/panel-test cci --then macd
```

## Overlay Indicator Workflow

For overlays (drawn on price chart):

### 1. Verify Backend
Same as panel indicators - check/add to `indicators.py`.

### 2. Add to Price Chart

Edit `web/src/components/analysis/charts/PriceChartPanel.tsx`:
```typescript
// Add series for overlay
const vwapSeries = chart.addLineSeries({
  color: '#FF6D00',
  lineWidth: 1,
  priceLineVisible: false,
});

// In update method
const vwap = calculateVWAP(candles);
vwapSeries.setData(vwap);
```

### 3. Add to Registry
Same as panel indicators, but with `category: 'overlay'`.

## Common Pitfalls

1. **Empty deps `[]` in initialize useEffect** - MUST use `[height, config]`
2. **Missing React state for crosshair values** - Legend will show stale data
3. **Forgetting to register with sync manager** - Crosshair won't sync
4. **Wrong series type** - Use `LineSeries` for oscillators, `HistogramSeries` for volume-based

## Verification Checklist

- [ ] Backend calculation returns correct values
- [ ] Panel renders without errors
- [ ] Legend shows indicator name and params
- [ ] Values update on crosshair hover
- [ ] Adding second panel doesn't break first
- [ ] Build passes (`npm run build`)
- [ ] Panel appears in user add order

## Quick Reference

| Indicator | Type | Series | Reference Lines |
|-----------|------|--------|-----------------|
| RSI | Panel | Line | 30, 70 |
| MACD | Panel | 2 Lines + Histogram | 0 |
| Stoch | Panel | 2 Lines | 20, 80 |
| CCI | Panel | Line | -100, +100 |
| ADX | Panel | Line | 25 |
| ATR | Panel | Line | - |
| SMA | Overlay | Line | - |
| EMA | Overlay | Line | - |
| VWAP | Overlay | Line | - |
| BBands | Overlay | 3 Lines + Area | - |
