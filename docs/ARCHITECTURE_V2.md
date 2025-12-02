# Bonito Architecture

## Overview

This document outlines the current production architecture and the planned evolution to support institutional-grade strategies.

**Current Version:** 0.4.1
**Last Updated:** December 2025

---

## Current Architecture (v0.4)

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐      ┌─────────────────────────────────────────────────┐  │
│   │    CLI      │      │              Next.js Web UI                     │  │
│   │  (Typer)    │      │   Chat │ Strategies │ Data │ Equity Chart      │  │
│   └──────┬──────┘      └────────────────────┬────────────────────────────┘  │
│          │                                   │                               │
│          │         ┌─────────────────────────┤                               │
│          │         │                         │ SSE Streaming                 │
│          ▼         ▼                         ▼                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        FastAPI Server                                │   │
│   │   /api/chat  │  /api/strategies  │  /api/backtest  │  /api/data    │   │
│   └─────────────────────────────────────┬───────────────────────────────┘   │
│                                         │                                    │
└─────────────────────────────────────────┼────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    AI Orchestrator (ReAct Loop)                      │   │
│   │   • Parse user intent                                                │   │
│   │   • Select appropriate tools                                         │   │
│   │   • Execute tool calls                                               │   │
│   │   • Interpret results                                                │   │
│   │   • Iterate or respond                                               │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│              ┌───────────────────────┼───────────────────────┐              │
│              ▼                       ▼                       ▼              │
│   ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐      │
│   │  Strategy Tools │     │  Backtest Tools │     │   Data Tools    │      │
│   │  • create       │     │  • run          │     │  • ingest       │      │
│   │  • save/load    │     │  • analyze      │     │  • list         │      │
│   │  • list         │     │  • compare      │     │  • info         │      │
│   └─────────────────┘     └─────────────────┘     └─────────────────┘      │
│                                      │                                       │
└──────────────────────────────────────┼───────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENGINE LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                    Vectorized Backtest Engine                       │    │
│   │                                                                     │    │
│   │   Strategy DSL ─► Indicator Calc ─► Signal Gen ─► Simulation       │    │
│   │       (JSON)        (NumPy)         (Rules)       (Loop)           │    │
│   │                                                                     │    │
│   │   Outputs: Trades, Equity Curve, Performance Metrics               │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌────────────────────┐    ┌────────────────────┐                          │
│   │  Indicator Library │    │   Strategy DSL     │                          │
│   │  SMA, EMA, RSI,    │    │   Entry/Exit Rules │                          │
│   │  MACD, ATR, BBands,│    │   Position Sizing  │                          │
│   │  Stochastic        │    │   Stop/Take Profit │                          │
│   └────────────────────┘    └────────────────────┘                          │
│                                                                              │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐   │
│   │   DuckDB           │    │   Strategy Store   │    │  Yahoo Finance  │   │
│   │   (Market Data)    │    │   (JSON Files)     │    │  (Data Source)  │   │
│   │                    │    │                    │    │                 │   │
│   │   OHLCV bars       │    │   strategies/      │    │  Free API       │   │
│   │   Multi-timeframe  │    │   *.json           │    │  Limited hist   │   │
│   └────────────────────┘    └────────────────────┘    └─────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Current Capabilities

| Component | Status | Details |
|-----------|--------|---------|
| **Data Ingestion** | ✅ Complete | Yahoo Finance, DuckDB storage |
| **Timeframes** | ✅ Complete | 1m, 5m, 15m, 1h, 4h, 1d |
| **Indicators** | ✅ Basic (7) | SMA, EMA, RSI, MACD, ATR, BBands, Stoch |
| **Strategy DSL** | ✅ Complete | JSON-based, entry/exit rules |
| **Backtest Engine** | ✅ Complete | Vectorized, sub-second |
| **AI Agent** | ✅ Complete | Claude, ReAct loop, tool calling |
| **CLI** | ✅ Complete | ingest, backtest, chat commands |
| **REST API** | ✅ Complete | FastAPI with SSE streaming |
| **Web UI** | ✅ Basic | Chat, strategies, data views |
| **Docker** | ✅ Complete | Dockerfile + docker-compose |

### Current Limitations

See `FEATURE_BACKLOG.md` for detailed analysis. Key gaps:

1. **Long-only** — No short selling
2. **Single symbol** — No multi-asset strategies
3. **Stateless** — No position memory
4. **7 indicators** — Missing volume, ADX, channels
5. **No trailing stops** — Fixed stops only
6. **Single timeframe** — No MTF analysis

---

## Planned Architecture (v1.0)

