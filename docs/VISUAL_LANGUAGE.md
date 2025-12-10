# Visual Language: Agent-Chart Synthesis

> **The chart IS the conversation. The conversation IS the chart.**

## Executive Summary

Traditional trading platforms separate analysis (charts) from strategy (code/rules) from explanation (documentation). Bonito's opportunity is to **unify these into a single conversational visual experience** where:

1. The AI agent can **control** the chart (add indicators, annotations, navigate)
2. The user can **click** the chart to ask questions ("What happened here?")
3. Strategies are **visualized** as they're created (entry/exit markers, indicator overlays)
4. The agent can **explain in context** ("See this golden cross? That's where we entered")

No one has done this well because it requires:
- A sophisticated chart library (✅ we have Lightweight Charts)
- AI with tool-calling capabilities (✅ we have Claude)
- Tight frontend-backend integration (✅ our stack supports this)

## The Paradigm Shift

### Before (Traditional)
```
User: "Create an RSI strategy"
Agent: "Here's the strategy... [text description]"
Agent: "Backtest results: 25% return, 8% drawdown... [table]"
User: *goes to separate chart view*
User: *mentally maps text results to chart*
User: "I wonder what happened in March..."
User: *manually scrolls, guesses at dates*
```

### After (Visual Language)
```
User: "Create an RSI strategy"
Agent: "Here's the strategy - watch the chart."
       → Chart adds RSI indicator
       → Trade markers appear at entry/exit points
       → Annotations explain key moments

User: *clicks on a red exit marker*
Agent: "This exit on March 15th was triggered by your 5% stop loss.
       The entry at $145 looked good but price gapped down on earnings.
       See the volume spike? That was the catalyst."
       → Chart zooms to trade
       → Highlights volume spike
       → Shows the stop loss level

User: "What if I used ATR stops instead?"
Agent: → Shows alternative stop level on chart
       → "With 2x ATR stops, this trade would have survived the dip
          and exited here instead (+12% vs -5%)"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     UNIFIED ANALYSIS VIEW                            │
├─────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    INTELLIGENT CHART                          │  │
│  │                                                               │  │
│  │  • Price data (candlesticks, volume)                         │  │
│  │  • Agent-controlled indicators (SMA, RSI, etc.)              │  │
│  │  • Trade markers (▲ entry, ▼ exit, — stop loss)              │  │
│  │  • AI annotations (explanations, signals, patterns)          │  │
│  │  • Interactive regions (click → agent responds)              │  │
│  │  • Drawing tools (user draws → agent interprets)             │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↕ bidirectional                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              CONVERSATIONAL INTERFACE                         │  │
│  │                                                               │  │
│  │  "Create strategy..."  → Agent creates, chart updates        │  │
│  │  "What happened here?" → Agent explains, chart highlights    │  │
│  │  "Show me the trades"  → Chart annotates, agent describes    │  │
│  │  "Zoom to the drawdown"→ Chart navigates, agent explains     │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                      SHARED CONTEXT                                  │
│  • chartState: { symbol, interval, visibleRange, cursorPosition }   │
│  • strategyState: { activeStrategy, indicators, rules }             │
│  • backtestState: { results, trades, equityCurve }                  │
│  • annotationState: { markers, lines, labels }                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Core Concepts

### 1. Chart Intents (Agent → Chart)

The agent can emit "intents" that control the chart:

```typescript
interface ChartIntent {
  type: "navigate" | "annotate" | "overlay" | "highlight" | "clear";

  // Navigation
  timestamp?: number;           // Navigate to specific time
  range?: { start: number; end: number }; // Set visible range

  // Annotation
  annotation?: {
    type: "marker" | "line" | "label" | "region";
    timestamp: number;
    text?: string;
    color?: string;
    icon?: "entry" | "exit" | "stop" | "signal" | "warning";
  };

  // Overlay
  indicator?: {
    type: string;      // "sma", "rsi", etc.
    params: object;
    highlight?: boolean;
  };

