"""Trading bot that executes strategies via a broker."""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from typing import Literal

import numpy as np

from bonito.backtest.indicators import compute_indicators
from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData

from . import signals
from .broker import Broker
from .executor import OrderExecutor
from .models import BotConfig, DeployedBot, Order, Position
from .monitor import PositionMonitor

logger = logging.getLogger(__name__)


class TradingBot:
    """A running trading bot instance."""

    def __init__(self, config: BotConfig, broker: Broker):
        self.config = config
        self.broker = broker
        self._status: Literal["stopped", "running", "paused", "error"] = "stopped"
        self._task: asyncio.Task | None = None
        self._positions: list[Position] = []
        self._orders: list[Order] = []
        self._start_time: datetime | None = None
        self._total_trades: int = 0
        self._realized_pnl: float = 0.0

        # Trailing stop tracking: symbol -> highest price since entry (longs) or lowest (shorts)
        self._trailing_highs: dict[str, float] = {}

        # Initialize executor and monitor
        self._executor = OrderExecutor(broker, config.trading_config)
        self._monitor = PositionMonitor(broker)

        # Parse strategy config
        self._strategy = StrategyConfig.model_validate(config.strategy_config)

        # Cache for recent market data
        self._last_data_fetch: datetime | None = None
        self._cached_data: BarData | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def id(self) -> str:
        return self.config.id

    async def start(self) -> None:
        """Start the bot's trading loop."""
        if self._status == "running":
            raise RuntimeError("Bot is already running")

        await self.broker.connect()
        self._status = "running"
        self._start_time = datetime.utcnow()
        logger.info(f"Bot {self.id} started")

        # Start the main loop based on execution model
        self._task = asyncio.create_task(self._run_loop())

    async def pause(self) -> None:
        """Pause trading (keep positions, stop new trades)."""
        if self._status != "running":
            raise RuntimeError("Can only pause a running bot")
        self._status = "paused"
        logger.info(f"Bot {self.id} paused")

    async def resume(self) -> None:
        """Resume a paused bot."""
        if self._status != "paused":
            raise RuntimeError("Can only resume a paused bot")
        self._status = "running"
        logger.info(f"Bot {self.id} resumed")

    async def stop(self, close_positions: bool = False) -> None:
        """Stop the bot completely."""
        if close_positions and self._positions:
            await self.broker.close_all_positions()

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        await self.broker.disconnect()
        self._status = "stopped"
        logger.info(f"Bot {self.id} stopped")

    async def _run_loop(self) -> None:
        """Main trading loop - executes strategy based on execution model."""
        try:
            # Determine check interval based on timeframe
            check_interval = self._get_check_interval()

            while self._status in ("running", "paused"):
                if self._status == "paused":
                    await asyncio.sleep(1)
                    continue

                # Check strategy signals and execute trades
                await self._check_and_execute()

                # Sleep until next check
                await asyncio.sleep(check_interval)
        except asyncio.CancelledError:
            logger.info(f"Bot {self.id} loop cancelled")
            raise
        except Exception as e:
            self._status = "error"
            logger.error(f"Bot {self.id} error: {e}", exc_info=True)

    def _get_check_interval(self) -> float:
        """Get check interval in seconds based on strategy timeframe.

        Returns:
            Seconds to wait between checks
        """
        # Map timeframe to check interval
        # For production, check less frequently than the bar period
        interval_map = {
            "1m": 30,  # Check every 30 seconds for 1-minute bars
            "5m": 60,  # Check every minute for 5-minute bars
            "15m": 180,  # Check every 3 minutes for 15-minute bars
            "1h": 600,  # Check every 10 minutes for hourly bars
            "4h": 1800,  # Check every 30 minutes for 4-hour bars
            "1d": 3600,  # Check every hour for daily bars
        }
        return interval_map.get(self._strategy.timeframe, 60)

    async def _check_and_execute(self) -> None:
        """Check strategy signals and execute trades.

        This is the core trading loop - evaluates strategy conditions against
        current market data and generates trade signals.
        """
        try:
            # Fetch recent market data
            data = await self._fetch_recent_data()
            if data is None or len(data) < 2:
                logger.debug(f"Insufficient data for bot {self.id}, skipping execution")
                return

            # Refresh positions from broker
            self._positions = await self._monitor.refresh_positions()

            # Calculate indicators
            indicators = compute_indicators(data, self._strategy.indicators)

            # Get the latest indicator values (last bar)
            latest_idx = len(data) - 1

            # Check if we have an open position for this symbol
            symbol = self._strategy.symbols[0]  # MVP: single symbol
            existing_position = next((p for p in self._positions if p.symbol == symbol), None)

            if existing_position:
                # We have an open position - check exit conditions
                await self._check_exit_conditions(existing_position, indicators, latest_idx, data)
            else:
                # No position - check entry conditions
                await self._check_entry_conditions(indicators, latest_idx, data)

        except Exception as e:
            logger.error(f"Error in bot {self.id} execution: {e}", exc_info=True)

    async def _fetch_recent_data(self) -> BarData | None:
        """Fetch recent market data from Alpaca.

        Gets enough bars to calculate all indicators. For example, if the strategy
        uses SMA(200), we need at least 200 bars.

        Returns:
            BarData with recent bars, or None if fetch failed
        """
        try:
            # Import Alpaca data client here to avoid circular imports
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            # Determine how many bars we need based on indicator requirements
            max_period = self._get_max_indicator_period()
            # Fetch extra bars as buffer
            lookback_bars = max(max_period * 2, 300)

            # Map timeframe
            timeframe_map = {
                "1m": TimeFrame.Minute,
                "5m": TimeFrame(5, TimeFrameUnit.Minute),
                "15m": TimeFrame(15, TimeFrameUnit.Minute),
                "1h": TimeFrame.Hour,
                "4h": TimeFrame(4, TimeFrameUnit.Hour),
                "1d": TimeFrame.Day,
            }
            alpaca_timeframe = timeframe_map.get(self._strategy.timeframe, TimeFrame.Day)

            # Calculate lookback time
            # For daily bars, lookback in days; for intraday, use a different approach
            if self._strategy.timeframe == "1d":
                start = datetime.now() - timedelta(days=lookback_bars)
            else:
                # For intraday, be more conservative
                start = datetime.now() - timedelta(days=max(lookback_bars // 10, 30))

            symbol = self._strategy.symbols[0]  # MVP: single symbol

            # Get API credentials from broker (assuming AlpacaBroker)
            if not hasattr(self.broker, "api_key") or not hasattr(self.broker, "secret_key"):
                logger.error("Broker does not have Alpaca credentials")
                return None

            # Create data client
            data_client = StockHistoricalDataClient(
                self.broker.api_key,  # type: ignore
                self.broker.secret_key,  # type: ignore
            )

            # Fetch bars
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_timeframe,
                start=start,
            )

            bars_response = data_client.get_stock_bars(request)

            if symbol not in bars_response.data:
                logger.warning(f"No data returned for {symbol}")
                return None

            bars = bars_response.data[symbol]

            if not bars:
                logger.warning(f"Empty bars for {symbol}")
                return None

            # Convert to BarData
            bar_data = BarData(
                symbol=symbol,
                timeframe=self._strategy.timeframe,
                timestamps=[bar.timestamp for bar in bars],
                opens=[float(bar.open) for bar in bars],
                highs=[float(bar.high) for bar in bars],
                lows=[float(bar.low) for bar in bars],
                closes=[float(bar.close) for bar in bars],
                volumes=[float(bar.volume) for bar in bars],
            )

            logger.debug(
                f"Fetched {len(bar_data)} bars for {symbol} "
                f"from {bar_data.timestamps[0]} to {bar_data.timestamps[-1]}"
            )

            self._last_data_fetch = datetime.now()
            self._cached_data = bar_data
            return bar_data

        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}", exc_info=True)
            return None

    def _get_max_indicator_period(self) -> int:
        """Get the maximum period required by any indicator in the strategy.

        Returns:
            Maximum period needed, defaults to 200 if can't determine
        """
        max_period = 50  # Reasonable default

        for indicator in self._strategy.indicators:
            params = indicator.params
            # Check common period parameter names
            period = params.get("period") or params.get("length") or params.get("timeperiod")
            if period:
                max_period = max(max_period, int(period))

            # Check for multi-period indicators like MACD
            if indicator.type == "macd":
                slow = params.get("slow_period", 26)
                max_period = max(max_period, slow)

        return max_period

    async def _check_entry_conditions(
        self,
        indicators: dict[str, np.ndarray],
        latest_idx: int,
        data: BarData,
    ) -> None:
        """Check if entry conditions are met and execute entry if so.

        Args:
            indicators: Computed indicators
            latest_idx: Index of the latest bar
            data: Market data
        """
        # Check each entry rule
        for rule in self._strategy.entry_rules:
            if self._evaluate_rule_for_bar(rule, indicators, latest_idx):
                # Entry signal detected
                side = rule.side
                symbol = self._strategy.symbols[0]

                # Calculate position size
                account = await self.broker.get_account()
                current_equity = account.equity

                if self._strategy.position_size.type.value == "percent_equity":
                    pct = min(self._strategy.position_size.value, 99.5) / 100
                    position_value = current_equity * pct
                elif self._strategy.position_size.type.value == "fixed_value":
                    position_value = self._strategy.position_size.value
                else:  # fixed_quantity
                    # For fixed quantity, value IS the quantity
                    quantity = self._strategy.position_size.value
                    await self._executor.execute_signal(
                        symbol=symbol,
                        side="buy" if side == "long" else "sell",
                        quantity=quantity,
                        reason=f"Entry signal: {side} (rule matched)",
                    )
                    self._total_trades += 1
                    logger.info(
                        f"Bot {self.id}: Entered {side} position in {symbol} with {quantity} shares"
                    )
                    return

                # Convert position value to quantity based on current price
                current_price = data.closes[latest_idx]
                quantity = position_value / current_price

                # Check if we have enough buying power
                if position_value <= current_equity:
                    await self._executor.execute_signal(
                        symbol=symbol,
                        side="buy" if side == "long" else "sell",
                        quantity=quantity,
                        reason=f"Entry signal: {side} (rule matched)",
                    )
                    self._total_trades += 1
                    logger.info(
                        f"Bot {self.id}: Entered {side} position in {symbol} "
                        f"with {quantity:.2f} shares (${position_value:.2f})"
                    )
                else:
                    logger.warning(
                        f"Bot {self.id}: Insufficient equity for entry. "
                        f"Need ${position_value:.2f}, have ${current_equity:.2f}"
                    )

                # Only take one position at a time (for now)
                return

    async def _check_exit_conditions(
        self,
        position: Position,
        indicators: dict[str, np.ndarray],
        latest_idx: int,
        data: BarData,
    ) -> None:
        """Check if exit conditions are met and execute exit if so.

        Args:
            position: Current open position
            indicators: Computed indicators
            latest_idx: Index of the latest bar
            data: Market data
        """
        should_exit = False
        exit_reason = "signal"

        # Check exit rules from strategy
        for rule in self._strategy.exit_rules:
            if self._evaluate_rule_for_bar(rule, indicators, latest_idx):
                should_exit = True
                exit_reason = "Exit rule matched"
                break

        # Check stop loss
        if not should_exit and self._strategy.stop_loss:
            current_price = data.closes[latest_idx]
            if self._check_stop_loss(position, current_price, self._strategy.stop_loss):
                should_exit = True
                exit_reason = "Stop loss triggered"

        # Check take profit
        if not should_exit and self._strategy.take_profit:
            current_price = data.closes[latest_idx]
            if self._check_take_profit(position, current_price, self._strategy.take_profit):
                should_exit = True
                exit_reason = "Take profit triggered"

        # Execute exit if needed
        if should_exit:
            await self._executor.close_position(position.symbol)
            logger.info(f"Bot {self.id}: Exited position in {position.symbol}: {exit_reason}")

            # Clear trailing stop tracking
            self._trailing_highs.pop(position.symbol, None)

            # Record P&L
            pnl = position.unrealized_pnl
            self._monitor.record_trade_pnl(pnl)
            self._realized_pnl += pnl

    def _evaluate_rule_for_bar(
        self,
        rule,  # Rule
        indicators: dict[str, np.ndarray],
        bar_idx: int,
    ) -> bool:
        """Evaluate a single rule for the latest bar (delegates to signals module)."""
        return signals.evaluate_rule_for_bar(rule, indicators, bar_idx)

    def _evaluate_condition_for_bar(
        self,
        condition,  # RuleCondition
        indicators: dict[str, np.ndarray],
        bar_idx: int,
    ) -> bool:
        """Evaluate a single condition for a bar (delegates to signals module)."""
        return signals.evaluate_condition_for_bar(condition, indicators, bar_idx)

    def _check_stop_loss(
        self,
        position: Position,
        current_price: float,
        stop_config,  # StopLossConfig
    ) -> bool:
        """Check if stop loss is triggered (delegates to signals module).

        Maintains the per-symbol trailing extreme in self._trailing_highs.
        """
        tracked = self._trailing_highs.get(position.symbol, position.entry_price)
        triggered, new_extreme = signals.stop_loss_triggered(
            position.side, position.entry_price, current_price, stop_config, tracked
        )
        if stop_config.type.value == "trailing_percent":
            self._trailing_highs[position.symbol] = new_extreme
        return triggered

    def _check_take_profit(
        self,
        position: Position,
        current_price: float,
        tp_config,  # TakeProfitConfig
    ) -> bool:
        """Check if take profit is triggered (delegates to signals module)."""
        return signals.take_profit_triggered(
            position.side, position.entry_price, current_price, tp_config
        )

    def get_deployed_bot_state(self) -> DeployedBot:
        """Get the current state as a DeployedBot model."""
        return DeployedBot(
            id=self.id,
            config=self.config,
            status=self._status,
            broker_connected=self.broker._connected
            if hasattr(self.broker, "_connected")
            else False,
            open_positions=self._positions,
            pending_orders=self._orders,
            start_time=self._start_time or datetime.utcnow(),
            total_trades=self._total_trades,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=sum(p.unrealized_pnl for p in self._positions),
            peak_equity=0.0,  # Track separately
            current_equity=0.0,  # Get from broker
            daily_pnl=0.0,  # Track separately
        )
