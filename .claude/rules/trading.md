# Trading Domain Rules

## Position Handling

### Long Positions
- Entry: BUY at open * (1 + slippage)
- Exit: SELL at open * (1 - slippage)
- P&L: (exit_price - entry_price) * quantity
- Stop loss: triggers when price FALLS below stop

### Short Positions
- Entry: SELL at open * (1 - slippage)
- Exit: BUY at open * (1 + slippage)
- P&L: (entry_price - exit_price) * quantity
- Stop loss: triggers when price RISES above stop

## Signals
- Signals are computed on bar N-1
- Execution happens at open of bar N
- This prevents look-ahead bias

## Stop Loss Types
```python
# Fixed: set at entry, never moves
stop = entry_price * (1 - percent)

# Trailing: follows price, protects gains
stop = highest_price * (1 - percent)  # For longs
stop = lowest_price * (1 + percent)   # For shorts

# Breakeven: moves to entry after profit threshold
if profit_pct > trigger:
    stop = entry_price
```

## Metrics Interpretation
| Metric | Good | Warning |
|--------|------|---------|
| Sharpe | > 1.0 | < 0.5 |
| Max Drawdown | < 20% | > 30% |
| Win Rate | > 45% | < 35% |
| Profit Factor | > 1.2 | < 1.0 |
| Trades | > 30 | < 20 |

## Overfitting Signals
- Sharpe > 3.0 (too good)
- Exact round numbers (period=50)
- Too many indicators (>4)
- Results don't match out-of-sample
