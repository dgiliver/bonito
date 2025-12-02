# High Priority Implementation Plan

**Purpose:** Detailed analysis and implementation plan for the high-priority features identified in the backlog. No code — just strategy, tradeoffs, and sequencing.

**Last Updated:** December 2025

---

## Executive Summary

The current DSL handles ~60% of retail use cases but hits walls with anything sophisticated. To reach 90%+ coverage and attract serious users, we need:

1. **F019: pandas-ta** — 130+ indicators (1-2 days)
2. **F020: Short Selling** — Doubles strategy universe (2-3 days)
3. **F021: Trailing Stops** — Essential for trend-following (1 day)
4. **F022: Rolling Lookback** — Breakout strategies (2-3 days)
5. **F002: Plugin Interface** — Escape hatch for power users (3-4 days)

**Total estimated effort:** 10-14 days
**Recommended sequence:** F019 → F021 → F020 → F022 → F002

---

## F019: pandas-ta Integration

### Why This First?

**Impact:** Immediately unlocks 130+ indicators with minimal architectural change.

**Current state:** 7 hand-rolled indicators in `indicators.py` (~200 lines). Each new indicator requires manual implementation.

**After:** Any pandas-ta indicator available via DSL. Users can use VWAP, ADX, Donchian without code changes.

### Analysis

