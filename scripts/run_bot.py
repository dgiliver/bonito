"""Persistent bot runner for Bonito trading strategies.

Loads a strategy JSON, connects to Alpaca, and runs the trading loop.
Designed to run as a systemd service on EC2.

Usage:
    python scripts/run_bot.py --strategy research_output/2026-03-24/best_strategy.json
    python scripts/run_bot.py --strategy strategies/my_strat.json --mode live
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bonito.trading.alpaca_broker import AlpacaBroker  # noqa: E402
from bonito.trading.bot import TradingBot  # noqa: E402
from bonito.trading.models import BotConfig, ExecutionModel, TradingConfig  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bonito_bot.log"),
    ],
)
logger = logging.getLogger("bonito.runner")


def load_strategy(path: str) -> dict:
    """Load strategy JSON, handling wrapper format."""
    with open(path) as f:
        data = json.load(f)
    # Handle wrapper format: {"id": ..., "config": {...}}
    if "config" in data and "indicators" not in data:
        return data["config"]
    return data


def get_credentials(mode: str) -> tuple[str, str]:
    """Get Alpaca credentials from environment.

    Credentials come from environment variables, which are set by:
    - Local: sourcing .env.alpaca.bonito
    - EC2: AWS Secrets Manager via start_bot.sh

    Never hardcode credentials.
    """
    if mode == "paper":
        key = os.environ.get("ALPACA_PAPER_API_KEY")
        secret = os.environ.get("ALPACA_PAPER_API_SECRET")
    else:
        key = os.environ.get("ALPACA_LIVE_API_KEY")
        secret = os.environ.get("ALPACA_LIVE_API_SECRET")

    if not key or not secret:
        logger.error(
            f"Missing Alpaca {mode} credentials. "
            "Set ALPACA_PAPER_API_KEY/SECRET or ALPACA_LIVE_API_KEY/SECRET."
        )
        sys.exit(1)

    return key, secret


async def main(strategy_path: str, mode: str = "paper") -> None:
    """Run the trading bot."""
    # Load strategy
    strategy = load_strategy(strategy_path)
    strategy_name = strategy.get("name", Path(strategy_path).stem)

    logger.info(f"Strategy: {strategy_name}")
    logger.info(f"Mode: {mode}")
    logger.info(f"Symbols: {strategy.get('symbols', ['SPY'])}")
    logger.info(f"Indicators: {len(strategy.get('indicators', []))}")

    # Get credentials
    api_key, api_secret = get_credentials(mode)

    # Create bot
    bot_config = BotConfig(
        id=f"bonito-{strategy_name}-{mode}",
        name=f"{strategy_name} ({mode})",
        strategy_name=strategy_name,
        strategy_config=strategy,
        trading_config=TradingConfig(
            execution_model=ExecutionModel.CONTINUOUS,
            mode=mode,
            order_type="market",
        ),
        created_at=datetime.now(UTC),
        created_by="run_bot.py",
    )

    broker = AlpacaBroker(api_key=api_key, secret_key=api_secret, mode=mode)
    bot = TradingBot(config=bot_config, broker=broker)

    # Handle graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal(sig: int, _frame: object) -> None:
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Start bot
    await bot.start()
    logger.info("Bot is running. Press Ctrl+C to stop.")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Graceful shutdown
    logger.info("Stopping bot...")
    await bot.stop(close_positions=False)
    logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Bonito trading bot")
    parser.add_argument(
        "--strategy",
        required=True,
        help="Path to strategy JSON file",
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.strategy, args.mode))
