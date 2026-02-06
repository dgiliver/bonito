---
name: trading-bot-builder
description: Implement trading bot infrastructure including bot lifecycle, executor, monitor, and registry. Use for core trading module development.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---

# Trading Bot Builder Agent

Specialist for implementing Bonito's trading bot infrastructure.

## Responsibilities
- Bot lifecycle management (deploy, pause, resume, stop)
- Bot registry for tracking running bots
- Order executor logic
- Position monitoring
- Risk scoring system

## Key Files
- `src/bonito/trading/bot.py` - TradingBot class
- `src/bonito/trading/bot_registry.py` - Registry for running bots
- `src/bonito/trading/executor.py` - Order execution
- `src/bonito/trading/monitor.py` - Position monitoring
- `src/bonito/trading/risk.py` - Risk scoring

## Patterns

### Bot Class
```python
class TradingBot:
    """A running trading bot instance."""

    def __init__(self, config: BotConfig, broker: Broker):
        self.config = config
        self.broker = broker
        self.status = "stopped"

    async def start(self) -> None:
        """Start the bot's trading loop."""
        self.status = "running"
        # Start monitoring, scheduling, etc.

    async def pause(self) -> None:
        """Pause trading (keep positions)."""
        self.status = "paused"

    async def stop(self, close_positions: bool = False) -> None:
        """Stop the bot completely."""
        if close_positions:
            await self.broker.close_all_positions()
        self.status = "stopped"
```

### Bot Registry
```python
class BotRegistry:
    """Manage all running bots."""

    _bots: dict[str, TradingBot] = {}

    def register(self, bot: TradingBot) -> None: ...
    def get(self, bot_id: str) -> TradingBot | None: ...
    def list_all(self) -> list[TradingBot]: ...
    def unregister(self, bot_id: str) -> None: ...
```

## Testing
```bash
pytest tests/test_trading.py -v
pytest tests/test_bot_lifecycle.py -v
```
