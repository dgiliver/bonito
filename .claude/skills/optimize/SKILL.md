---
name: optimize
description: Optimize strategy parameters via grid search. Use to find best indicator periods, stop losses, etc.
allowed-tools: Bash, Read
---

# Parameter Optimization Skill

Optimize trading strategy parameters using grid search to find the best combinations.

## Quick Optimize via API

Start the API server if not running:
```bash
make api &
```

The agent has an `optimize_parameters` tool that runs grid search automatically.

## Via CLI Chat

```bash
make chat
```

Then: "Optimize my RSI strategy - try RSI periods 10, 14, 20 and stop losses 3%, 5%, 8%"

## Via Agent Tool Directly

The `optimize_parameters` tool accepts:
- `strategy_name`: Name of strategy in session
- `parameter_grid`: Parameters to test, e.g., `{"rsi_period": [10, 14, 20], "stop_loss_pct": [0.03, 0.05, 0.08]}`
- `symbol`: Symbol to test on (default: SPY)
- `target_metric`: What to optimize - `sharpe_ratio`, `total_return`, or `profit_factor`

## Batch Backtest (Multi-Symbol)

The `batch_backtest` tool tests a strategy across multiple symbols:
- `strategy_name`: Name of strategy
- `symbols`: List of symbols, e.g., `["SPY", "QQQ", "IWM"]`

## Limits

- Maximum 50 parameter combinations per optimization run
- Grid size = product of all value list lengths
- Example: 3 x 3 x 3 = 27 combinations (OK), 10 x 10 = 100 (too many)

## Interpreting Results

Results are ranked by target metric. Look for:
- **Consistency**: Do nearby parameter values perform similarly? (good sign)
- **Sensitivity**: Does small parameter change drastically change results? (overfitting risk)
- **Trade count**: Enough trades for statistical significance (>30)?
