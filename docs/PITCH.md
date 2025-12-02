# Quant Agent: AI-Native Algorithmic Trading Platform

## The Problem

**Existing quant platforms are stuck in 2010.**

| Platform | Pain Point |
|----------|------------|
| QuantConnect | Steep learning curve, C#/Python required |
| Backtrader | Complex API, no AI integration |
| TradingView | Limited backtesting, manual strategy building |
| Bloomberg Terminal | $24K/year, enterprise-only |

**The gap:** No platform lets you go from idea → tested strategy in natural language.

---

## The Solution

**Quant Agent** — an AI-native platform where you describe strategies in plain English and iterate in real-time.

```
You: "Create a momentum strategy using RSI with a trend filter"

Agent: Created strategy with RSI(14) + 200-day SMA filter.
       Backtest results: 20.3% return, 0.97 Sharpe, 8.25% max drawdown.

       The RSI < 35 threshold caught better pullback opportunities.
       Would you like me to test on different assets or adjust parameters?
```

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

**Time elapsed: ~2 minutes**
**Traditional approach: Hours of coding and manual iteration**

---

## Key Features

### 🧠 Natural Language Strategy Creation
No coding required. Describe what you want:
- "Buy when RSI is oversold and price is above the moving average"
- "Create an EMA crossover strategy with 12/26 periods"
- "Add a 3% stop loss to protect against drawdowns"

### 📊 Instant Backtesting
- Sub-second execution on years of data
- Full metrics: Sharpe, Sortino, drawdown, win rate
- Trade-by-trade analysis

### 🔄 Iterative Refinement
The AI doesn't just execute — it analyzes and suggests:
- "Win rate is low, consider tighter entry conditions"
- "High drawdown suggests adding a trend filter"
- "Try RSI 30/70 levels for cleaner signals"

### 📈 7 Built-in Indicators
SMA, EMA, RSI, MACD, ATR, Bollinger Bands, Stochastic

### 🛡️ Safe Strategy DSL
Strategies are defined in a constrained JSON format:
- No arbitrary code execution
- Full auditability
- Version controlled

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Natural Language                      │
│            "Create a momentum strategy..."               │
└─────────────────────────────┬───────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                    AI Agent (Claude)                     │
│         • Understands intent                            │
│         • Creates strategy JSON                         │
│         • Analyzes results                              │
│         • Suggests improvements                         │
└─────────────────────────────┬───────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Strategy │   │ Backtest │   │   Data   │
        │  Tools   │   │  Engine  │   │   Store  │
        └──────────┘   └──────────┘   └──────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                   Market Data (DuckDB)                   │
│              Yahoo Finance • 1-minute bars              │
└─────────────────────────────────────────────────────────┘
```

---

## Target Users

### 1. **Aspiring Quants**
- Want to learn algorithmic trading
- Don't have programming background
- Need guidance on strategy development

### 2. **Retail Traders**
- Currently use TradingView/manual trading
- Want to systematize their approach
- Need proper backtesting

### 3. **Small Hedge Funds**
- Need rapid strategy prototyping
- Want to reduce developer dependency
- Value iteration speed over infrastructure

---

## Competitive Advantage

| Feature | Quant Agent | QuantConnect | Backtrader |
|---------|-------------|--------------|------------|
| Natural language | ✅ | ❌ | ❌ |
| No coding required | ✅ | ❌ | ❌ |
| AI iteration | ✅ | ❌ | ❌ |
| Instant feedback | ✅ | Minutes | Minutes |
| Free tier | ✅ | Limited | ✅ |
| Strategy explanation | ✅ | ❌ | ❌ |

**Unique value:** The AI doesn't just execute — it **teaches** and **iterates**.

---

## Roadmap

### ✅ MVP (Complete)
- [x] Data ingestion (Yahoo Finance)
- [x] Vectorized backtesting engine
- [x] 7 technical indicators
- [x] Strategy DSL (JSON-based)
- [x] AI agent with tool calling
- [x] CLI interface
- [x] Strategy save/load
- [x] Multi-timeframe support (1m-1d)
- [x] FastAPI REST API
- [x] SSE streaming chat endpoint
- [x] Docker containerization

### 🔄 Phase 2 (Next)
- [ ] Web UI (Next.js)
- [ ] Strategy comparison tool
- [ ] Custom formula indicators
- [ ] Authentication

### 🔮 Phase 3 (Future)
- [ ] Paper trading (Alpaca integration)
- [ ] Multi-asset portfolios
- [ ] Walk-forward optimization
- [ ] Strategy marketplace

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12 |
| AI | Claude Sonnet (Anthropic) |
| Data Storage | DuckDB |
| Data Source | Yahoo Finance |
| Backtesting | NumPy (vectorized) |
| CLI | Typer + Rich |
| Validation | Pydantic |

---

## Getting Started

```bash
# Install
pip install -e ".[dev]"

# Download data
quant ingest SPY --start 2020-01-01

# Start chatting
quant chat

# Or run a strategy directly
quant backtest examples/ema_cross_strategy.json
```

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
       overbought entries. The win rate is moderate but winners
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
```

---

## Contact

[Your Name]
[Email]
[GitHub]

---

*Built with Claude Sonnet, NumPy, and a vision for democratizing quantitative trading.*
