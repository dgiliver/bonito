# Agent-Chart Synthesis: Integration Rules & Workflows

> ⚠️ **Authoritative Rules**: The core integration rules are in `.cursor/rules/bonito-standards.mdc`.
> This document provides expanded examples and detailed workflows.

> **Philosophy**: The agent and chart are not separate tools - they form a unified visual analysis system. Every chart feature should enhance the agent's capabilities, and every agent capability should manifest visually.

---

## Core Principles

### 1. Bidirectional Communication
```
┌─────────────┐                    ┌─────────────┐
│    Agent    │◄──── Context ──────│    Chart    │
│             │───── Intents ─────►│             │
└─────────────┘                    └─────────────┘
```
- **Agent → Chart**: Agent sends `ChartIntent` to manipulate visualization
- **Chart → Agent**: Chart provides `ChartContext` with current state

### 2. Shared State via AnalysisContext
All state flows through `AnalysisContext`. Never create parallel state:
```typescript
// ✅ CORRECT: Use shared context
const { state, dispatch } = useAnalysis();
dispatch({ type: "SET_SYMBOL", symbol: "AAPL" });

// ❌ WRONG: Local state that duplicates context
const [symbol, setSymbol] = useState("SPY");
```

### 3. Agent Awareness
The agent should ALWAYS know:
- Current symbol and timeframe
- Visible date range
- Active indicators
- Backtest results (if any)
- Selected trade (if any)
- User's recent interactions

---

## Integration Checklist for New Features

When adding ANY new charting feature, complete this checklist:

### A. Context Exposure
- [ ] Does the agent need to know about this feature's state?
- [ ] Add to `ChartContextPayload` interface if yes
- [ ] Include in context sent to `/api/chat/stream`

### B. Agent Control
- [ ] Should the agent be able to trigger this feature?
- [ ] Add new `ChartIntent` type if yes
- [ ] Implement intent handling in `IntelligentChart`

### C. User Interaction → Agent
- [ ] Can the user interact with this feature?
- [ ] Should interactions inform the agent?
- [ ] Add event dispatch to notify agent of user actions

### D. Visual Feedback
- [ ] Does the agent's output need visual representation?
- [ ] Implement annotation/marker/overlay as needed

---

## Feature Integration Patterns

### Pattern 1: Indicators

**When adding a new indicator overlay:**

```typescript
// 1. Context: Agent knows which indicators are active
interface ChartContext {
  indicators: {
    type: string;      // "rsi", "macd", "bollinger"
    params: Record<string, number>;
    visible: boolean;
  }[];
}

// 2. Intent: Agent can add/remove indicators
interface ChartIntent {
  type: "overlay";
  indicator: {
    type: "rsi";
    params: { period: 14 };
    visible: true;
  };
}

// 3. User Action → Agent: User toggles indicator
const handleIndicatorToggle = (indicator: string) => {
  dispatch({ type: "TOGGLE_INDICATOR", indicator });
  // Agent is notified via context update
};

// 4. Quick Action: Suggest relevant indicators
// After backtest, suggest: "Add RSI to see overbought exits"
```

**Example agent prompts that should work:**
- "Add RSI(14) to the chart" → Agent sends overlay intent
- "What indicators are showing?" → Agent reads context
- "The RSI is overbought" → Agent sees RSI value in context

---

### Pattern 2: Drawing Tools

**When adding drawing tools (trendlines, support/resistance):**

```typescript
// 1. Context: Agent knows about drawn elements
interface ChartContext {
  drawings: {
    id: string;
    type: "trendline" | "horizontal" | "fibonacci" | "rectangle";
    points: { time: number; price: number }[];
    label?: string;
  }[];
}

// 2. Intent: Agent can draw
interface ChartIntent {
  type: "draw";
  drawing: {
    type: "horizontal";
    price: 450.00;
    label: "Resistance";
    color: "#ef4444";
  };
}

// 3. User Action → Agent: User draws a line
const handleUserDraw = (drawing: Drawing) => {
  dispatch({ type: "ADD_DRAWING", drawing });
  // Optionally trigger agent analysis:
  // "I see you drew a trendline. This could indicate..."
};
```

**Example agent prompts that should work:**
- "Draw support at $420" → Agent sends draw intent
- "What levels have I marked?" → Agent reads drawings from context
- "Analyze my trendline" → Agent sees user's drawing, explains significance

---

### Pattern 3: Comparisons

**When adding symbol comparisons:**

```typescript
// 1. Context: Agent knows comparison state
interface ChartContext {
  comparisons: {
    symbol: string;
    color: string;
    visible: boolean;
    correlation?: number;  // Calculated correlation coefficient
  }[];
}

// 2. Intent: Agent can add comparisons
interface ChartIntent {
  type: "compare";
  symbol: "QQQ";
  color: "#8b5cf6";
}

// 3. Agent Analysis: Automatic correlation insight
// When comparison added, agent could say:
// "SPY and QQQ have 0.92 correlation over this period"
```

**Example agent prompts that should work:**
- "Compare with QQQ" → Agent adds comparison overlay
- "How correlated are these?" → Agent calculates and explains
- "Remove all comparisons" → Agent clears comparison intents

---

### Pattern 4: Time Navigation

**When adding time range controls:**

