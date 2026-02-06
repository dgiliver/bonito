---
name: deploy-bot
description: Deploy a backtested strategy as a trading bot to Alpaca paper or live trading.
allowed-tools: Read, Grep, Bash
---

# Deploy Bot Skill

Deploy a validated strategy to paper or live trading.

## Usage
```bash
/deploy-bot "strategy_name"              # Deploy to paper trading
/deploy-bot "strategy_name" --paper      # Explicit paper trading
/deploy-bot "strategy_name" --live       # Live trading (requires extra confirmation)
```

## Pre-Deployment Checklist

1. **Verify Strategy Exists**
```bash
ls strategies/*.json | grep "strategy_name"
cat strategies/strategy_name.json
```

2. **Check Backtest Results**
```bash
# Run backtest to verify strategy works
bonito backtest run --strategy strategy_name --symbol SPY --start 2023-01-01
```

3. **Verify Alpaca Account Linked**
```bash
curl http://localhost:8000/api/trading/account
```

4. **Calculate Risk Score**
- Check position sizing
- Verify stop loss exists
- Check daily loss limits

## Deployment Flow

```
1. Load strategy config
2. Calculate risk score
3. If high/extreme risk → Show warnings, require acknowledgment
4. Create BotConfig
5. Deploy via API
6. Show bot status
```

## Post-Deployment

```bash
# Check bot is running
curl http://localhost:8000/api/trading/bots

# Monitor logs
tail -f logs/trading.log

# View positions
curl http://localhost:8000/api/trading/bots/{id}/positions
```
