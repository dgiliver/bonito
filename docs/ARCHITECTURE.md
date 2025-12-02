# AI-Native Quant Platform Architecture

## Core Philosophy

This platform inverts the traditional quant workflow. Instead of:
```
Human writes code → Platform runs backtest → Human interprets → Human rewrites
```

We build:
```
Agent proposes strategy → Tools execute backtest → Agent interprets → Agent refines → Human approves
```

The human becomes a **supervisor** rather than an **implementer**.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                  │
│                    (CLI for MVP, Web UI for v1.0)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR LAYER                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Agent Runtime  │  │  Session State  │  │  Conversation History       │  │
│  │  (LLM + Tools)  │  │  (Portfolio,    │  │  (Decisions, Rationale,     │  │
│  │                 │  │   Strategies)   │  │   Traces)                   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TOOL LAYER                                      │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Backtest    │  │  Market Data │  │  Execution   │  │  Analysis    │    │
│  │  Engine      │  │  Service     │  │  Simulator   │  │  Tools       │    │
│  │              │  │              │  │              │  │              │    │
│  │ • run()      │  │ • get_bars() │  │ • place()    │  │ • metrics()  │    │
│  │ • validate() │  │ • stream()   │  │ • cancel()   │  │ • explain()  │    │
│  │ • explain()  │  │ • symbols()  │  │ • status()   │  │ • compare()  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CORE LAYER                                      │
│                                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │  Strategy Runtime    │  │  Event Engine        │  │  Portfolio       │  │
│  │                      │  │                      │  │  State           │  │
│  │  • Code sandbox      │  │  • Bar processing    │  │  • Positions     │  │
│  │  • Signal generation │  │  • Order matching    │  │  • Cash          │  │
│  │  • State management  │  │  • Fill simulation   │  │  • History       │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PERSISTENCE LAYER                                  │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │  Market Data     │  │  Strategy Store  │  │  Trace Store             │  │
│  │  (DuckDB)        │  │  (SQLite)        │  │  (SQLite + JSON)         │  │
│  │                  │  │                  │  │                          │  │
│  │  • OHLCV bars    │  │  • Code versions │  │  • Backtest results      │  │
│  │  • Tick data     │  │  • Parameters    │  │  • Agent decisions       │  │
│  │  • Fundamentals  │  │  • Metadata      │  │  • Performance logs      │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Strategy Representation

**NOT** arbitrary Python code. Instead, a **constrained DSL** with escape hatches.

```python
# Example Strategy Definition (not arbitrary code)
class StrategyConfig:
    name: str
    symbols: list[str]
    timeframe: str  # "1m", "5m", "1h", "1d"
    
    # Indicators are pre-defined, parameterized
    indicators: list[IndicatorConfig]
    
    # Entry/exit rules use a mini-DSL
    entry_rules: list[Rule]
    exit_rules: list[Rule]
    
    # Risk parameters
    position_size: PositionSizer
    stop_loss: StopLossConfig | None
    take_profit: TakeProfitConfig | None
```

Why? Because:
- LLMs can reliably generate structured configs
- Validation is straightforward
- No security sandbox needed
- Deterministic execution
- Easy to explain/audit

**Escape hatch**: Custom Python functions can be registered for advanced users, but the agent doesn't generate these.

### 2. Backtesting Engine

**Vectorized-first, event-capable.**

For MVP:
- Vectorized pandas/numpy for simple strategies (fast: <1s)
- Pre-computed indicators
- Simple fill model (next-bar open)

Post-MVP:
- Event-driven mode for complex strategies
- Realistic slippage/fill models
- Multi-asset portfolio simulation

### 3. Tool Protocol

Each tool follows a standard interface:

```python
@dataclass
class ToolResult:
    success: bool
    data: dict | None
    error: str | None
    trace_id: str  # For debugging/audit

class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def description(self) -> str: ...
    
    @property
    @abstractmethod
    def parameters(self) -> dict: ...  # JSON Schema
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...
```

### 4. Agent Architecture

**ReAct-style agent** with:
- Explicit reasoning traces (logged)
- Tool selection
- Result interpretation
- Iterative refinement

```
Loop:
  1. Think: What should I do next?
  2. Act: Call a tool
  3. Observe: Interpret results
  4. Decide: Continue refining or return to user
```

---

## Data Flow: Strategy Development Cycle

```
┌─────────────┐
│ User Query  │  "Create a momentum strategy for SPY"
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ Agent: Plan                                  │
│ 1. Define strategy structure                 │
│ 2. Configure indicators (RSI, SMA)           │
│ 3. Set entry/exit rules                      │
│ 4. Run backtest                              │
│ 5. Analyze results                           │
│ 6. Refine if needed                          │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ Agent: Generate Strategy Config              │
│                                              │
│ {                                            │
│   "name": "spy_momentum_v1",                 │
│   "symbols": ["SPY"],                        │
│   "timeframe": "1d",                         │
│   "indicators": [                            │
│     {"type": "RSI", "period": 14},           │
│     {"type": "SMA", "period": 50}            │
│   ],                                         │
│   "entry_rules": [...],                      │
│   "exit_rules": [...]                        │
│ }                                            │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ Tool: backtest.run(strategy_config)          │
│                                              │
│ Returns:                                     │
│ {                                            │
│   "sharpe": 1.2,                             │
│   "max_drawdown": -0.15,                     │
│   "total_return": 0.45,                      │
│   "win_rate": 0.58,                          │
│   "trades": [...],                           │
│   "equity_curve": [...]                      │
│ }                                            │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ Agent: Analyze & Decide                      │
│                                              │
│ "Sharpe of 1.2 is decent, but max drawdown   │
│ of 15% is high. Let me add a volatility      │
│ filter to avoid entries during high-vol      │
│ periods..."                                  │
│                                              │
│ → Modify strategy config                     │
│ → Re-run backtest                            │
│ → Repeat until satisfactory                  │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ Agent: Present Results to User               │
│                                              │
│ "Here's your momentum strategy. After 3      │
│ iterations, I achieved:                      │
│ - Sharpe: 1.5                                │
│ - Max DD: 10%                                │
│ - 127 trades over 5 years                    │
│                                              │
│ Key decisions:                               │
│ - Added ATR filter (iteration 2)             │
│ - Widened stop loss (iteration 3)            │
│                                              │
│ Want me to deploy to paper trading?"         │
└─────────────────────────────────────────────┘
```

---

## Security Model

### Strategy Execution Sandbox

Even with a constrained DSL, we sandbox execution:

1. **No network access** during backtest
2. **No file system access**
3. **CPU/memory limits** per backtest
4. **Timeout enforcement**
5. **Pre-approved indicator/function allowlist**

For MVP: Use `RestrictedPython` or simple AST validation
Post-MVP: Consider WASM sandbox or subprocess isolation

---

## Scalability Considerations (Post-MVP)

1. **Backtest parallelization**: Run multiple parameter combinations simultaneously
2. **Data partitioning**: Shard market data by symbol/date
3. **Agent queue**: Multiple users, queued agent sessions
4. **Caching**: Indicator pre-computation, result caching

---

## External Integrations (Post-MVP)

| Integration | Purpose | Priority |
|------------|---------|----------|
| Alpaca | Paper/live trading | High |
| Polygon.io | Market data | High |
| Interactive Brokers | Live trading | Medium |
| OpenBB | Alternative data | Medium |
| Weights & Biases | Experiment tracking | Low |

