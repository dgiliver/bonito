---
name: bot-status
description: Check trading bot status, positions, P&L, and recent trades.
allowed-tools: Read, Bash
---

# Bot Status Skill

View detailed status of trading bots.

## Usage
```bash
/bot-status                    # List all bots
/bot-status {bot_id}           # Specific bot details
/bot-status --all              # All bots with full details
```

## Commands

### List All Bots
```bash
curl http://localhost:8000/api/trading/bots
```

### Get Specific Bot
```bash
curl http://localhost:8000/api/trading/bots/{bot_id}
```

### Get Positions
```bash
curl http://localhost:8000/api/trading/bots/{bot_id}/positions
```

### Get Trade History
```bash
curl http://localhost:8000/api/trading/bots/{bot_id}/trades?limit=20
```

### Get Equity Curve
```bash
curl http://localhost:8000/api/trading/bots/{bot_id}/equity
```

## Bot Actions

### Pause Bot
```bash
curl -X POST http://localhost:8000/api/trading/bots/{bot_id}/pause
```

### Resume Bot
```bash
curl -X POST http://localhost:8000/api/trading/bots/{bot_id}/resume
```

### Stop Bot
```bash
curl -X POST http://localhost:8000/api/trading/bots/{bot_id}/stop
curl -X POST http://localhost:8000/api/trading/bots/{bot_id}/stop?close_positions=true
```

## Status Codes

| Status | Meaning |
|--------|---------|
| 🟢 running | Bot actively trading |
| 🟡 paused | Bot paused, positions held |
| ⚪ stopped | Bot stopped completely |
| 🔴 error | Bot encountered an error |
