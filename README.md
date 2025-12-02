# Quant Agent

> AI-native algorithmic trading platform — backtesting and deployment built for agents, not scripts.

## Overview

Traditional quant platforms (QuantConnect, Tradestation, etc.) were built in a pre-AI paradigm. They assume you write deterministic strategies, run slow backtests, and manually iterate.

**Quant Agent** inverts this:

- **Agent-first**: An AI agent generates, tests, and refines strategies
- **Tool-based**: Modular MCP-style tools for backtesting, data, and analysis
- **Fast iteration**: Sub-second backtests for rapid experimentation
- **Observable**: Every decision is traced and explainable

## Quick Start

```bash
# Clone the repo
cd quant-agent

# Install dependencies (using uv recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Set up your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Ingest some data
quant ingest SPY AAPL QQQ --start 2020-01-01 --end 2024-12-01

# Start chatting with the agent
quant chat
```

## Example Session

```
You: Create a momentum strategy for SPY

Agent: I'll create a momentum strategy using RSI and moving averages...

🔧 Running validate_strategy...
✅ validate_strategy completed

🔧 Running backtest_run...
✅ backtest_run completed

Here are the results:

Backtest Results: spy_momentum_v1
==================================================
Period: 2020-01-01 to 2024-01-01
Initial Capital: $100,000.00
Final Capital: $142,350.00

RETURNS
  Total Return: 42.35%
  Annualized Return: 9.25%

RISK
  Sharpe Ratio: 1.15
  Max Drawdown: 12.3%

The Sharpe ratio is decent but I notice the drawdown is a bit high.
Let me add an ATR-based volatility filter to reduce entries during
choppy markets...

🔧 Running backtest_run...
✅ backtest_run completed

After adding the volatility filter:
- Sharpe improved to 1.42
- Max drawdown reduced to 8.7%
- Fewer trades but higher win rate

Would you like me to explain the strategy logic or make further refinements?
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER (CLI/API)                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      QUANT AGENT (LLM)                          │
│  • Generates strategy configurations                            │
│  • Calls tools to test strategies                               │
│  • Analyzes results and iterates                                │
└─────────────────────────────────────────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Backtest Tool  │  │   Data Tool     │  │ Validation Tool │
│  • run()        │  │  • get_bars()   │  │  • validate()   │
│  • explain()    │  │  • list()       │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
              │                 │
              ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CORE ENGINE                             │
│  • Vectorized backtest simulation                               │
│  • Technical indicators (SMA, RSI, MACD, etc.)                  │
│  • Portfolio state management                                   │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER (DuckDB)                        │
│  • OHLCV bar storage                                            │
│  • Fast analytical queries                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Strategy DSL

Instead of arbitrary Python code, strategies are defined as structured configurations:

```json
{
  "name": "ema_cross_rsi_filter",
  "description": "EMA crossover with RSI filter",
  "symbols": ["SPY"],
  "timeframe": "1d",
  "indicators": [
    {"type": "ema", "name": "fast_ema", "params": {"period": 12}},
    {"type": "ema", "name": "slow_ema", "params": {"period": 26}},
    {"type": "rsi", "name": "rsi", "params": {"period": 14}}
  ],
  "entry_rules": [
    {
      "conditions": [
        {"left": "fast_ema", "comparison": "crosses_above", "right": "slow_ema"},
        {"left": "rsi", "comparison": "<", "right": 70}
      ],
      "logic": "AND"
    }
  ],
  "exit_rules": [
    {
      "conditions": [
        {"left": "fast_ema", "comparison": "crosses_below", "right": "slow_ema"}
      ],
      "logic": "AND"
    }
  ],
  "position_size": {"type": "percent_equity", "value": 10},
  "stop_loss": {"type": "percent", "value": 0.05}
}
```

This approach:
- ✅ LLMs can reliably generate valid configs
- ✅ Easy to validate
- ✅ No security sandbox needed
- ✅ Deterministic execution
- ✅ Easy to audit and explain

## Project Structure

```
quant-agent/
├── src/quant_agent/
│   ├── agent/           # LLM agent and prompts
│   │   ├── core.py      # Agent implementation
│   │   └── prompts.py   # System and task prompts
│   ├── backtest/        # Backtesting engine
│   │   ├── engine.py    # Vectorized backtest
│   │   ├── indicators.py# Technical indicators
│   │   ├── strategy.py  # Strategy DSL models
│   │   └── models.py    # Result models
│   ├── data/            # Data layer
│   │   ├── store.py     # DuckDB storage
│   │   └── models.py    # Data models
│   ├── tools/           # Agent tools
│   │   ├── base.py      # Tool protocol
│   │   ├── backtest_tools.py
│   │   ├── data_tools.py
│   │   └── strategy_tools.py
│   ├── cli.py           # Command-line interface
│   └── config.py        # Configuration
├── tests/               # Test suite
├── examples/            # Example strategies
├── docs/                # Documentation
│   ├── ARCHITECTURE.md
│   └── MVP_ROADMAP.md
└── data/                # Local data storage
```

## Development

```bash
# Run tests
pytest

# Run linting
ruff check src/

# Type checking
mypy src/
```

## Roadmap

See [docs/MVP_ROADMAP.md](docs/MVP_ROADMAP.md) for the detailed development plan.

**MVP (Weeks 1-6)**
- [x] Project structure
- [ ] Data layer (DuckDB + Yahoo Finance)
- [ ] Backtest engine
- [ ] Tool layer
- [ ] Agent integration
- [ ] CLI interface

**Post-MVP**
- [ ] Paper trading (Alpaca)
- [ ] Web UI
- [ ] Walk-forward optimization
- [ ] Multi-asset portfolios

## License

MIT
