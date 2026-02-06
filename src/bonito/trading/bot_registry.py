"""Registry for managing running trading bots."""

import logging
from collections.abc import Callable

from .bot import TradingBot

logger = logging.getLogger(__name__)


class BotRegistry:
    """Manage all running trading bots."""

    _instance: "BotRegistry | None" = None

    def __new__(cls) -> "BotRegistry":
        """Singleton pattern for global bot registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._bots = {}
            cls._instance._listeners = []
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def register(self, bot: TradingBot) -> None:
        """Register a new bot."""
        if bot.id in self._bots:
            raise ValueError(f"Bot {bot.id} is already registered")
        self._bots[bot.id] = bot
        self._notify_listeners("registered", bot)
        logger.info(f"Bot {bot.id} registered")

    def unregister(self, bot_id: str) -> TradingBot | None:
        """Unregister a bot and return it."""
        bot = self._bots.pop(bot_id, None)
        if bot:
            self._notify_listeners("unregistered", bot)
            logger.info(f"Bot {bot_id} unregistered")
        return bot

    def get(self, bot_id: str) -> TradingBot | None:
        """Get a bot by ID."""
        return self._bots.get(bot_id)

    def list_all(self) -> list[TradingBot]:
        """List all registered bots."""
        return list(self._bots.values())

    def list_by_status(self, status: str) -> list[TradingBot]:
        """List bots filtered by status."""
        return [b for b in self._bots.values() if b.status == status]

    def add_listener(self, callback: Callable[[str, TradingBot], None]) -> None:
        """Add a listener for registry events."""
        self._listeners.append(callback)

    def _notify_listeners(self, event: str, bot: TradingBot) -> None:
        """Notify all listeners of an event."""
        for callback in self._listeners:
            try:
                callback(event, bot)
            except Exception as e:
                logger.error(f"Listener error: {e}", exc_info=True)