### Target State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────────┐    ┌───────────────────┐    ┌─────────────────────────┐   │
│   │    CLI      │    │   Web UI (v2)     │    │   Mobile (Future)       │   │
│   └──────┬──────┘    │  • Dark/light     │    └─────────────────────────┘   │
│          │           │  • TradingView    │                                   │
│          │           │  • Strategy editor│                                   │
│          │           └─────────┬─────────┘                                   │
└──────────┼─────────────────────┼─────────────────────────────────────────────┘
           │                     │
           ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FastAPI + Rate Limiting + Auth (Clerk/Supabase)                    │   │
│   │                                                                      │   │
│   │  /api/v1/chat          Stream chat with agent                       │   │
│   │  /api/v1/strategies    CRUD + semantic search                       │   │
│   │  /api/v1/backtest      Run + queue long backtests                   │   │
│   │  /api/v1/data          Ingest + query market data                   │   │
│   │  /api/v1/paper         Paper trading (Alpaca)          [PLANNED]    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    AI Orchestrator (Enhanced)                        │   │
│   │   • Multi-turn context                                               │   │
│   │   • Strategy similarity search                                       │   │
│   │   • Proactive suggestions                                            │   │
│   │   • Walk-forward validation                       [PLANNED]          │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Tool Categories:                                                           │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│   │ Strategy     │ │ Backtest     │ │ Data         │ │ Analysis     │       │
│   │ • create     │ │ • run        │ │ • ingest     │ │ • compare    │       │
│   │ • modify     │ │ • optimize   │ │ • list       │ │ • attribute  │       │
│   │ • save/load  │ │ • walkfwd    │ │ • stream     │ │ • explain    │       │
│   │ • search     │ │              │ │              │ │              │       │
│   └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENGINE LAYER (Enhanced)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Backtest Engine v2                                │   │
│   │                                                                      │   │
│   │   NEW:                                                               │   │
│   │   • Long/Short positions                                             │   │
│   │   • Multi-symbol execution                                           │   │
│   │   • Position state/memory                                            │   │
│   │   • Trailing stops                                                   │   │
│   │   • Scale in/out                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────┐    ┌─────────────────────┐                        │
│   │  pandas-ta Library  │    │  Plugin Interface   │                        │
│   │  130+ indicators    │    │  Custom strategies  │                        │
│   │  • VWAP, OBV, ADX   │    │  Full Python access │                        │
│   │  • Donchian, Keltner│    │  Parameter schemas  │                        │
│   │  • Volume analysis  │    │  Auto-discovery     │                        │
│   └─────────────────────┘    └─────────────────────┘                        │
│                                                                              │
│   ┌─────────────────────┐    ┌─────────────────────┐                        │
│   │  Strategy DSL v2    │    │  Expression Parser  │                        │
│   │  • side: long/short │    │  rolling_max(c,20)  │                        │
│   │  • lookback windows │    │  zscore(rsi, 100)   │                        │
│   │  • trailing stops   │    │  close[10]          │                        │
│   └─────────────────────┘    └─────────────────────┘                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER (Enhanced)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│   │  PostgreSQL +    │  │  Redis           │  │  S3/R2           │          │
│   │  pgvector        │  │  (Cache/Queue)   │  │  (Results)       │          │
│   │                  │  │                  │  │                  │          │
│   │  • Market data   │  │  • Session state │  │  • Large results │          │
│   │  • Strategies    │  │  • Rate limits   │  │  • Backtest logs │          │
│   │  • Embeddings    │  │  • Job queue     │  │  • User files    │          │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                              │
│   Data Providers (Unified Interface):                                        │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│   │ Yahoo Finance│  │ Alpaca       │  │ Polygon.io   │  │ Binance      │    │
│   │ (Free/Basic) │  │ (Free/RT)    │  │ (Paid/Full)  │  │ (Crypto)     │    │
│   └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Migration Path

| Phase | Focus | Key Changes |
|-------|-------|-------------|
| **v0.5** | Indicators | pandas-ta integration, 130+ indicators |
| **v0.6** | Trading | Short selling, trailing stops |
| **v0.7** | DSL v2 | Rolling lookbacks, expressions |
| **v0.8** | Multi-asset | Portfolio backtesting |
| **v0.9** | Plugin | Custom strategy interface |
| **v1.0** | Production | Auth, PostgreSQL, Alpaca paper trading |

---

## Strategy Store with Similarity Search

### Strategy Schema

```python
class StrategyRecord(BaseModel):
    """Persisted strategy with metadata."""

    # Identity
    id: str  # UUID
    name: str
    description: str
    version: int = 1

    # Config
    config: StrategyConfig  # The actual DSL config

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str | None  # User ID
    tags: list[str] = []  # ["momentum", "mean-reversion", "trend-following"]

    # Performance (cached from last backtest)
    last_backtest: BacktestSummary | None

    # For similarity search (planned)
    embedding: list[float] | None  # Vector embedding of description + config
```