  // Highlight
  highlightRange?: { start: number; end: number; color: string };
}
```

### 2. Chart Events (Chart → Agent)

The chart emits events the agent can respond to:

```typescript
interface ChartEvent {
  type: "click" | "select" | "hover";

  // Context
  timestamp: number;
  price: number;

  // What was clicked
  target?: {
    type: "candle" | "marker" | "indicator" | "annotation";
    data?: any;
  };

  // Surrounding context
  visibleRange: { start: number; end: number };
  indicators: string[];
}
```

### 3. Contextual Prompting

When processing user messages, the agent receives chart context:

```
CHART CONTEXT:
- Viewing: SPY, 1D timeframe
- Visible range: 2024-01-01 to 2024-06-01
- Active indicators: SMA(20), RSI(14)
- Active strategy: "rsi_momentum" (23 trades in view)
- User clicked: Candle at 2024-03-15, price $485
```

## Implementation Phases

### Phase 1: Context Bridge (Week 1)
**Goal:** Agent knows what user is viewing

- [ ] Create ChartContext provider (React)
- [ ] Pass context to agent on each message
- [ ] Agent can reference "the current chart"
- [ ] Add `analyze_chart` tool for the agent

Deliverables:
- User views SPY chart, asks "Is this a good entry?" → Agent knows they mean SPY

### Phase 2: Trade Visualization (Week 2)
**Goal:** Backtest results appear on chart

- [ ] Trade markers (entry/exit points)
- [ ] Stop loss / take profit lines
- [ ] Click marker → show trade details
- [ ] Strategy indicators auto-appear

Deliverables:
- Run backtest → trades appear on chart
- Click any trade → see entry/exit prices, P&L, duration

### Phase 3: Agent Chart Control (Week 3)
**Goal:** Agent can manipulate chart

- [ ] Implement ChartIntent system
- [ ] Agent can add indicators: "Let me show you the RSI"
- [ ] Agent can navigate: "Look at March"
- [ ] Agent can annotate: "See this candle?" → arrow appears

Deliverables:
- Agent adds/removes indicators during conversation
- Agent navigates chart to relevant moments
- Agent adds annotations to explain concepts

### Phase 4: Interactive Analysis (Week 4)
**Goal:** Chart click → agent explains

- [ ] Click anywhere → "What happened here?"
- [ ] Agent provides contextual analysis
- [ ] Pattern recognition suggestions
- [ ] "Explain this trade" deep dive

Deliverables:
- Click candle → agent explains price action, volume, indicators
- Click trade marker → agent explains why entry/exit happened
- Multi-modal analysis (price + volume + indicators)

### Phase 5: Visual Strategy Building (Week 5)
**Goal:** Draw → strategy

- [ ] Drawing tools (lines, regions)
- [ ] Agent interprets drawings
- [ ] "Create strategy from what I drew"
- [ ] Visual backtesting feedback

Deliverables:
- Draw support line → agent creates price-level rule
- Circle a pattern → agent identifies it
- Mark ideal entries → agent learns preference

## Technical Design

### Frontend State Management

```typescript
// contexts/AnalysisContext.tsx
interface AnalysisState {
  // Chart state
  chart: {
    symbol: string;
    interval: string;
    visibleRange: [number, number];
    indicators: IndicatorConfig[];
  };

  // Active strategy
  strategy: StrategyConfig | null;

  // Backtest results
  backtest: {
    result: BacktestResult | null;
    trades: Trade[];
    selectedTrade: Trade | null;
  };

  // Annotations from agent
  annotations: Annotation[];

  // Agent intents queue (processed by chart)
  pendingIntents: ChartIntent[];
}

// Actions
type AnalysisAction =
  | { type: "SET_SYMBOL"; symbol: string }
  | { type: "SET_STRATEGY"; strategy: StrategyConfig }
  | { type: "SET_BACKTEST"; result: BacktestResult }
  | { type: "ADD_INTENT"; intent: ChartIntent }
  | { type: "PROCESS_INTENT"; intentId: string }
  | { type: "CHART_CLICK"; event: ChartEvent }
  | { type: "SELECT_TRADE"; trade: Trade };
