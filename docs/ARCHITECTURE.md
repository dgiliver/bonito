# Bonito Architecture

> AI-native algorithmic trading platform — backtesting and deployment built for agents, not scripts.

**Version:** 0.9.1
**Last Updated:** February 2026

---

## Core Philosophy

Traditional quant platforms assume you write deterministic strategies, run slow backtests, and manually iterate. Bonito inverts this:

```
Traditional:  Human writes code → Platform runs backtest → Human interprets → Human rewrites
Bonito:       Agent proposes strategy → Tools execute backtest → Agent interprets → Agent refines → Human approves
```

The human becomes a **supervisor** rather than an **implementer**.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────────┐      ┌─────────────────────────────────────────────────┐  │
│   │    CLI      │      │              Next.js 16 Web UI                  │  │
│   │  (Typer)    │      │   Chat │ Strategies │ Charts │ Trade Analysis  │  │
│   └──────┬──────┘      └────────────────────┬────────────────────────────┘  │
│          │                                   │                               │
│          │         ┌─────────────────────────┤                               │
│          │         │                         │ SSE Streaming                 │
│          ▼         ▼                         ▼                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        FastAPI Server                                │   │
│   │   /api/chat  │  /api/strategies  │  /api/backtest  │  /api/data    │   │
│   └─────────────────────────────────────┬───────────────────────────────┘   │
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
│   │   • Control chart visualization                                      │   │
│   │   • Iterate or respond                                               │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│              ┌───────────────────────┼───────────────────────┐              │
│              ▼                       ▼                       ▼              │
│   ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐      │
│   │  Strategy Tools │     │  Backtest Tools │     │  Chart Tools    │      │
│   │  • create/save  │     │  • run/analyze  │     │  • add_indicator│      │
│   │  • list/load    │     │  • compare      │     │  • spotlight    │      │
│   │  • plugin_run   │     │  • metrics      │     │  • annotate     │      │
│   └─────────────────┘     └─────────────────┘     └─────────────────┘      │
│                                      │                                       │
└──────────────────────────────────────┼───────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENGINE LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                    Vectorized Backtest Engine                       │    │
│   │                                                                     │    │
│   │   Strategy DSL ─► Indicator Calc ─► Signal Gen ─► Simulation       │    │
│   │       (JSON)        (NumPy)         (Rules)       (Vectorized)     │    │
│   │                                                                     │    │
│   │   Features: Long/Short, Trailing Stops, Rolling Lookbacks          │    │
│   │   Outputs: Trades, Equity Curve, Performance Metrics               │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐   │
│   │  pandas-ta Library │    │   Strategy DSL     │    │  Plugin System  │   │
│   │  60+ indicators    │    │   Entry/Exit Rules │    │  Custom Python  │   │
│   │  SMA, RSI, MACD,   │    │   Position Sizing  │    │  strategies     │   │
│   │  ADX, VWAP, etc.   │    │   Trailing Stops   │    │  Auto-discovery │   │
│   └────────────────────┘    └────────────────────┘    └─────────────────┘   │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐   │
│   │   DuckDB           │    │   Strategy Store   │    │  Yahoo Finance  │   │
│   │   (Market Data)    │    │   (JSON Files)     │    │  (Data Source)  │   │
│   │                    │    │                    │    │                 │   │
│   │   OHLCV bars       │    │   strategies/      │    │  Free API       │   │
│   │   Multi-timeframe  │    │   *.json           │    │  Daily data     │   │
│   └────────────────────┘    └────────────────────┘    └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Strategy as Data (Not Code)

Strategies are JSON-serializable configurations, NOT arbitrary Python:

```json
{
  "name": "momentum_rsi",
  "symbols": ["SPY"],
  "timeframe": "1d",
  "indicators": [
    {"type": "rsi", "name": "rsi_14", "params": {"period": 14}},
    {"type": "sma", "name": "sma_50", "params": {"period": 50}}
  ],
  "entry_rules": [{
    "side": "long",
    "conditions": [
      {"left": "close", "comparison": "crosses_above", "right": "sma_50"},
      {"left": "rsi_14", "comparison": "lt", "right": 70}
    ]
  }],
  "exit_rules": [...],
  "stop_loss": {"type": "trailing_percent", "value": 0.05}
}
```

