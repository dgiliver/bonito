# MVP Roadmap: AI-Native Quant Platform

## MVP Definition

**Goal**: A working demo where an AI agent can:
1. Accept a natural language strategy request
2. Generate a valid strategy configuration
3. Run a backtest
4. Interpret results
5. Iterate to improve
6. Present final strategy to user

**Timeline**: 4-6 weeks (solo developer, part-time: 8-10 weeks)

---

## Phase 0: Foundation (Week 1)

### 0.1 Project Setup
- [ ] Python project structure (see file structure below)
- [ ] Dependency management (pyproject.toml / uv)
- [ ] Pre-commit hooks (ruff, mypy)
- [ ] Basic logging infrastructure
- [ ] Configuration management (pydantic-settings)

### 0.2 Data Layer
- [ ] DuckDB setup for market data
- [ ] Data ingestion script (Yahoo Finance for MVP - free, easy)
- [ ] Bar data model (OHLCV)
- [ ] Simple data API: `get_bars(symbol, start, end, timeframe)`

**Deliverable**: Can load and query SPY daily bars from 2019-2024

---

## Phase 1: Backtest Engine (Week 2)

### 1.1 Core Engine
- [ ] Strategy configuration schema (Pydantic models)
- [ ] Indicator library (SMA, EMA, RSI, MACD, ATR, Bollinger)
- [ ] Rule DSL parser (entry/exit conditions)
- [ ] Position sizing models (fixed, percent equity)

### 1.2 Simulation
- [ ] Vectorized backtest loop
- [ ] Order generation from rules
- [ ] Fill simulation (next-bar-open model)
- [ ] Portfolio state tracking (cash, positions, equity)

### 1.3 Metrics
- [ ] Return calculation
- [ ] Sharpe ratio
- [ ] Max drawdown
- [ ] Win rate / profit factor
- [ ] Trade list generation

**Deliverable**: Can backtest a hardcoded EMA crossover strategy, returns JSON metrics

---

## Phase 2: Tool Layer (Week 3)

### 2.1 Tool Protocol
- [ ] Base `Tool` class with standard interface
- [ ] `ToolResult` response model
- [ ] Tool registry

### 2.2 Core Tools
- [ ] `backtest.run` - Execute backtest, return metrics
- [ ] `backtest.explain` - Explain why trades happened
- [ ] `data.get_bars` - Fetch historical data
- [ ] `data.list_symbols` - Available symbols
- [ ] `strategy.validate` - Validate strategy config
- [ ] `analysis.compare` - Compare two strategies

### 2.3 Tool Schemas
- [ ] JSON Schema for each tool's parameters
- [ ] LLM-friendly descriptions

**Deliverable**: Tools callable via Python API with typed inputs/outputs

---

## Phase 3: Agent Integration (Week 4)

### 3.1 LLM Integration
- [ ] OpenAI/Anthropic client setup
- [ ] System prompt for quant agent
- [ ] Tool-calling format (function calling or structured output)

### 3.2 Agent Loop
- [ ] ReAct-style reasoning loop
- [ ] Tool selection and execution
- [ ] Result interpretation
- [ ] Iteration logic (when to refine vs. stop)

### 3.3 Strategy Generation
- [ ] Prompt templates for strategy generation
- [ ] Output parsing to StrategyConfig
- [ ] Validation and error recovery

### 3.4 Conversation Management
- [ ] Session state
- [ ] History tracking
- [ ] Strategy versioning within session

**Deliverable**: Agent can generate, test, and refine a strategy from natural language

---

## Phase 4: Interface & Polish (Week 5-6)

### 4.1 CLI Interface
- [ ] Interactive chat mode
- [ ] Strategy display (pretty-printed config)
- [ ] Results display (metrics table)
- [ ] Equity curve ASCII chart (or save to file)

### 4.2 Persistence
- [ ] Save/load strategies
- [ ] Session history
- [ ] Backtest result archive

### 4.3 Demo Script
- [ ] Pre-written demo scenarios
- [ ] Happy path validation
- [ ] Error case handling

### 4.4 Documentation
- [ ] README with setup instructions
- [ ] Example conversations
- [ ] Architecture overview

**Deliverable**: Polished demo you can show to investors/colleagues

---

## Post-MVP Phases

### Phase 5: Paper Trading (Week 7-8)
- [ ] Real-time data feed (Alpaca free tier)
- [ ] Paper execution simulator
- [ ] Live position tracking
- [ ] Performance monitoring

### Phase 6: Web UI (Week 9-12)
- [ ] Next.js frontend
- [ ] Chat interface
- [ ] Strategy editor
- [ ] Interactive charts
- [ ] Backtest visualizations

### Phase 7: Advanced Features
- [ ] Walk-forward optimization
- [ ] Multi-asset portfolios
- [ ] Custom indicators (user-defined)
- [ ] Strategy templates library
- [ ] Performance attribution

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM generates invalid strategies | Strict schema validation, retry with error feedback |
| Backtest too slow | Start with vectorized approach, optimize hot paths |
| Scope creep | Ruthlessly prioritize; no ML training in MVP |
| Data quality issues | Use well-known data sources (Yahoo Finance, then Polygon) |
| Agent loops forever | Max iteration limits, token budgets |

---

## Success Criteria (MVP)

✅ Agent can generate a working strategy from "Create a momentum strategy for SPY"
✅ Backtest runs in <5 seconds
✅ Agent autonomously refines strategy at least once
✅ Final metrics are reasonable (not obviously broken)
✅ Entire flow completes in <2 minutes
✅ User can save the resulting strategy

---

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | Ecosystem, LLM libs, pandas/numpy |
| Data Store | DuckDB | Fast analytics, embedded, SQL |
| Strategy Store | SQLite | Simple, embedded |
| LLM | Claude / GPT-4 | Best tool-calling support |
| Data Validation | Pydantic v2 | Schema generation, validation |
| CLI | Typer + Rich | Beautiful CLI with minimal effort |
| Async | asyncio | LLM calls, future streaming |
| Testing | pytest | Standard |
| Linting | Ruff | Fast, comprehensive |

---

## Milestones

| Week | Milestone | Demo |
|------|-----------|------|
| 1 | Data layer works | Query SPY bars |
| 2 | Backtest works | Run EMA cross strategy |
| 3 | Tools work | Call backtest via tool interface |
| 4 | Agent works | Agent generates + tests strategy |
| 5 | CLI works | Interactive demo |
| 6 | Polish | Investor-ready demo |