```

### Backend Agent Tools

```python
# New agent tools for visual analysis

class AnalyzeChartTool(Tool):
    """Agent tool to analyze current chart context."""

    async def execute(self, context: ChartContext) -> ToolResult:
        # Analyze price action
        # Identify patterns
        # Check indicator signals
        # Return visual analysis
        pass

class ChartControlTool(Tool):
    """Agent tool to control chart display."""

    async def execute(
        self,
        action: str,  # "navigate", "annotate", "overlay"
        **params
    ) -> ToolResult:
        # Emit chart intents
        # Return confirmation
        pass

class ExplainTradeTool(Tool):
    """Agent tool to explain a specific trade in context."""

    async def execute(
        self,
        trade_id: str,
        context: ChartContext
    ) -> ToolResult:
        # Get trade details
        # Analyze entry conditions
        # Analyze exit conditions
        # Explain in context of chart
        pass
```

### API Endpoints

```python
# New endpoints for visual analysis

@router.post("/api/analysis/context")
async def set_context(context: ChartContext):
    """Receive chart context from frontend."""
    pass

@router.get("/api/analysis/explain/{timestamp}")
async def explain_point(timestamp: int, symbol: str):
    """Get AI explanation for a specific point in time."""
    pass

@router.post("/api/analysis/interpret-drawing")
async def interpret_drawing(drawing: Drawing):
    """Convert user drawing into strategy rules."""
    pass
```

## UI Components

### 1. Unified Analysis View

```tsx
// components/AnalysisView.tsx
export function AnalysisView() {
  return (
    <AnalysisProvider>
      <div className="flex h-full">
        {/* Main chart area */}
        <div className="flex-1">
          <IntelligentChart />
        </div>

        {/* Side panel with chat + details */}
        <div className="w-96 border-l">
          <ChatPanel contextAware={true} />
          <TradeDetails /> {/* Shows when trade selected */}
        </div>
      </div>
    </AnalysisProvider>
  );
}
```

### 2. Intelligent Chart

```tsx
// components/chart/IntelligentChart.tsx
export function IntelligentChart() {
  const { state, dispatch } = useAnalysis();

  // Process intents from agent
  useEffect(() => {
    for (const intent of state.pendingIntents) {
      processIntent(intent, chartRef.current);
      dispatch({ type: "PROCESS_INTENT", intentId: intent.id });
    }
  }, [state.pendingIntents]);

  // Handle clicks
  const handleClick = (event: ChartEvent) => {
    dispatch({ type: "CHART_CLICK", event });
    // This triggers agent to explain
  };

  return (
    <ChartContainer onClick={handleClick}>
      <CandlestickSeries />
      <VolumeSeries />
      <IndicatorOverlays indicators={state.chart.indicators} />
      <TradeMarkers trades={state.backtest.trades} />
      <Annotations annotations={state.annotations} />
    </ChartContainer>
  );
}
```

### 3. Context-Aware Chat

```tsx
// components/ChatPanel.tsx
export function ChatPanel({ contextAware }: { contextAware: boolean }) {
  const { state } = useAnalysis();

  const sendMessage = async (message: string) => {
    // Include chart context with message
    const context = contextAware ? {
      symbol: state.chart.symbol,
      interval: state.chart.interval,
      visibleRange: state.chart.visibleRange,
      indicators: state.chart.indicators.map(i => i.name),
      activeStrategy: state.strategy?.name,
      selectedTrade: state.backtest.selectedTrade,
    } : undefined;

    await streamChat(message, sessionId, context);
  };

  // ... rest of chat implementation
}
```

## Example Flows

### Flow 1: Strategy Creation with Visual Feedback

```
User: "Create an RSI momentum strategy for SPY"

Agent: [calls create_strategy]
       [calls run_backtest]
       [emits chart_intent: overlay RSI(14)]
       [emits chart_intent: add trade markers]

       "I've created an RSI momentum strategy. You can see:
        - RSI indicator in the lower panel
        - Green arrows at entry points (RSI < 30)
        - Red arrows at exits

        Total: 23 trades, +34% return, 1.2 Sharpe

        Click any marker to see trade details."