### Storage Evolution

| Phase | Storage | Search | Use Case |
|-------|---------|--------|----------|
| **Current** | JSON files | Text match | Local development |
| **v0.6** | SQLite + FTS | Full-text | Single user |
| **v1.0** | PostgreSQL + pgvector | Semantic | Multi-tenant production |

---

## Deployment Architecture

### Development (Current)

```
┌─────────────────────────────────────────┐
│              Your Machine                │
│                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │   CLI   │  │   API   │  │   UI    │  │
│  │ (typer) │  │(FastAPI)│  │(Next.js)│  │
│  └────┬────┘  └────┬────┘  └────┬────┘  │
│       │            │            │        │
│       └────────────┼────────────┘        │
│                    │                     │
│            ┌───────┴───────┐             │
│            │    DuckDB     │             │
│            │  + JSON files │             │
│            └───────────────┘             │
└─────────────────────────────────────────┘
```

### Production (Planned v1.0)

```
┌──────────────────────────────────────────────────────────────┐
│                         Internet                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Cloudflare CDN    │
                    │   (+ WAF, DDoS)     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
    ┌─────────────────┐              ┌─────────────────┐
    │   Next.js UI    │              │   FastAPI       │
    │   (Vercel)      │              │   (Railway)     │
    └─────────────────┘              └────────┬────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    ▼                         ▼                         ▼
          ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
          │   PostgreSQL    │      │     Redis       │      │   S3 / R2       │
          │   + pgvector    │      │   (sessions,    │      │   (backtest     │
          │   (Supabase)    │      │    cache)       │      │    results)     │
          └─────────────────┘      └─────────────────┘      └─────────────────┘
```

---

## Component Details

### Backtest Engine

**Current Implementation:**
- Vectorized NumPy operations
- Single-pass simulation loop
- Signal generation from rule evaluation
- Percent-based stops only

**Planned Enhancements:**
- Position state tracking (bars held, high-water mark)
- Short position support with margin simulation
- Trailing stop calculation per bar
- Multi-symbol portfolio with capital allocation
- Scale in/out with partial positions

### Indicator System

**Current:** Hand-rolled 7 indicators in `indicators.py`

**Planned:** pandas-ta integration

```python
# Current approach (limited)
def compute_indicators(data, indicators):
    for config in indicators:
        if config.type == IndicatorType.SMA:
            results[config.name] = sma(data.close, period)
        # ... 6 more cases

# Planned approach (extensible)
def compute_indicators(data, indicators):
    df = to_dataframe(data)
    for config in indicators:
        # Dynamic dispatch to pandas-ta
        indicator_func = getattr(df.ta, config.type, None)
        if indicator_func:
            indicator_func(**config.params, append=True)
    return from_dataframe(df)
```

### Strategy DSL

**Current Schema:**
```json
{
  "name": "strategy_name",
  "indicators": [...],
  "entry_rules": [{"conditions": [...], "logic": "AND"}],
  "exit_rules": [...],
  "position_size": {"type": "percent_equity", "value": 10},
  "stop_loss": {"type": "percent", "value": 0.05}
}
```

**Planned v2 Schema:**
```json
{
  "name": "strategy_name",
  "indicators": [...],
  "entry_rules": [
    {
      "side": "long",
      "conditions": [
        {"left": "close", "comparison": "gte", "right": "rolling_max(close, 20)"}
      ]
    },
    {
      "side": "short",
      "conditions": [
        {"left": "rsi", "comparison": "gt", "right": 80}
      ]
    }
  ],
  "stop_loss": {
    "type": "trailing_atr",
    "value": 2.0,
    "atr_period": 14
  },
  "position_sizing": {
    "type": "volatility_target",
    "target_vol": 0.15
  }
}
```

---

## Security Considerations

### Current (Development)
- No authentication
- Local-only access
- No user isolation

### Planned (Production)
- OAuth via Clerk/Supabase
- API key authentication
- Row-level security in PostgreSQL
- Rate limiting per user tier
- Sandboxed plugin execution

---

## Performance Targets

| Operation | Current | Target (v1.0) |
|-----------|---------|---------------|
| Simple backtest (1 symbol, 4 years) | <1s | <500ms |
| Complex backtest (10 indicators) | <3s | <1s |
| Portfolio backtest (10 symbols) | N/A | <5s |
| Strategy semantic search | N/A | <100ms |
| Chat response (first token) | ~1s | <500ms |

---

*This document reflects architecture as of v0.4.1. Updated December 2025.*
