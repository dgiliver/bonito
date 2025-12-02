# Bonito: AI-Native Algorithmic Trading Platform

> **From idea to backtested strategy in 60 seconds.**

---

## The Problem

**Existing quant platforms are stuck in 2010.**

| Platform | Pain Point |
|----------|------------|
| QuantConnect | Steep learning curve, C#/Python required, slow iteration |
| Backtrader | Complex API, no AI integration, abandoned maintenance |
| TradingView | Limited backtesting, manual strategy building, Pine Script lock-in |
| Bloomberg Terminal | $24K/year, enterprise-only, overkill for most |
| Zipline | Deprecated, Python 2 legacy, no active development |

**The gap:** No platform lets you go from idea → tested strategy in natural language with intelligent iteration.

**The opportunity:** AI can now understand trading intent, generate valid strategy code, analyze results, and suggest improvements — all in conversation.

---

## The Solution

**Bonito** — describe strategies in plain English, iterate in real-time, deploy with confidence.

```
You: "Create a momentum strategy using RSI with a trend filter"

Agent: Created strategy with RSI(14) + 200-day SMA filter.
       Backtest results: 20.3% return, 0.97 Sharpe, 8.25% max drawdown.

       The RSI < 35 threshold caught better pullback opportunities.
       Would you like me to test on different assets or adjust parameters?
```

**No coding. No configuration files. Just conversation.**

---

## Demo: Strategy Iteration in 60 Seconds

### Round 1: Initial Strategy
```
You: "Create a simple RSI momentum strategy"
```
**Result:** 28.9% return, but 32.8% drawdown (too risky)

### Round 2: Add Risk Management
```
You: "Add a 200-day SMA trend filter"
```
**Result:** -0.12% return (too selective, only 2 trades)

### Round 3: Optimize Parameters
```
You: "Relax to RSI < 35 and use 100-day SMA"
```
**Result:** 20.3% return, 8.25% drawdown, 0.97 Sharpe ✅

**Time elapsed:** ~2 minutes
**Traditional approach:** Hours of coding and manual iteration

---

## What Makes Bonito Different

### 🧠 AI That Actually Understands Trading

Not just GPT wrapper. The agent:
- Knows indicator semantics (RSI 30 = oversold, not "buy signal")
- Understands risk/reward tradeoffs
- Suggests improvements based on backtest analysis
- Explains *why* a strategy works or fails

### ⚡ Sub-Second Backtesting

Vectorized NumPy engine runs years of data in <1 second:
- No waiting for results
- Instant iteration cycles
- Try 10 variations in the time it takes to try 1 elsewhere

### 🔒 Safe by Design

Strategies are defined in a constrained JSON DSL:
- No arbitrary code execution
- Full auditability
- Version controlled
- Schema validated

### 🎯 Intelligent Iteration

The agent doesn't just execute — it coaches:
- "Win rate is low, consider tighter entry conditions"
- "High drawdown suggests adding a trend filter"
- "This strategy is similar to your RSI_momentum_v2 — want to compare?"

---

## Current Capabilities

### ✅ Working Today

| Feature | Status |
|---------|--------|
| Natural language strategy creation | ✅ |
| 7 technical indicators (SMA, EMA, RSI, MACD, ATR, BBands, Stoch) | ✅ |
| Instant backtesting (<1 second) | ✅ |
| Full metrics (Sharpe, Sortino, drawdown, win rate) | ✅ |
| Multi-timeframe data (1m to 1d) | ✅ |
| Strategy save/load | ✅ |
| Web UI with chat interface | ✅ |
| Equity curve visualization | ✅ |
| REST API with SSE streaming | ✅ |
| Docker deployment | ✅ |

### 🔜 Coming Soon

| Feature | Timeline |
|---------|----------|
| 130+ indicators (pandas-ta) | 2 weeks |
| Short selling | 2 weeks |
| Trailing stops | 2 weeks |
| Custom Python strategies | 4 weeks |
| Multi-asset portfolios | 6 weeks |
| Paper trading (Alpaca) | 8 weeks |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Natural Language                          │
│            "Create a momentum strategy..."                   │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI Agent (Claude)                         │
│         • Understands intent                                 │
│         • Creates strategy JSON                              │
│         • Analyzes results                                   │
│         • Suggests improvements                              │
└─────────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Strategy │   │ Backtest │   │   Data   │
        │  Tools   │   │  Engine  │   │   Store  │
        └──────────┘   └──────────┘   └──────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Market Data (DuckDB)                       │
│              Yahoo Finance • Multi-timeframe                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Target Users

### 1. **Aspiring Quants** (Primary)
- Want to learn algorithmic trading
- Don't have programming background
- Need guidance on strategy development
- *"I have ideas but don't know how to test them"*

### 2. **Retail Traders**
- Currently use TradingView/manual trading
- Want to systematize their approach
- Need proper backtesting without learning Pine Script
- *"I want to automate my strategy but coding is a barrier"*

