---
name: backtest
description: Run a backtest and analyze results. Use when testing trading strategies.
allowed-tools: Bash, Read
---

# Backtest Skill

Run backtests and analyze trading strategy performance.

## Quick Backtest via API

Start the API server if not running:
```bash
make api &
```

Then run a backtest:
```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": {
      "name": "test_strategy",
      "symbols": ["SPY"],
      "timeframe": "1d",
      "indicators": [
        {"type": "sma", "name": "sma_20", "params": {"period": 20}},
        {"type": "rsi", "name": "rsi_14", "params": {"period": 14}}
      ],
      "entry_rules": [{
        "conditions": [
          {"left": "close", "comparison": "crosses_above", "right": "sma_20"},
          {"left": "rsi_14", "comparison": "lt", "right": 70}
        ]
      }],
      "exit_rules": [{
        "conditions": [
          {"left": "close", "comparison": "crosses_below", "right": "sma_20"}
        ]
      }],
      "position_size": {"type": "percent_equity", "value": 95}
    },
    "start_date": "2020-01-01",
    "end_date": "2024-01-01",
    "initial_capital": 100000
  }'
```

## CLI Backtest

Use the interactive agent:
```bash
make chat
```

Then: "Create a momentum strategy for SPY with RSI and moving averages"

## Key Metrics to Check

| Metric | Good | Excellent |
|--------|------|-----------|
| Sharpe Ratio | > 1.0 | > 1.5 |
| Max Drawdown | < 20% | < 10% |
| Win Rate | > 45% | > 55% |
| Profit Factor | > 1.2 | > 1.5 |

## Available Indicators

Built-in: SMA, EMA, RSI, MACD, ATR, Bollinger Bands, Stochastic

Extended (pandas-ta): ADX, VWAP, OBV, SuperTrend, Donchian, Keltner, Aroon, CCI, MFI, ROC

## Troubleshooting

**"No data found"**: Run `bonito ingest SPY --start 2020-01-01`
**"Invalid indicator"**: Check indicator name and params in orchestrator.py
