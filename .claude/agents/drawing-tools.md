---
name: drawing-tools
description: Implement chart drawing capabilities (trendlines, horizontal levels, annotations, Fibonacci retracements) without breaking existing chart functionality.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---

# Drawing Tools Agent

Specialist for implementing chart annotation and drawing capabilities in Bonito.

## Current State Analysis

**Existing Infrastructure:**
- `lightweight-charts` v4 library with plugin API
- `AnalysisContext` for state management
- Multi-panel chart architecture
- Crosshair sync system

**Missing (to be implemented):**
- Drawing tool selection UI
- Trendline rendering
- Horizontal level lines
- Text annotations
- Fibonacci retracements
- Drawing persistence (save/load)
- Undo/redo for drawings

## Architecture Design

### Drawing State in AnalysisContext

```typescript
// In AnalysisContext.tsx

interface DrawingState {
  drawings: Drawing[];
  selectedTool: DrawingTool | null;
  activeDrawing: Drawing | null;  // Currently being drawn
  history: Drawing[][];  // For undo/redo
  historyIndex: number;
}

type DrawingTool = 'trendline' | 'horizontal' | 'vertical' | 'fibonacci' | 'text' | 'rectangle';

interface Drawing {
  id: string;
  type: DrawingTool;
  points: Point[];  // Start, end for lines; multiple for fib
  style: DrawingStyle;
  panelId: string;  // Which panel it belongs to
  locked: boolean;
  visible: boolean;
}

interface Point {
  time: number;  // Unix timestamp
  value: number;  // Price/indicator value
}

interface DrawingStyle {
  color: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  showLabels: boolean;
}
```

### Drawing Manager

```typescript
// web/src/components/analysis/drawings/DrawingManager.ts

export class DrawingManager {
  private chart: IChartApi;
  private drawings: Map<string, ISeriesApi<'Line'>>;

  constructor(chart: IChartApi) {
    this.chart = chart;
    this.drawings = new Map();
  }

  addTrendline(start: Point, end: Point, style: DrawingStyle): string {
    const id = generateId();
    const lineSeries = this.chart.addLineSeries({
      color: style.color,
      lineWidth: style.lineWidth,
      lineStyle: this.mapLineStyle(style.lineStyle),
    });

    // Calculate intermediate points for the line
    const points = this.interpolateLine(start, end);
    lineSeries.setData(points);

    this.drawings.set(id, lineSeries);
    return id;
  }

  addHorizontalLine(price: number, style: DrawingStyle): string {
    const id = generateId();
    // Use price line from lightweight-charts
    const priceLine = this.chart.addLineSeries({
      color: style.color,
      lineWidth: style.lineWidth,
      priceLineVisible: true,
      lastValueVisible: false,
    });

    // Set data spanning full time range
    const timeRange = this.chart.timeScale().getVisibleRange();
    priceLine.setData([
      { time: timeRange.from, value: price },
      { time: timeRange.to, value: price },
    ]);

    this.drawings.set(id, priceLine);
    return id;
  }

  removeDrawing(id: string): void {
    const series = this.drawings.get(id);
    if (series) {
      this.chart.removeSeries(series);
      this.drawings.delete(id);
    }
  }

  clearAll(): void {
    this.drawings.forEach((series, id) => {
      this.chart.removeSeries(series);
    });
    this.drawings.clear();
  }
}
```

## Implementation Plan

### Phase 1: Core Infrastructure
1. Add `DrawingState` to AnalysisContext
2. Create `DrawingManager` class
3. Add drawing action types to reducer

### Phase 2: Basic Lines
1. Implement horizontal line tool
2. Implement vertical line tool
3. Implement trendline tool (two-point)

### Phase 3: Advanced Tools
1. Fibonacci retracements
2. Rectangle/box tool
3. Text annotations

### Phase 4: UX Polish
1. Drawing toolbar UI
2. Right-click context menu
3. Drag to modify drawings
4. Keyboard shortcuts (Delete to remove)

### Phase 5: Persistence
1. Save drawings to localStorage
2. Associate drawings with symbol
3. Export/import drawing sets

