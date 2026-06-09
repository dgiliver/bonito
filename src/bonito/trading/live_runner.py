"""Daily live-trading runner for the Robinhood universe.

Orchestrates the option-A pipeline: DuckDB bars → signal evaluation →
TradeIntents → paper fills (or JSON handoff to a Claude session that
places real orders via the Robinhood MCP).

Position sizing deliberately ignores the strategy's own position_size
(tuned for single-symbol backtests) and applies the universe risk caps
instead — small dollar-based fractional orders across many symbols.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from bonito.backtest.strategy import StrategyConfig
from bonito.data.store import MarketDataStore

from . import signals
from .paper import PaperFill, PaperLedger
from .signals import TradeIntent

logger = logging.getLogger(__name__)

DEFAULT_UNIVERSE_PATH = Path("config/universe.json")

# Bars older than this are considered stale and the symbol is skipped.
MAX_DATA_AGE_DAYS = 5
# Robinhood's minimum dollar-based order is $1; below this we don't bother.
MIN_ORDER_USD = 1.0


class RiskConfig(BaseModel):
    """Hard caps applied to every generated intent."""

    starting_cash_usd: float = 150.0
    max_position_usd: float = 30.0
    max_positions: int = 5
    max_daily_buys: int = 3
    min_cash_buffer_usd: float = 5.0
    allow_short: bool = False


class DataConfig(BaseModel):
    timeframe: str = "1d"
    start_date: str = "2022-01-01"


class UniverseConfig(BaseModel):
    """Parsed config/universe.json."""

    name: str
    description: str = ""
    broker: str = "robinhood"
    account_nickname: str = "Agentic"
    mode: str = "paper"
    live_enabled: bool = False
    symbols: list[str] = Field(..., min_length=1)
    strategy_path: str
    data: DataConfig = Field(default_factory=DataConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    @classmethod
    def load(cls, path: Path = DEFAULT_UNIVERSE_PATH) -> "UniverseConfig":
        return cls.model_validate_json(Path(path).read_text())

    def load_strategy(self) -> StrategyConfig:
        data = json.loads(Path(self.strategy_path).read_text())
        if "config" in data and "indicators" not in data:
            data = data["config"]
        return StrategyConfig(**data)


def refresh_data(
    universe: UniverseConfig,
    store: MarketDataStore,
    end: datetime | None = None,
) -> dict[str, int]:
    """Ingest fresh daily bars for every universe symbol.

    Returns:
        Symbol → number of bars ingested. Failures are logged and return -1
        so one bad symbol doesn't abort the whole refresh.
    """
    end = end or datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    results: dict[str, int] = {}
    for symbol in universe.symbols:
        try:
            results[symbol] = store.ingest_from_yahoo(
                symbol,
                start=universe.data.start_date,
                end=end,
                timeframe=universe.data.timeframe,  # type: ignore[arg-type]
            )
        except Exception:
            logger.error(f"Failed to refresh {symbol}", exc_info=True)
            results[symbol] = -1
    return results


def generate_intents(
    universe: UniverseConfig,
    store: MarketDataStore,
    ledger: PaperLedger,
    as_of: datetime | None = None,
) -> tuple[list[TradeIntent], dict[str, float]]:
    """Evaluate the strategy across the universe and produce trade intents.

    Exits are evaluated for every open position; entries only while risk
    caps allow. Trailing-stop high-water marks on the ledger are updated
    as a side effect (caller is responsible for saving the ledger).

    Returns:
        (intents, last_close_prices) — prices cover every symbol that had
        usable data, for marking the ledger to market.
    """
    strategy = universe.load_strategy()
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")

    intents: list[TradeIntent] = []
    prices: dict[str, float] = {}

    # --- Exits first: every open position gets checked ---
    for symbol, pos in sorted(ledger.positions.items()):
        data = store.get_bars(symbol, start, as_of, universe.data.timeframe)
        if data is None or len(data) < 2:
            logger.warning(f"{symbol}: no data for exit check, holding")
            continue
        if _is_stale(data.timestamps[-1], as_of):
            logger.warning(f"{symbol}: data is stale, holding")
            continue

        last_close = data.closes[-1]
        prices[symbol] = last_close

        should_exit, reason, new_hwm = signals.latest_exit_signal(
            strategy,
            data,
            side="long",
            entry_price=pos.entry_price,
            tracked_extreme=pos.high_water_mark,
        )
        ledger.update_high_water_mark(symbol, new_hwm)

        if should_exit:
            intents.append(
                TradeIntent(
                    symbol=symbol,
                    side="sell",
                    quantity=pos.quantity,
                    reason=reason,
                    signal_price=last_close,
                    signal_date=data.timestamps[-1],
                    strategy_name=strategy.name,
                )
            )

    # --- Entries: only while caps allow ---
    sells = {i.symbol for i in intents}
    open_after_exits = len(ledger.positions) - len(sells)
    # Cash freed by pending sells isn't counted — entries spend only
    # currently-settled cash, which is the conservative cash-account behavior.
    available = ledger.cash - universe.risk.min_cash_buffer_usd
    buys = 0

    for symbol in universe.symbols:
        if buys >= universe.risk.max_daily_buys:
            break
        if open_after_exits + buys >= universe.risk.max_positions:
            break
        if symbol in ledger.positions:
            continue

        dollar = min(universe.risk.max_position_usd, available)
        if dollar < MIN_ORDER_USD:
            break

        data = store.get_bars(symbol, start, as_of, universe.data.timeframe)
        if data is None or len(data) < 2:
            logger.warning(f"{symbol}: no data, skipping")
            continue
        if _is_stale(data.timestamps[-1], as_of):
            logger.warning(f"{symbol}: data is stale, skipping")
            continue

        last_close = data.closes[-1]
        prices[symbol] = last_close

        side, reason = signals.latest_entry_signal(strategy, data)
        if side is None:
            continue
        if side == "short" and not universe.risk.allow_short:
            logger.info(f"{symbol}: short signal ignored (allow_short=false)")
            continue

        intents.append(
            TradeIntent(
                symbol=symbol,
                side="buy",
                dollar_amount=round(dollar, 2),
                reason=reason,
                signal_price=last_close,
                signal_date=data.timestamps[-1],
                strategy_name=strategy.name,
            )
        )
        buys += 1
        available -= dollar

    return intents, prices


def execute_paper(
    ledger: PaperLedger,
    intents: list[TradeIntent],
    prices: dict[str, float],
) -> tuple[list[PaperFill], list[str]]:
    """Fill intents against the paper ledger at the given prices.

    Sells run before buys so freed cash is available. Intents without a
    price are rejected, never silently dropped.

    Returns:
        (fills, errors)
    """
    fills: list[PaperFill] = []
    errors: list[str] = []

    ordered = [i for i in intents if i.side == "sell"] + [i for i in intents if i.side == "buy"]
    for intent in ordered:
        price = prices.get(intent.symbol)
        if price is None or price <= 0:
            errors.append(f"{intent.symbol}: no fill price available")
            continue
        try:
            if intent.side == "sell":
                fills.append(ledger.apply_sell(intent, price))
            else:
                fills.append(ledger.apply_buy(intent, price))
        except ValueError as e:
            errors.append(f"{intent.symbol}: {e}")

    return fills, errors


def check_stops(
    universe: UniverseConfig,
    ledger: PaperLedger,
    prices: dict[str, float],
) -> list[TradeIntent]:
    """Intraday stop-loss / take-profit sweep at current prices.

    Designed for the in-session monitor loop: prices come from Robinhood
    MCP quotes (live) or any fresh source (paper). Only inspects open
    positions; never generates entries. Updates trailing high-water marks.
    """
    strategy = universe.load_strategy()
    intents: list[TradeIntent] = []
    now = datetime.now(UTC)

    for symbol, pos in sorted(ledger.positions.items()):
        price = prices.get(symbol)
        if price is None or price <= 0:
            logger.warning(f"{symbol}: no price for stop check")
            continue

        reason: str | None = None
        if strategy.stop_loss:
            triggered, new_hwm = signals.stop_loss_triggered(
                "long", pos.entry_price, price, strategy.stop_loss, pos.high_water_mark
            )
            ledger.update_high_water_mark(symbol, new_hwm)
            if triggered:
                reason = "stop loss triggered (intraday)"

        if (
            reason is None
            and strategy.take_profit
            and signals.take_profit_triggered("long", pos.entry_price, price, strategy.take_profit)
        ):
            reason = "take profit triggered (intraday)"

        if reason:
            intents.append(
                TradeIntent(
                    symbol=symbol,
                    side="sell",
                    quantity=pos.quantity,
                    reason=reason,
                    signal_price=price,
                    signal_date=now,
                    strategy_name=strategy.name,
                )
            )

    return intents


def save_intents(intents: list[TradeIntent], directory: Path = Path("livetrade/intents")) -> Path:
    """Write intents to a timestamped JSON file for audit / live handoff."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"intents_{datetime.now(UTC).strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(json.dumps([json.loads(i.model_dump_json()) for i in intents], indent=2))
    return path


def _is_stale(last_bar: datetime, as_of: datetime) -> bool:
    return (as_of - last_bar) > timedelta(days=MAX_DATA_AGE_DAYS)
