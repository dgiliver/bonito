# Project Roadmap: AI-Native Quant Platform

**Last Updated:** December 2025
**Current Version:** 0.4.1

---

## ✅ MVP Complete

The MVP is **complete**. All core functionality is working:

| Goal | Status | Notes |
|------|--------|-------|
| Accept natural language strategy request | ✅ | Claude agent with tool calling |
| Generate valid strategy configuration | ✅ | JSON DSL with validation |
| Run a backtest | ✅ | Vectorized engine, <1s execution |
| Interpret results | ✅ | Agent analyzes metrics, suggests improvements |
| Iterate to improve | ✅ | Multi-turn conversation with context |
| Present final strategy | ✅ | Save to JSON, display in UI |

---

## Completed Phases

### ✅ Phase 0: Foundation (Week 1)

- [x] Python project structure (`src/bonito/`)
- [x] Dependency management (pyproject.toml / uv)
- [x] Pre-commit hooks (ruff, mypy)
- [x] Basic logging infrastructure
- [x] Configuration management (pydantic-settings)
- [x] DuckDB setup for market data
- [x] Data ingestion (Yahoo Finance)
- [x] Bar data model (OHLCV)
- [x] Data API: `get_bars(symbol, start, end, timeframe)`

**Deliverable:** ✅ Can load and query SPY daily bars

---

### ✅ Phase 1: Backtest Engine (Week 2)

- [x] Strategy configuration schema (Pydantic models)
- [x] Indicator library (SMA, EMA, RSI, MACD, ATR, Bollinger, Stochastic)
- [x] Rule DSL parser (entry/exit conditions)
- [x] Position sizing models (fixed, percent equity)
- [x] Vectorized backtest loop
- [x] Order generation from rules
- [x] Fill simulation (next-bar-open model)
- [x] Portfolio state tracking (cash, positions, equity)
- [x] Return calculation, Sharpe ratio, max drawdown
- [x] Win rate, profit factor, trade list generation

**Deliverable:** ✅ Can backtest EMA crossover strategy, returns JSON metrics

---

### ✅ Phase 2: Tool Layer (Week 3)

- [x] Base `Tool` class with standard interface
- [x] `ToolResult` response model
- [x] Tool registry
- [x] `backtest.run` - Execute backtest, return metrics
- [x] `data.get_bars` - Fetch historical data
- [x] `data.list_symbols` - Available symbols
- [x] `strategy.create` - Generate strategy config
- [x] `strategy.save/load` - Persist strategies
- [x] JSON Schema for tool parameters
- [x] LLM-friendly descriptions

**Deliverable:** ✅ Tools callable via Python API with typed inputs/outputs

---

### ✅ Phase 3: Agent Integration (Week 4)

- [x] Anthropic Claude client setup
- [x] System prompt for quant agent
- [x] Tool-calling format (Claude native)
- [x] ReAct-style reasoning loop
- [x] Tool selection and execution
- [x] Result interpretation
- [x] Iteration logic
- [x] Prompt templates for strategy generation
- [x] Output parsing to StrategyConfig
- [x] Validation and error recovery
- [x] Session state and history tracking

**Deliverable:** ✅ Agent generates, tests, and refines strategies from natural language

---

### ✅ Phase 4: Interface & API (Week 5)

- [x] Interactive CLI chat mode
- [x] Strategy display (pretty-printed)
- [x] Results display (metrics table)
- [x] Save/load strategies
- [x] FastAPI REST API
- [x] SSE streaming for chat
- [x] Docker containerization

**Deliverable:** ✅ Full API server with streaming chat

---

### ✅ Phase 5: Web UI (Week 6)

- [x] Next.js app with App Router
- [x] Chat interface with streaming
- [x] Markdown rendering (react-markdown)
- [x] Strategy list view
- [x] Data management view
- [x] Equity curve chart (Recharts)
- [x] Quick action buttons
- [x] Responsive sidebar

**Deliverable:** ✅ Working web UI for demos

---

## Current Phase: Post-MVP Enhancement

### 🔄 Phase 6: DSL & Indicators (Weeks 7-8)

Focus: Expand what the DSL can express without custom code.

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| pandas-ta integration (130+ indicators) | 🔥 Critical | 1-2 days | Planned |
| Trailing stops (percent, ATR) | High | 1 day | Planned |
| Short selling support | 🔥 Critical | 2-3 days | Planned |
| Rolling lookback conditions | High | 2-3 days | Planned |
| Custom formula indicators | Medium | 1-2 days | Planned |

**Success criteria:**
- User can use VWAP, ADX, Donchian channels in strategies
- User can short overbought conditions
- User can create "20-day high breakout" strategies

---

### 📋 Phase 7: Plugin System (Weeks 9-10)

Focus: Escape hatch for advanced users who need full Python.

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| StrategyBase abstract class | High | 1 day | Planned |
| Auto-discovery from strategies/ folder | High | 1 day | Planned |
| Parameter schema for agent tuning | Medium | 1 day | Planned |
| Unit test template | Low | 0.5 days | Planned |
| Example plugins (pairs, momentum) | Medium | 1 day | Planned |