## Key Integration Points

### ChartContainer.tsx

```typescript
// Add drawing manager ref
const drawingManagerRef = useRef<DrawingManager | null>(null);

// Initialize after chart creation
useEffect(() => {
  if (chartRef.current) {
    drawingManagerRef.current = new DrawingManager(chartRef.current);
  }
}, []);

// Handle drawing tool selection
const handleChartClick = useCallback((param: MouseEventParams) => {
  if (selectedTool && param.time && param.point) {
    dispatch({
      type: 'ADD_DRAWING_POINT',
      payload: { time: param.time, value: param.point.y }
    });
  }
}, [selectedTool, dispatch]);
```

### Drawing Toolbar Component

```tsx
// web/src/components/analysis/DrawingToolbar.tsx

export function DrawingToolbar() {
  const { state, dispatch } = useAnalysis();

  const tools: DrawingTool[] = ['trendline', 'horizontal', 'vertical', 'fibonacci', 'text'];

  return (
    <div className="flex gap-2 p-2 border-b border-border">
      {tools.map(tool => (
        <button
          key={tool}
          onClick={() => dispatch({ type: 'SET_DRAWING_TOOL', payload: tool })}
          className={cn(
            'p-2 rounded hover:bg-muted',
            state.drawings.selectedTool === tool && 'bg-primary text-primary-foreground'
          )}
        >
          <ToolIcon tool={tool} />
        </button>
      ))}
      <button
        onClick={() => dispatch({ type: 'CLEAR_DRAWINGS' })}
        className="p-2 rounded hover:bg-destructive hover:text-destructive-foreground"
      >
        Clear All
      </button>
    </div>
  );
}
```

## Testing Strategy

### Unit Tests
```typescript
describe('DrawingManager', () => {
  it('should add trendline between two points', () => {
    const manager = new DrawingManager(mockChart);
    const id = manager.addTrendline(
      { time: 1000, value: 100 },
      { time: 2000, value: 150 },
      { color: '#ff0000', lineWidth: 2, lineStyle: 'solid' }
    );
    expect(id).toBeDefined();
    expect(mockChart.addLineSeries).toHaveBeenCalled();
  });
});
```

### Visual Tests (via Chrome MCP)
1. Select trendline tool
2. Click start point on chart
3. Click end point on chart
4. Verify line renders correctly
5. Zoom/pan - verify line moves with chart
6. Delete line - verify removal

## Compatibility Checklist

Before merging drawing tools:

- [ ] Indicator panels still work (RSI, MACD, Stoch)
- [ ] Crosshair sync unaffected
- [ ] Trade markers still visible
- [ ] Panel ordering preserved
- [ ] Time scale sync works
- [ ] Performance acceptable (no lag on draw)
- [ ] Mobile touch events supported

## Known Challenges

### Challenge 1: Z-Index
Drawings must appear above candlesticks but below crosshair.

**Solution**: Use lightweight-charts layer ordering or custom overlay canvas.

### Challenge 2: Panel Coordination
Drawing on indicator panels vs price chart needs different value scaling.

**Solution**: Each panel has its own DrawingManager instance, coordinated via AnalysisContext.

### Challenge 3: Persistence Across Sessions
Drawings need to persist and reload correctly.

**Solution**: Store in localStorage keyed by symbol, serialize/deserialize on mount.

## Agent Chat Integration

Enable agent to create drawings:

```typescript
// In agent tools
{
  name: 'add_chart_annotation',
  description: 'Add a drawing or annotation to the chart',
  parameters: {
    type: { enum: ['horizontal', 'trendline', 'text'] },
    points: { type: 'array' },
    label: { type: 'string' },
  },
  execute: async (params) => {
    dispatch({ type: 'ADD_DRAWING', payload: params });
    return { success: true, message: 'Drawing added to chart' };
  }
}
```

## Resources

- lightweight-charts docs: https://tradingview.github.io/lightweight-charts/
- Plugin API: https://tradingview.github.io/lightweight-charts/plugins/
- Example drawing tools: https://github.com/nicksheffield/lwc-drawings