```typescript
// 1. Context: Agent knows visible range
interface ChartContext {
  visibleRange: {
    start: number;  // Unix timestamp
    end: number;
  };
  dataRange: {
    start: number;  // Full available data range
    end: number;
  };
}

// 2. Intent: Agent can navigate
interface ChartIntent {
  type: "navigate";
  range?: { start: number; end: number };
  timestamp?: number;  // Jump to specific point
}

// 3. User Scroll → Agent: User pans to new area
// Debounced update to agent context
```

**Example agent prompts that should work:**
- "Zoom to March 2023" → Agent sends navigate intent
- "Show the 2020 crash" → Agent navigates to that period
- "What period am I viewing?" → Agent reads visibleRange

---

### Pattern 5: Annotations & Signals

**When adding annotation capabilities:**

```typescript
// 1. Context: Agent knows annotations
interface ChartContext {
  annotations: {
    id: string;
    type: "marker" | "label" | "region";
    timestamp: number;
    text?: string;
    icon?: "entry" | "exit" | "signal" | "warning";
  }[];
}

// 2. Intent: Agent can annotate
interface ChartIntent {
  type: "annotate";
  annotation: {
    type: "marker";
    timestamp: 1699920000;
    text: "Earnings beat";
    icon: "signal";
  };
}

// 3. Agent Proactive: After analysis, add annotations
// "I've marked 3 potential entry points on your chart"
```

---

## Workflow: Adding a New Chart Feature

### Step 1: Design the Contract
Before coding, define:
1. **State shape**: What data does this feature need?
2. **Context exposure**: What should the agent see?
3. **Intent interface**: How can the agent control this?
4. **User interactions**: What can the user do?

### Step 2: Update AnalysisContext
```typescript
// Add to state type
interface AnalysisState {
  // ... existing
  newFeature: {
    enabled: boolean;
    config: NewFeatureConfig;
  };
}

// Add action types
type AnalysisAction =
  | { type: "ENABLE_NEW_FEATURE"; config: NewFeatureConfig }
  | { type: "DISABLE_NEW_FEATURE" }
  // ...
```

### Step 3: Update ChartContext Payload
```typescript
// In buildChartContext()
export function buildChartContext(state: AnalysisState): ChartContextPayload {
  return {
    // ... existing
    newFeature: state.newFeature.enabled ? {
      // relevant data for agent
    } : null,
  };
}
```

### Step 4: Add Intent Handling
```typescript
// In IntelligentChart.tsx useEffect for intents
case "new_feature":
  if (intent.config) {
    // Apply to chart
    applyNewFeature(intent.config);
  }
  break;
```

### Step 5: Add Quick Actions (if applicable)
```typescript
// In ChatPanel quick actions
{state.newFeature.enabled && (
  <button onClick={() => dispatch({ type: "DISABLE_NEW_FEATURE" })}>
    <Icon /> Disable Feature
  </button>
)}
```

### Step 6: Update Agent System Prompt
```python
# In orchestrator.py SYSTEM_PROMPT
## Chart Features
- New Feature: [description of what it does and how to use it]
```

---

## Anti-Patterns to Avoid

### ❌ Silent Features
Features that work but the agent doesn't know about:
```typescript
// BAD: Indicator added without context update
addIndicator("RSI", 14);  // Agent has no idea
```

### ❌ Orphaned State
State that exists outside AnalysisContext:
```typescript
// BAD: Component-local state for shared concerns
const [drawings, setDrawings] = useState([]);  // Should be in context
```

### ❌ One-Way Integration
Features where agent can see but not control (or vice versa):
```typescript
// BAD: Agent can read indicators but not add them
// Should always be bidirectional
```

### ❌ Manual Synchronization
Requiring users to manually sync agent and chart:
```typescript
// BAD: User must click "Refresh" to update agent
// Should be automatic via context
```

---

## Testing New Integrations

For every new feature, verify:

1. **Agent Awareness Test**:
   - Enable feature on chart
   - Ask agent: "What features are active?"
   - Agent should know about the new feature

2. **Agent Control Test**:
   - Ask agent: "Enable [feature] with [params]"
   - Chart should update accordingly

3. **Round-Trip Test**:
   - User enables feature
   - Agent describes what it sees
   - Agent modifies feature
   - Chart reflects changes

4. **Context Persistence Test**:
   - Enable feature, run backtest
   - Switch to trade details and back
   - Feature state should persist

---

## Quick Reference: Intent Types

| Intent Type | Purpose | Example |
|-------------|---------|---------|
| `navigate` | Change visible range | Zoom to backtest period |
| `annotate` | Add markers/labels | Mark entry/exit points |
| `overlay` | Add/remove indicators | Add RSI overlay |
| `highlight` | Emphasize region | Highlight drawdown period |
| `draw` | Create drawings | Draw support line |
| `compare` | Add symbol comparison | Compare with benchmark |
| `clear` | Remove elements | Clear all annotations |

---

## Future Vision

The ultimate goal is **conversational charting**:

```
User: "Show me AAPL with Bollinger Bands, mark where it touched the lower band,
       and highlight any periods where RSI was oversold at the same time"

Agent: [Adds BB overlay]
       [Scans for lower band touches]
       [Adds markers at touch points]
       [Highlights RSI<30 periods]
       [Responds with analysis]
```

Every feature we add should move us closer to this vision.
