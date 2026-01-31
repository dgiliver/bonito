---
name: explore-ui
description: Start servers and explore the UI in browser. Use to visually verify features and find bugs.
allowed-tools: Bash, Read, mcp__Claude_in_Chrome__*
---

# Explore UI Skill

Launches the Bonito trading platform and explores it in Chrome.

## Quick Start

```bash
/explore-ui
```

## What It Does

1. Starts the API server (port 8000)
2. Starts the frontend dev server (port 3000)
3. Opens Chrome to http://localhost:3000
4. Explores the UI interactively

## Manual Steps

### Start Servers
```bash
# Terminal 1: API
cd /Users/dgiliver/personal_projects/bonito && make api

# Terminal 2: Frontend
cd /Users/dgiliver/personal_projects/bonito/web && npm run dev
```

### Navigate
Use Chrome MCP tools:
- `navigate` to http://localhost:3000
- `read_page` to see UI elements
- `find` to locate specific components
- `computer` for clicks and interactions
- `read_console_messages` for errors

## Exploration Checklist

### Chart Component
- [ ] Symbol dropdown works
- [ ] Interval buttons change timeframe
- [ ] Range buttons load correct data
- [ ] Crosshair shows OHLCV values
- [ ] Trade markers appear on chart

### Backtest Flow
- [ ] Can configure strategy
- [ ] Run backtest completes
- [ ] Metrics display correctly
- [ ] Trade log shows all trades
- [ ] Clicking trade highlights on chart

### Short Selling (F020)
- [ ] Short trades show "SHORT" label
- [ ] Red markers for short entries
- [ ] Trade log shows position_side
- [ ] P&L correct for shorts

## Common Issues

**Port already in use**: Kill existing process
```bash
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9
```

**API not responding**: Check for errors
```bash
curl http://localhost:8000/health
```

**Frontend errors**: Check console
Use `read_console_messages` tool