**Why?**
- ✅ LLMs can reliably generate valid configs
- ✅ Easy to validate with Pydantic
- ✅ No security sandbox needed
- ✅ Deterministic execution
- ✅ Easy to audit and explain

**Escape hatch:** Plugin interface for advanced users who need full Python.

### 2. Vectorized Backtesting

All indicator calculations use NumPy arrays (not bar-by-bar loops):
- Sub-second execution for typical strategies
- No arbitrary code execution
- Full auditability of results

### 3. Agent-Chart Synthesis

The agent controls the chart visualization through intents:
- `AnalysisContext` is single source of truth
- Agent sends `ChartIntent` commands (add_indicator, spotlight, annotate)
- Bidirectional: agent sees what user views, controls display

### 4. Tool Protocol (MCP-style)

Every tool follows a standard interface:

```python
class Tool(ABC):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> dict: ...  # JSON Schema

    async def execute(self, **kwargs) -> ToolResult: ...
```

---

## Current Capabilities (v0.9.1)

| Component | Status | Details |
|-----------|--------|---------|
| **Data Ingestion** | ✅ Complete | Yahoo Finance, DuckDB storage |
| **Timeframes** | ✅ Complete | 1m, 5m, 15m, 1h, 4h, 1d |
| **Indicators** | ✅ Complete | 60+ via pandas-ta |
| **Strategy DSL** | ✅ Complete | JSON-based, entry/exit rules, long/short |
| **Short Selling** | ✅ Complete | Full support with correct P&L |
| **Trailing Stops** | ✅ Complete | Percent and ATR-based |
| **Rolling Lookbacks** | ✅ Complete | rolling_max, rolling_min expressions |
| **Plugin System** | ✅ Complete | Custom Python strategies |
| **Backtest Engine** | ✅ Complete | Vectorized, sub-second |
| **AI Agent** | ✅ Complete | Claude, ReAct loop, tool calling |
| **CLI** | ✅ Complete | ingest, backtest, chat commands |
| **REST API** | ✅ Complete | FastAPI with SSE streaming |
| **Web UI** | ✅ Complete | Chart, indicators, trade markers |
| **Multi-panel Charts** | ✅ Complete | RSI, MACD, Stochastic panels |
| **Docker** | ✅ Complete | Dockerfile + docker-compose |

---

## Architecture Components

### Backtest Engine

- Vectorized NumPy operations for speed
- Signal generation from rule evaluation
- Position state tracking (long/short)
- Trailing stop calculation per bar
- Slippage and commission modeling

### Indicator System

Leverages pandas-ta for 60+ indicators:
- Trend: SMA, EMA, MACD, ADX, SuperTrend
- Momentum: RSI, Stochastic, CCI, ROC
- Volatility: ATR, Bollinger Bands, Keltner
- Volume: OBV, VWAP, MFI

### Chart System

Multi-panel synchronized charts using lightweight-charts:
- Price chart with candlesticks and volume
- Indicator panels (RSI, MACD, Stochastic)
- Trade markers with directional coloring
- Crosshair sync across all panels
- Dynamic panel ordering (user add order)

---

## Planned Evolution

### Near-term (v1.0)
- Authentication (Supabase)
- Real-time data (WebSocket feeds)
- Drawing tools (trendlines, annotations)
- Production deployment

### Future
- Paper trading (Alpaca integration)
- Multi-asset portfolios
- Walk-forward optimization
- Crypto support

---

## Performance Targets

| Operation | Current | Target |
|-----------|---------|--------|
| Simple backtest (1 symbol, 4 years) | <1s | <500ms |
| Complex backtest (10 indicators) | <2s | <1s |
| Chart render with panels | <500ms | <200ms |
| Agent response (first token) | ~1s | <500ms |

---

## Security Model

### Current (Development)
- No authentication
- Local-only access
- Strategy configs are JSON (no code execution)

### Planned (Production)
- OAuth via Supabase
- API key authentication
- Row-level security
- Rate limiting
- Sandboxed plugin execution

---

*This document reflects architecture as of v0.9.1. Updated February 2026.*
