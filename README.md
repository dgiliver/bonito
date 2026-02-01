# 🐟 Bonito

> AI-native algorithmic trading platform — backtesting and deployment built for agents, not scripts.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What Makes Bonito Different

Traditional quant platforms assume you write code, run slow backtests, and manually iterate. **Bonito inverts this:**

| Traditional | Bonito |
|-------------|--------|
| Human writes strategy code | Agent generates strategy configs |
| Run backtest, wait, analyze | Sub-second backtests, instant feedback |
| Manual parameter tuning | Agent iterates and refines |
| Code review for safety | JSON configs = no arbitrary code execution |

**The human becomes a supervisor, not an implementer.**

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourusername/bonito.git
cd bonito
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Set up your API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# Ingest market data
bonito ingest SPY AAPL QQQ --start 2020-01-01

# Start the web UI
make api &  # Backend on :8000
make web    # Frontend on :3000
```

## Example Session

```
You: Create a momentum strategy for SPY with trailing stops

Agent: I'll create a momentum strategy using RSI and moving averages
       with ATR-based trailing stops...

🔧 Running backtest...
✅ Completed in 0.3s

Backtest Results: spy_momentum_v2
═══════════════════════════════════
Period: 2020-01-01 to 2024-01-01
Initial: $100,000 → Final: $156,420

PERFORMANCE
  Total Return: 56.42%
  Sharpe Ratio: 1.48
  Max Drawdown: 9.2%
  Win Rate: 62%

The Sharpe looks good but I can improve the drawdown.
Let me add a volatility filter...

[Agent iterates 2 more times, improves Sharpe to 1.65]

Would you like me to explain the strategy logic?
```

## Key Features

### ✅ Completed
- **Vectorized Backtesting** — Sub-second execution via NumPy
- **60+ Indicators** — pandas-ta integration (RSI, MACD, ADX, VWAP, etc.)
- **Long/Short Trading** — Full short selling support
- **Trailing Stops** — Percent and ATR-based
- **Strategy DSL** — JSON configs, not arbitrary code
- **Plugin System** — Custom Python strategies when needed
- **Multi-panel Charts** — RSI, MACD, Stochastic with crosshair sync
- **AI Agent** — Claude-powered strategy generation and analysis
- **Trade Markers** — Visual entry/exit points with P&L details

### 🚧 Coming Soon
- Authentication (Supabase)
- Real-time data (WebSocket)
- Drawing tools (trendlines, annotations)
- Paper trading (Alpaca integration)

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         USER (CLI/Web)                        │
└──────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                      BONITO AGENT (LLM)                       │
│   • Generates strategy configurations                         │
│   • Calls tools to test strategies                            │
│   • Analyzes results and iterates                             │
│   • Controls chart visualization                              │
└──────────────────────────────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
│  Backtest Tool   │  │  Data Tool   │  │   Chart Tool     │
│  • run()         │  │  • get_bars()│  │  • add_indicator │
│  • analyze()     │  │  • ingest()  │  │  • spotlight     │
└──────────────────┘  └──────────────┘  └──────────────────┘
              │                │
              ▼                ▼
┌──────────────────────────────────────────────────────────────┐
│                      CORE ENGINE (NumPy)                      │
│   • Vectorized backtest simulation                            │
│   • 60+ technical indicators                                  │
│   • Strategy DSL evaluation                                   │
└──────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────┐
│                    DATA LAYER (DuckDB)                        │
│   • OHLCV bar storage                                         │
│   • Fast analytical queries                                   │
└──────────────────────────────────────────────────────────────┘
```

## Strategy DSL

Strategies are JSON configs, not Python code:

```json
{
  "name": "ema_cross_rsi_filter",
  "symbols": ["SPY"],
  "timeframe": "1d",
  "indicators": [
    {"type": "ema", "name": "fast_ema", "params": {"period": 12}},
    {"type": "ema", "name": "slow_ema", "params": {"period": 26}},
    {"type": "rsi", "name": "rsi", "params": {"period": 14}}
  ],
  "entry_rules": [{
    "side": "long",
    "conditions": [
      {"left": "fast_ema", "comparison": "crosses_above", "right": "slow_ema"},
      {"left": "rsi", "comparison": "lt", "right": 70}
    ]
  }],
  "exit_rules": [{
    "conditions": [
      {"left": "fast_ema", "comparison": "crosses_below", "right": "slow_ema"}
    ]
  }],
  "stop_loss": {"type": "trailing_percent", "value": 0.05}
}
```

**Why JSON?**
- ✅ LLMs generate valid configs reliably
- ✅ Easy validation (Pydantic)
- ✅ No security sandbox needed
- ✅ Deterministic execution
- ✅ Full auditability

## Development

```bash
make api          # Start API server (port 8000)
make web          # Start frontend (port 3000)
make chat         # CLI agent chat
make test         # Run all tests
make lint         # Run ruff linter
make docker-up    # Start with Docker
```

## Project Structure

```
bonito/
├── src/bonito/
│   ├── agent/        # LLM agent and orchestrator
│   ├── backtest/     # Vectorized engine, indicators, DSL
│   ├── data/         # DuckDB storage
│   ├── tools/        # Agent tools
│   └── api/          # FastAPI server
├── web/              # Next.js 16 frontend
├── tests/            # pytest suite
├── strategies/       # Example strategy configs
└── docs/             # Architecture, roadmap
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design and decisions
- [Strategy DSL](docs/STRATEGY_DSL.md) — Complete DSL reference
- [API Reference](docs/API.md) — REST endpoints
- [Launch Plan](docs/LAUNCH_PLAN.md) — Go-to-market strategy

## License

MIT