**Success criteria:**
- Power user can write Python strategy, have agent backtest it
- Agent can tune parameters on custom strategies

---

### 📋 Phase 8: Multi-Asset & Portfolio (Weeks 11-12)

Focus: Real portfolio strategies with multiple symbols.

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Multi-symbol signal scanning | High | 2 days | Planned |
| Shared capital pool allocation | High | 1 day | Planned |
| Portfolio-level metrics | High | 1 day | Planned |
| Position correlation analysis | Medium | 1 day | Planned |
| Risk parity sizing | Medium | 1 day | Planned |

**Success criteria:**
- User can run same strategy across AAPL, MSFT, GOOGL, TSLA
- See combined equity curve and per-symbol breakdown

---

### 📋 Phase 9: Production Hardening (Weeks 13-14)

Focus: Multi-tenant, scalable, secure deployment.

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Authentication (Clerk/Supabase) | Critical | 2-3 days | Planned |
| PostgreSQL + pgvector migration | High | 2 days | Planned |
| Strategy semantic search | Medium | 1 day | Planned |
| Rate limiting | High | 0.5 days | Planned |
| User isolation (RLS) | Critical | 1 day | Planned |
| Monitoring (Sentry, PostHog) | Medium | 1 day | Planned |

**Success criteria:**
- Multiple users can sign in, each sees only their strategies
- Semantic search: "find my momentum strategies"

---

### 🔮 Phase 10: Paper Trading (Weeks 15-16)

Focus: Bridge from backtest to live markets.

| Task | Priority | Effort | Status |
|------|----------|--------|--------|
| Alpaca OAuth integration | High | 2 days | Planned |
| Real-time bar streaming | High | 2 days | Planned |
| Paper order execution | High | 2 days | Planned |
| Live vs backtest comparison | Medium | 1 day | Planned |
| Kill switch / risk controls | Critical | 1 day | Planned |

**Success criteria:**
- User connects Alpaca paper account
- Strategy runs in real-time, places simulated orders
- Dashboard shows live P&L

---

## Risk Mitigation

| Risk | Mitigation | Status |
|------|------------|--------|
| LLM generates invalid strategies | Strict schema validation, retry with error feedback | ✅ Implemented |
| Backtest too slow | Vectorized approach, optimize hot paths | ✅ Implemented |
| Scope creep | Ruthlessly prioritize; no ML training in MVP | ✅ Active |
| Data quality issues | Use well-known data sources | ✅ Yahoo Finance works |
| Agent loops forever | Max iteration limits, token budgets | ✅ Implemented |
| DSL too limiting | Plugin system as escape hatch | 📋 Planned |
| Single-tenant only | Auth + RLS in Phase 9 | 📋 Planned |

---

## Success Metrics

### MVP (Achieved ✅)

- [x] Agent can generate a working strategy from natural language
- [x] Backtest runs in <5 seconds
- [x] Agent autonomously refines strategy at least once
- [x] Final metrics are reasonable
- [x] Entire flow completes in <2 minutes
- [x] User can save the resulting strategy

### v1.0 Targets

- [ ] 130+ indicators available
- [ ] Short selling works
- [ ] Multi-symbol portfolios work
- [ ] 100 concurrent users supported
- [ ] <100ms semantic search
- [ ] Paper trading connected

---

## Tech Stack

| Component | Current | Planned (v1.0) |
|-----------|---------|----------------|
| Language | Python 3.12 | Python 3.12 |
| AI | Claude Sonnet | Claude Sonnet |
| Market Data DB | DuckDB | DuckDB |
| Strategy Store | JSON files | PostgreSQL + pgvector |
| Cache | - | Redis |
| Data Source | Yahoo Finance | Yahoo + Alpaca |
| Backtesting | NumPy (vectorized) | NumPy + pandas-ta |
| Indicators | Hand-rolled (7) | pandas-ta (130+) |
| CLI | Typer + Rich | Typer + Rich |
| API | FastAPI | FastAPI |
| Web UI | Next.js | Next.js |
| Auth | - | Clerk/Supabase |
| Hosting | Local/Docker | Vercel + Railway |

---

## Timeline Summary

| Phase | Weeks | Status |
|-------|-------|--------|
| Phase 0-5: MVP | 1-6 | ✅ Complete |
| Phase 6: DSL & Indicators | 7-8 | 🔄 Next |
| Phase 7: Plugin System | 9-10 | 📋 Planned |
| Phase 8: Multi-Asset | 11-12 | 📋 Planned |
| Phase 9: Production | 13-14 | 📋 Planned |
| Phase 10: Paper Trading | 15-16 | 📋 Planned |

**Estimated v1.0 completion:** ~10 more weeks (Q1 2026)

---

*Last updated: December 2025*