Chart: Shows RSI, entry/exit markers appear
User: *clicks a green arrow*

Agent: "This entry on Jan 15, 2024:
        - RSI dropped to 28 (oversold)
        - Price was $442, below the 20-day SMA
        - Volume was above average (accumulation)

        The trade ran for 8 days to exit at $465 (+5.2%)
        Exit triggered by RSI > 70 (overbought)"

        [emits chart_intent: highlight Jan 15-23 region]
```

### Flow 2: Interactive Analysis

```
User: *viewing SPY chart, clicks on March 15 candle*

Agent: [receives chart_click event with context]

       "March 15, 2024 was significant:
        - Price: $510.50 (all-time high at the time)
        - Volume: 2x average (institutional interest)
        - RSI: 72 (overbought but not extreme)
        - Your active strategy had no position

        This was 2 days before the Fed meeting. The high volume
        suggested smart money positioning.

        Want me to analyze what would have happened if we
        entered here with your strategy?"

User: "Yes, what if we entered?"

Agent: [runs hypothetical analysis]
       [emits chart_intent: show hypothetical trade]

       "If we had entered at $510:
        - Exit would have triggered at $498 (stop loss hit)
        - Loss: -2.4%
        - The Fed hawkish surprise caused the 3-day pullback

        See the dashed line showing the hypothetical trade.
        Your strategy correctly avoided this entry because
        RSI was > 70."
```

### Flow 3: Visual Strategy Building

```
User: *draws a horizontal line at $500 on SPY*

Agent: [receives drawing event]

       "I see you've marked $500 as a significant level.
        Looking at the data:
        - This has acted as support 4 times in 2024
        - Resistance 2 times before the breakout

        Would you like me to:
        1. Create a strategy that buys near this level?
        2. Add it as a stop loss reference?
        3. Analyze historical bounces from this level?"

User: "Create a strategy that buys near this level"

Agent: [creates strategy with price-based rule]
       [shows trade markers for hypothetical entries]

       "Created 'support_500_bounce' strategy:
        - Entry: Price < $502 AND RSI < 40
        - Stop: $495 (1% below support)
        - Target: $520 (4% above)

        Backtested: 8 trades, 62% win rate, +18% total
        See the entry points marked on your chart."
```

## Success Metrics

1. **Engagement:** Time spent in unified view vs. switching between views
2. **Understanding:** User can explain why a strategy worked/failed
3. **Speed:** Time from idea to visualized backtest
4. **Accuracy:** User correctly predicts strategy behavior
5. **Satisfaction:** "This feels like talking to a trading mentor"

## Competitive Advantage

| Feature | Bonito | TradingView | QuantConnect | Bloomberg |
|---------|--------|-------------|--------------|-----------|
| AI Strategy Creation | ✅ | ❌ | ❌ | ❌ |
| Conversational Interface | ✅ | ❌ | ❌ | ❌ |
| Visual + Text Synthesis | ✅ | ❌ | ❌ | ❌ |
| Click-to-Explain | ✅ | ❌ | ❌ | ❌ |
| Agent Chart Control | ✅ | ❌ | ❌ | ❌ |
| Draw-to-Strategy | ✅ | ❌ | ❌ | ❌ |

**This is the moat.** Anyone can add charts. Anyone can add AI.
The synthesis is what no one else has.

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Complexity creep | Start with Phase 1-2, validate before advancing |
| Performance issues | Debounce intents, virtualize annotations |
| User confusion | Clear visual language (consistent colors, icons) |
| Agent hallucination | Ground explanations in real data |

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Context Bridge | 1 week | Agent knows chart state |
| 2. Trade Visualization | 1 week | Trades on chart |
| 3. Agent Control | 1 week | Agent manipulates chart |
| 4. Interactive Analysis | 1 week | Click-to-explain |
| 5. Visual Building | 1 week | Draw-to-strategy |

Total: 5 weeks to full visual language

---

*"The best interface is no interface. The best explanation is showing, not telling."*