**Pros:**
- Massive feature expansion for 1-2 days work
- pandas-ta is actively maintained (unlike TA-Lib)
- Pure Python — no C dependencies, easy Docker builds
- Battle-tested calculations (don't roll your own RSI)

**Cons:**
- Adds ~50MB dependency
- DataFrame conversion overhead (mitigatable)
- Parameter names may differ from our current conventions
- Some indicators return multiple columns (ADX returns ADX, +DI, -DI)

**Risk assessment:**
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Performance regression | Medium | Profile before/after, cache DataFrame |
| Breaking existing strategies | Low | Keep old implementations as fallback |
| Parameter confusion | Medium | Document parameter mapping |

### Implementation Approach

**Option A: Full replacement**
Replace all 7 hand-rolled indicators with pandas-ta equivalents.

*Pros:* Single code path, easier maintenance
*Cons:* Risk of subtle behavioral differences breaking existing strategies

**Option B: Hybrid (Recommended)**
Keep existing implementations, add pandas-ta as additional provider for new indicators.

```
User requests "sma" → Use existing implementation (battle-tested)
User requests "vwap" → Use pandas-ta (not implemented locally)
User requests "adx" → Use pandas-ta (new indicator)
```

*Pros:* Zero risk to existing strategies, gradual migration
*Cons:* Two code paths to maintain initially

**Option C: Adapter with validation**
Use pandas-ta for everything but run parallel validation against old implementations.

*Pros:* Catches discrepancies
*Cons:* Double computation during transition

**Recommendation:** Option B. Ship new indicators fast, migrate old ones later.

### Data Flow

```
Current:
  BarData → compute_indicators() → dict[str, np.ndarray]
                    │
                    └── Hand-rolled SMA, EMA, RSI, etc.

After:
  BarData → compute_indicators() → dict[str, np.ndarray]
                    │
                    ├── Legacy indicators (SMA, EMA, RSI, MACD, ATR, BBands, Stoch)
                    │
                    └── pandas-ta adapter
                            │
                            ├── Convert BarData → DataFrame
                            ├── Call df.ta.{indicator}()
                            └── Extract columns → np.ndarray
```

### Multi-Column Indicators

Some indicators return multiple values:
- **MACD:** line, signal, histogram (we handle this already)
- **ADX:** ADX, +DI, -DI
- **Bollinger:** upper, middle, lower (we handle this already)
- **Stochastic:** %K, %D (we handle this already)

**Naming convention:**
```json
{
  "type": "adx",
  "name": "trend_strength",
  "params": {"length": 14}
}
```
Results in:
- `trend_strength_adx` → ADX value
- `trend_strength_dmp` → +DI
- `trend_strength_dmn` → -DI

### Effort Breakdown

| Task | Effort | Notes |
|------|--------|-------|
| Add pandas-ta dependency | 0.5h | pyproject.toml |
| Create adapter function | 2h | BarData ↔ DataFrame conversion |
| Implement indicator dispatch | 2h | String matching to pandas-ta methods |
| Handle multi-column outputs | 2h | Naming convention |
| Update IndicatorType enum or validation | 1h | Allow dynamic types |
| Test critical indicators (VWAP, ADX, Donchian) | 2h | Verify correctness |
| Update agent prompts | 1h | Teach agent about new indicators |
| Documentation | 1h | List available indicators |

**Total:** 11-12 hours (~1.5 days)

---

## F020: Short Selling Support

### Why This Matters

**Current:** Long-only. Can only profit from upward moves.

**Impact:** Doubles the strategy universe:
- Mean reversion shorts (RSI > 80 → short)
- Trend-following shorts (breakdown below support)
- Hedging (long SPY, short VIX when complacent)
- Pairs trading foundations (long A, short B)

Without shorts, we can't implement:
- Long/short equity
- Market-neutral strategies
- Any bearish thesis

### Analysis

**Architectural Changes:**

1. **DSL Extension**
   ```json
   {
     "entry_rules": [
       {
         "side": "long",  // NEW FIELD
         "conditions": [...]
       },
       {
         "side": "short",
         "conditions": [...]
       }
     ]
   }
   ```

2. **Position Tracking**
   Current: `position: dict | None` — assumes long
   After: `position: {side: "long"|"short", ...}`

3. **P&L Calculation**
   - Long: `(exit_price - entry_price) * quantity`
   - Short: `(entry_price - exit_price) * quantity`

4. **Stop/Take Profit Direction**
   - Long stop: price falls below threshold
   - Short stop: price rises above threshold

**Edge Cases:**

| Scenario | Handling |
|----------|----------|
| Long + Short rules both trigger | Priority? First match? Configurable? |
| Already long, short signal fires | Exit long first? Flip? Ignore? |
| Margin/buying power | Ignore for backtest (assume unlimited) |
| Short borrow costs | Optional parameter, default 0 |
| Uptick rule | Ignore (most modern markets don't enforce) |

**Recommendation:**
- Allow only one position at a time (no hedging in v1)
- If opposite signal fires while in position, exit current first
- No automatic flip — require explicit exit rule

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| P&L calculation bugs | Medium | High | Extensive unit tests |
| Stop direction confusion | Medium | High | Clear test cases for short stops |
| Existing strategy breakage | Low | Medium | Default `side: "long"` for backward compat |
| Infinite loss on shorts | N/A | N/A | Stops required in real trading, optional in backtest |

### Effort Breakdown

| Task | Effort | Notes |
|------|--------|-------|
| Update Rule/StrategyConfig models | 1h | Add `side` field with default |
| Update position tracking in engine | 2h | Track side, adjust P&L calc |
| Update stop/TP logic for shorts | 2h | Invert direction checks |
| Update Trade model | 0.5h | Include side in output |
| Unit tests for short scenarios | 3h | Entry, exit, stop, TP for shorts |
| Update agent prompts | 1h | Teach about short strategies |
| Example short strategy | 0.5h | RSI overbought short |

**Total:** 10-11 hours (~1.5 days)

**Dependency:** None. Can be done independently.

---

## F021: Trailing Stops

### Why This Matters

**Current:** Fixed stops only. Set at entry, never move.

**Problem:** Trend-following strategies need to "let winners run" while protecting profits.

**Example:**
- Entry at $100
- Fixed 5% stop at $95
- Price goes to $150, then crashes to $96
- Fixed stop: exit at $96, keep $1 profit
- Trailing stop: would have exited at $142.50 (5% from $150 high)

### Types to Support

1. **Trailing Percent**
   Trail X% below highest price since entry
   ```json
   {"type": "trailing_percent", "value": 0.05}
   ```

2. **Trailing ATR**
   Trail N × ATR below highest price
   ```json
   {"type": "trailing_atr", "value": 2.0, "atr_period": 14}
   ```

3. **Breakeven Stop** (nice to have)
   Move stop to entry price after X% profit
   ```json
   {"type": "breakeven", "trigger_percent": 0.05}
   ```

### Architectural Changes

**Position State:**
```python
# Current
position = {
    "entry_time": ...,
    "entry_price": ...,
    "quantity": ...
}

# After
position = {
    "entry_time": ...,
    "entry_price": ...,
    "quantity": ...,
    "side": "long" | "short",           # From F020
    "highest_price": ...,               # Track for trailing
    "current_stop": ...                 # Dynamic stop level
}
```

**Engine Loop Changes:**
```
Each bar:
  1. Update highest_price if new high (for longs) / lowest if short
  2. Calculate new trailing stop level
  3. Check if price crossed stop
  4. Execute stop if triggered
```

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Gap down through stop | Exit at open (slippage already modeled) |
| Trailing stop + fixed stop | Use whichever is tighter |
| Short trailing stop | Trail above lowest price since entry |

### Effort Breakdown

| Task | Effort | Notes |
|------|--------|-------|
| Update StopLossConfig model | 0.5h | Add new types |
| Add high-water tracking to position | 1h | Update each bar |
| Implement trailing stop calculation | 2h | Percent and ATR variants |
| Handle short-side trailing | 1h | Invert logic |
| Unit tests | 2h | Various scenarios |
| Update agent prompts | 0.5h | |

**Total:** 7 hours (~1 day)

**Dependency:** Benefits from F020 (short selling) for short trailing stops, but can ship long-only first.

---

## F022: Rolling Lookback Conditions

### Why This Matters

**Current:** Conditions are point-in-time. "RSI < 30" checks current bar only.

**Missing patterns:**
- "Close at 20-day high" (breakout)
- "RSI was below 30 in last 5 bars" (recent oversold)
- "Volume > 2x 20-day average" (volume spike)
- "Price in bottom 10% of 100-day range" (extreme reading)

These are **bread and butter** for systematic traders.

### Design Options

**Option A: Pre-computed Virtual Indicators**

Add rolling stats as first-class indicators:
```json
{
  "indicators": [
    {"type": "rolling_max", "name": "high_20", "params": {"series": "close", "period": 20}},
    {"type": "zscore", "name": "rsi_zscore", "params": {"series": "rsi", "period": 100}}
  ]
}
```

Then reference in conditions:
```json
{"left": "close", "comparison": "gte", "right": "high_20"}
```

*Pros:* Fits current architecture, explicit
*Cons:* Verbose, users must pre-declare everything

**Option B: Inline Expressions**

Allow expressions in condition right-hand side:
```json
{"left": "close", "comparison": "gte", "right": "rolling_max(close, 20)"}
```

*Pros:* Concise, intuitive
*Cons:* Requires expression parser, more complexity

**Option C: New Comparison Operators**

Add lookback-aware comparisons:
```json
{"left": "close", "comparison": "at_period_high", "period": 20}
{"left": "rsi", "comparison": "was_below", "right": 30, "lookback": 5}
```

*Pros:* No parser needed, explicit semantics
*Cons:* Proliferation of comparison types

**Recommendation:** Option A + Option C hybrid

1. Add rolling computed indicators (rolling_max, rolling_min, zscore, percentile)
2. Add `was_above` / `was_below` comparisons with lookback parameter
3. Defer full expression parser to later (high complexity)

### New Computed Indicators

| Indicator | Output | Params |
|-----------|--------|--------|
| `rolling_max` | Highest value in period | series, period |
| `rolling_min` | Lowest value in period | series, period |
| `rolling_mean` | Average (same as SMA) | series, period |
| `zscore` | (value - mean) / std | series, period |
| `percentile` | Percentile rank 0-100 | series, period |

### New Comparison Operators

| Operator | Semantics |
|----------|-----------|
| `was_above` | True if left was > right at any point in lookback period |
| `was_below` | True if left was < right at any point in lookback period |
| `crossed_above_within` | Crossover happened within lookback period |
| `crossed_below_within` | Crossunder happened within lookback period |

### Implementation Complexity

**Rolling computations:** NumPy rolling operations are straightforward:
```python
rolling_max = np.maximum.accumulate(...)  # Needs sliding window variant
# Or use pandas rolling().max()
```

**was_above/was_below:** Requires checking a window of past values:
```python
# For each bar, check if condition was true in any of last N bars
for i in range(lookback):
    result |= (left[:-lookback+i] < right)  # Vectorized but complex indexing
```

### Effort Breakdown

| Task | Effort | Notes |
|------|--------|-------|
| Add rolling indicator types | 2h | rolling_max, rolling_min, zscore, percentile |
| Implement rolling calculations | 3h | Efficient NumPy/pandas |
| Add lookback comparisons | 2h | was_above, was_below |
| Update condition evaluation | 2h | Handle new comparison types |
| Unit tests | 3h | Various scenarios |
| Update agent prompts | 1h | Teach about new capabilities |

**Total:** 13 hours (~2 days)

**Dependency:** None, but benefits from F019 (pandas-ta has some rolling functions).

---

## F002: Strategy Plugin Interface

### Why This Matters

**The escape hatch.** No DSL can express everything. Power users need Python.

**Use cases:**
- Machine learning signals
- Complex multi-asset logic
- Custom indicators not in pandas-ta
- Event-driven strategies (earnings, FOMC)
- Integration with external data sources

### Design Principles

1. **Simple to implement** — One class, one method
2. **Agent-compatible** — Parameters exposed for tuning
3. **Safe to run** — Sandboxed execution (later)
4. **Discoverable** — Auto-loaded from folder

### Interface Design

```python
from abc import ABC, abstractmethod
from bonito.data.models import BarData
import numpy as np

class StrategyBase(ABC):
    """Base class for custom strategies."""

    # Metadata
    name: str = "unnamed_strategy"
    description: str = ""
    version: str = "1.0"

    # Parameters the agent can tune
    parameters: dict[str, ParameterSpec] = {}

    @abstractmethod
    def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
        """
        Compute entry/exit signals from data.

        Args:
            data: OHLCV bar data
            params: Parameter values (from self.parameters)

        Returns:
            SignalOutput with entry_long, exit_long, entry_short, exit_short arrays
        """
        pass

    def compute_indicators(self, data: BarData, params: dict) -> dict[str, np.ndarray]:
        """Optional: compute custom indicators for visualization."""
        return {}
```

### Parameter Schema

For agent tuning:
```python
class ParameterSpec(BaseModel):
    type: Literal["int", "float", "bool", "choice"]
    default: Any
    min: float | None = None
    max: float | None = None
    choices: list[Any] | None = None
    description: str = ""

# Example
class MyStrategy(StrategyBase):
    name = "momentum_zscore"
    parameters = {
        "lookback": ParameterSpec(type="int", default=20, min=5, max=100),
        "threshold": ParameterSpec(type="float", default=2.0, min=0.5, max=4.0),
    }
```

### Auto-Discovery

```
strategies/
├── __init__.py
├── momentum_zscore.py      # Contains MomentumZScore(StrategyBase)
├── pairs_trading.py        # Contains PairsStrategy(StrategyBase)
└── ml_signals.py           # Contains MLStrategy(StrategyBase)
```

On startup:
1. Scan `strategies/` folder
2. Import all `.py` files
3. Find subclasses of `StrategyBase`
4. Register in strategy registry

### Engine Integration

Current engine expects `StrategyConfig` (DSL).

Options:
1. **Adapter pattern:** Wrap plugin output to look like DSL signals
2. **Dual code path:** Engine handles both DSL and plugins
3. **Plugin generates DSL:** Plugin returns StrategyConfig (limited)

**Recommendation:** Option 1 — plugins produce signals, engine consumes uniformly.

```
DSL Strategy → compute_indicators() → evaluate_rules() → signals
Plugin       → compute_signals()                       → signals
                                                           │
                                                           ▼
                                                    Engine simulation
```

### Agent Integration

Agent needs to:
1. List available plugins
2. Understand what parameters each accepts
3. Run backtests with parameter variations
4. Suggest optimizations

**New tools:**
- `list_plugins()` → Returns list of plugin names + descriptions
- `get_plugin_params(name)` → Returns parameter schema
- `run_plugin_backtest(name, params, symbol, dates)` → Execute

### Security Considerations (Future)

For untrusted code:
- Run in subprocess with resource limits
- Whitelist allowed imports
- No network access
- Timeout enforcement
- Memory limits

**For MVP:** Trust user code, add sandboxing later.

### Effort Breakdown

| Task | Effort | Notes |
|------|--------|-------|
| Define StrategyBase abstract class | 1h | |
| Define ParameterSpec and SignalOutput | 1h | |
| Implement auto-discovery | 2h | |
| Create plugin registry | 1h | |
| Integrate with engine | 3h | Adapter for signal consumption |
| Add agent tools | 2h | list_plugins, get_params, run_backtest |
| Example plugin implementations | 2h | 2-3 examples |
| Unit tests | 2h | |
| Documentation | 1h | How to create a plugin |

**Total:** 15 hours (~2 days)

**Dependency:** Benefits from F020 (short selling) for full signal support.

---

## Implementation Sequence

### Recommended Order

```
Week 1:
├── F019: pandas-ta (1.5 days)     ← Biggest bang for buck
└── F021: Trailing stops (1 day)   ← Quick win, enables trend-following

Week 2:
├── F020: Short selling (1.5 days) ← Doubles strategy universe
└── F022: Rolling lookback (2 days) ← Breakout strategies

Week 3:
└── F002: Plugin interface (2 days) ← Escape hatch for power users
```

### Rationale

1. **F019 first:** Most requested feature, unblocks volume/ADX strategies
2. **F021 early:** Small scope, high value, enables "let winners run"
3. **F020 before F022:** Shorts are simpler conceptually, good foundation
4. **F022 before F002:** Covers 90% of remaining DSL gaps
5. **F002 last:** Escape hatch, less urgent if DSL is powerful

### Dependencies Graph

```
F019 (pandas-ta) ──────────────────────────────────────►
        │
        │ (provides ATR for trailing)
        ▼
F021 (trailing stops) ─────────────────────────────────►
        │
        │ (trailing works for shorts too)
        ▼
F020 (short selling) ──────────────────────────────────►
        │
        │ (shorts can use rolling conditions)
        ▼
F022 (rolling lookback) ───────────────────────────────►
        │
        │ (plugins can produce short signals)
        ▼
F002 (plugin interface) ───────────────────────────────►
```

---

## Success Criteria

### F019: pandas-ta
- [ ] User can use VWAP in a strategy
- [ ] User can use ADX in a strategy
- [ ] User can use Donchian channels in a strategy
- [ ] Existing strategies (SMA, RSI, etc.) still work unchanged
- [ ] Agent knows about new indicators

### F020: Short Selling
- [ ] User can create "short when RSI > 80" strategy
- [ ] Short P&L calculated correctly
- [ ] Stop loss works correctly for shorts (triggers on price rise)
- [ ] Agent can suggest short strategies

### F021: Trailing Stops
- [ ] User can add trailing percent stop
- [ ] User can add trailing ATR stop
- [ ] Trailing stop tracks high-water mark correctly
- [ ] Works for both long and short positions

### F022: Rolling Lookback
- [ ] User can create "close at 20-day high" condition
- [ ] User can use "volume > 2x average" condition
- [ ] User can use "RSI was below 30 in last 5 bars"
- [ ] Z-score and percentile work

### F002: Plugin Interface
- [ ] User can create custom strategy Python file
- [ ] Strategy auto-discovered on startup
- [ ] Agent can list and describe plugins
- [ ] Agent can run plugin backtests
- [ ] Agent can tune plugin parameters

---

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| pandas-ta performance issues | Medium | Low | Profile, cache DataFrames |
| Short P&L bugs | High | Medium | Extensive test suite |
| Breaking existing strategies | High | Low | Backward compatibility defaults |
| Plugin security vulnerabilities | High | Low | Defer sandboxing, trust users initially |
| Scope creep | Medium | Medium | Strict feature boundaries |
| Agent confusion with new features | Medium | Medium | Update prompts carefully, test conversations |

---

## Open Questions

1. **pandas-ta parameter naming:** Should we use their names or create aliases?
2. **Short + long simultaneous:** Allow hedging or force single position?
3. **Plugin discovery:** Hot reload or restart required?
4. **Rolling lookback expressions:** Full parser now or later?

---

*This plan will be updated as implementation progresses.*