### 3. **Small Funds / RIAs**
- Need rapid strategy prototyping
- Want to reduce developer dependency
- Value iteration speed over infrastructure
- *"We need to test ideas faster than our dev cycle allows"*

---

## Competitive Landscape

| Feature | Bonito | QuantConnect | TradingView | Backtrader |
|---------|--------|--------------|-------------|------------|
| Natural language | ✅ | ❌ | ❌ | ❌ |
| No coding required | ✅ | ❌ | ⚠️ Pine | ❌ |
| AI iteration | ✅ | ❌ | ❌ | ❌ |
| Instant feedback | ✅ | Minutes | Minutes | Minutes |
| Strategy explanation | ✅ | ❌ | ❌ | ❌ |
| Free tier | ✅ | Limited | Limited | ✅ |
| Modern stack | ✅ | ⚠️ | ✅ | ❌ Abandoned |

**Unique moat:** The AI doesn't just execute — it **teaches**, **iterates**, and **explains**.

---

## Business Model (Future)

### Freemium SaaS

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | 50 backtests/mo, 5 saved strategies, basic indicators |
| **Pro** | $29/mo | Unlimited backtests, all indicators, custom formulas |
| **Team** | $99/mo | Multi-user, API access, priority support |
| **Enterprise** | Custom | On-prem, custom integrations, SLA |

### Revenue Streams
1. **Subscriptions** — Primary revenue
2. **Data fees** — Premium data sources (Polygon, options)
3. **Paper trading** — Alpaca partnership revenue share
4. **Strategy marketplace** — Commission on strategy sales (future)

---

## Traction & Roadmap

### Completed (MVP)
- ✅ Full agent loop working
- ✅ 7 indicators, vectorized backtesting
- ✅ Web UI with streaming chat
- ✅ Docker deployment ready

### Next 90 Days
- 130+ indicators (pandas-ta integration)
- Short selling support
- Custom Python strategy plugins
- Multi-asset portfolio backtesting
- Authentication + multi-tenant

### 6-Month Vision
- Paper trading with Alpaca
- Strategy marketplace
- Mobile app
- Options backtesting (data permitting)

---

## Technical Highlights

| Component | Technology | Why |
|-----------|------------|-----|
| AI | Claude Sonnet | Best tool-calling, reasoning |
| Backtesting | NumPy vectorized | <1s execution on years of data |
| Data | DuckDB | Embedded analytics, zero ops |
| API | FastAPI + SSE | Real-time streaming |
| Frontend | Next.js 14 | Modern React, great DX |
| Validation | Pydantic | Schema generation, type safety |

**Lines of code:** ~3,000
**Dependencies:** Minimal, production-ready stack

---

## Sample Conversation

```
You: Create a strategy that buys when MACD crosses above signal line
     and RSI is below 50

Agent: I'll create a MACD crossover strategy with RSI confirmation.

       → create_strategy (macd_rsi_combo)
       → run_backtest (SPY, 2020-2024)

       Results:
       • Total Return: 34.2%
       • Sharpe Ratio: 0.82
       • Max Drawdown: 15.3%
       • Win Rate: 45%
       • Total Trades: 23

       The strategy captures momentum shifts while avoiding
       overbought entries. Win rate is moderate but winners
       are larger than losers (1.8:1 ratio).

       Would you like me to:
       1. Add a trend filter to improve win rate?
       2. Tighten the stop loss?
       3. Test on QQQ for comparison?

You: Add a 50-day SMA trend filter

Agent: → modify_strategy
       → run_backtest

       With trend filter:
       • Total Return: 28.1% (slightly lower)
       • Max Drawdown: 9.8% (much better!)
       • Sharpe Ratio: 1.12 (improved)

       The filter reduced trades from 23 to 14 but dramatically
       improved risk-adjusted returns. This is a better strategy
       for most investors.

You: Save this as "macd_trend_filtered"

Agent: → save_strategy

       ✅ Saved! You can load it anytime with "load macd_trend_filtered"
```

---

## Getting Started

```bash
# Clone and install
git clone https://github.com/dgiliver/bonito
cd bonito
pip install -e ".[dev]"

# Download market data
bonito ingest SPY --start 2020-01-01

# Start the API server
bonito-api

# Or use CLI directly
bonito chat
```

**Docker:**
```bash
docker-compose up
# Web UI at http://localhost:3000
# API at http://localhost:8000
```

---

## The Vision

**Today:** AI helps you create and test trading strategies in conversation.

**Tomorrow:** AI manages your entire quant workflow — from idea generation to paper trading to live execution — with human oversight at key decision points.

**We're building the quant platform that should have existed the moment LLMs got good at tool use.**

---

## Contact

**David Giliver**
[GitHub](https://github.com/dgiliver) • [Email]

---

*Built with Claude, NumPy, and a vision for democratizing quantitative trading.*
