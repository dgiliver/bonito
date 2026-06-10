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

from pydantic import BaseModel, Field, PrivateAttr

from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData
from bonito.data.store import MarketDataStore

from . import signals
from .paper import PaperFill, PaperLedger, PaperPosition
from .signals import TradeIntent

logger = logging.getLogger(__name__)

DEFAULT_UNIVERSE_PATH = Path("config/universe.json")

# Bars older than this are considered stale and the symbol is skipped.
MAX_DATA_AGE_DAYS = 5
# Robinhood's minimum dollar-based order is $1; below this we don't bother.
MIN_ORDER_USD = 1.0
# Extra history ingested for regime symbols so the SMA is defined from the
# universe start (200 trading days ≈ 10 months; 550 calendar days is safe).
REGIME_WARMUP_DAYS = 550


class RiskConfig(BaseModel):
    """Hard caps applied to every generated intent."""

    starting_cash_usd: float = 150.0
    max_position_usd: float = 30.0
    max_positions: int = 5
    max_daily_buys: int = 3
    min_cash_buffer_usd: float = 5.0
    allow_short: bool = False
    max_drawdown_halt: float | None = Field(
        default=0.25,
        description="Kill switch: flatten everything and halt new entries when "
        "account drawdown from peak equity reaches this fraction. None disables.",
    )


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
    symbol_strategies: dict[str, str] = Field(
        default_factory=dict,
        description="Per-symbol strategy path overrides; symbols not listed use strategy_path",
    )
    data: DataConfig = Field(default_factory=DataConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    _strategy_cache: dict[str, StrategyConfig] = PrivateAttr(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DEFAULT_UNIVERSE_PATH) -> "UniverseConfig":
        return cls.model_validate_json(Path(path).read_text())

    def load_strategy(self) -> StrategyConfig:
        return self._load_strategy_file(self.strategy_path)

    def load_strategy_for(self, symbol: str) -> StrategyConfig:
        """The strategy assigned to a symbol (override or default)."""
        path = self.symbol_strategies.get(symbol.upper(), self.strategy_path)
        return self._load_strategy_file(path)

    def regime_symbols(self) -> set[str]:
        """Reference symbols required by any assigned strategy's regime filter."""
        symbols: set[str] = set()
        for path in {self.strategy_path, *self.symbol_strategies.values()}:
            strategy = self._load_strategy_file(path)
            if strategy.regime_filter is not None:
                symbols.add(strategy.regime_filter.symbol.upper())
        return symbols

    def _load_strategy_file(self, path: str) -> StrategyConfig:
        if path not in self._strategy_cache:
            data = json.loads(Path(path).read_text())
            if "config" in data and "indicators" not in data:
                data = data["config"]
            self._strategy_cache[path] = StrategyConfig(**data)
        return self._strategy_cache[path]


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

    # Regime reference symbols need extra history so the SMA is defined
    # from the universe start date onward.
    universe_start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")
    regime_start = (universe_start - timedelta(days=REGIME_WARMUP_DAYS)).strftime("%Y-%m-%d")
    for symbol in sorted(universe.regime_symbols() - set(universe.symbols)):
        try:
            results[symbol] = store.ingest_from_yahoo(
                symbol,
                start=regime_start,
                end=end,
                timeframe=universe.data.timeframe,  # type: ignore[arg-type]
            )
        except Exception:
            logger.error(f"Failed to refresh regime symbol {symbol}", exc_info=True)
            results[symbol] = -1
    return results


def generate_intents(
    universe: UniverseConfig,
    store: MarketDataStore,
    ledger: PaperLedger,
    as_of: datetime | None = None,
) -> tuple[list[TradeIntent], dict[str, float]]:
    """Evaluate per-symbol strategies across the universe and produce intents.

    Exits are evaluated for every open position using the strategy PINNED at
    entry (lock-until-exit); entries use the symbol's currently-assigned
    strategy, gated by the regime filter and risk caps. After exits are
    priced, the portfolio kill switch runs: if drawdown from peak equity
    reaches risk.max_drawdown_halt, every position is flattened and the
    ledger halts — no entries until `bonito live resume`.

    Trailing-stop high-water marks and the peak-equity watermark on the
    ledger are updated as side effects (caller saves the ledger).

    Returns:
        (intents, last_close_prices) — prices cover every symbol that had
        usable data, for marking the ledger to market.
    """
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")

    intents: list[TradeIntent] = []
    prices: dict[str, float] = {}

    # --- Exits first: every open position gets checked ---
    for symbol, pos in sorted(ledger.positions.items()):
        strategy = _position_strategy(pos, universe)
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

    # --- Portfolio kill switch: flatten and halt on excessive drawdown ---
    sells = {i.symbol for i in intents}
    threshold = universe.risk.max_drawdown_halt
    if threshold is not None:
        equity = ledger.equity(prices)
        drawdown = ledger.note_equity(equity)
        if not ledger.halted and drawdown >= threshold:
            ledger.halt(
                f"drawdown {drawdown:.1%} >= {threshold:.0%} cap "
                f"(equity ${equity:.2f}, peak ${ledger.peak_equity:.2f})"
            )
            for symbol, pos in sorted(ledger.positions.items()):
                if symbol in sells:
                    continue
                price = prices.get(symbol)
                if price is None:
                    logger.warning(f"{symbol}: no price to flatten under halt; exit manually")
                    continue
                intents.append(
                    TradeIntent(
                        symbol=symbol,
                        side="sell",
                        quantity=pos.quantity,
                        reason=f"kill switch: {ledger.halt_reason}",
                        signal_price=price,
                        signal_date=as_of,
                        strategy_name=pos.strategy_name,
                    )
                )
                sells.add(symbol)

    if ledger.halted:
        logger.warning(f"Ledger halted ({ledger.halt_reason}); no entries generated")
        return intents, prices

    # --- Entries: only while caps allow ---
    open_after_exits = len(ledger.positions) - len(sells)
    # Cash freed by pending sells isn't counted — entries spend only
    # currently-settled cash, which is the conservative cash-account behavior.
    available = ledger.cash - universe.risk.min_cash_buffer_usd
    buys = 0
    regime_cache: dict[tuple[str, int], bool] = {}

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

        strategy = universe.load_strategy_for(symbol)
        if not _regime_allows(strategy, store, universe, as_of, regime_cache):
            logger.info(f"{symbol}: regime filter is risk-off, skipping entry")
            continue

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


def _position_strategy(pos: PaperPosition, universe: UniverseConfig) -> StrategyConfig:
    """The strategy managing an open position: pinned at entry, else current."""
    pinned = pos.pinned_strategy()
    if pinned is not None:
        return pinned
    return universe.load_strategy_for(pos.symbol)


def _regime_allows(
    strategy: StrategyConfig,
    store: MarketDataStore,
    universe: UniverseConfig,
    as_of: datetime,
    cache: dict[tuple[str, int], bool],
) -> bool:
    """Evaluate (and cache) a strategy's regime filter against stored bars."""
    regime = strategy.regime_filter
    if regime is None:
        return True
    key = (regime.symbol.upper(), regime.sma_period)
    if key not in cache:
        start = datetime.strptime(universe.data.start_date, "%Y-%m-%d") - timedelta(
            days=REGIME_WARMUP_DAYS
        )
        regime_data: BarData | None = store.get_bars(key[0], start, as_of, universe.data.timeframe)
        if (
            regime_data is not None
            and len(regime_data) > 0
            and _is_stale(regime_data.timestamps[-1], as_of)
        ):
            logger.warning(f"{key[0]}: regime data is stale, treating as risk-off")
            regime_data = None
        cache[key] = signals.regime_allows_long(regime, regime_data)
    return cache[key]


def execute_paper(
    ledger: PaperLedger,
    intents: list[TradeIntent],
    prices: dict[str, float],
    strategies: dict[str, StrategyConfig] | None = None,
) -> tuple[list[PaperFill], list[str]]:
    """Fill intents against the paper ledger at the given prices.

    Sells run before buys so freed cash is available. Intents without a
    price are rejected, never silently dropped.

    Args:
        strategies: Symbol → strategy that generated the buy intent; pinned
            to the position so exits use the same config (lock-until-exit).

    Returns:
        (fills, errors)
    """
    fills: list[PaperFill] = []
    errors: list[str] = []
    strategies = strategies or {}

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
                fills.append(
                    ledger.apply_buy(intent, price, strategy=strategies.get(intent.symbol))
                )
        except ValueError as e:
            errors.append(f"{intent.symbol}: {e}")

    return fills, errors


def check_stops(
    universe: UniverseConfig,
    ledger: PaperLedger,
    prices: dict[str, float],
    atrs: dict[str, float] | None = None,
) -> list[TradeIntent]:
    """Intraday stop-loss / take-profit sweep at current prices.

    Designed for the in-session monitor loop: prices come from Robinhood
    MCP quotes (live) or any fresh source (paper). Only inspects open
    positions; never generates entries. Updates trailing high-water marks.
    Each position is checked against its pinned strategy.

    Args:
        atrs: Symbol → current ATR, required for positions whose strategy
            uses atr/trailing_atr stops (compute with signals.latest_atr
            on stored daily bars).
    """
    intents: list[TradeIntent] = []
    atrs = atrs or {}
    now = datetime.now(UTC)

    for symbol, pos in sorted(ledger.positions.items()):
        strategy = _position_strategy(pos, universe)
        price = prices.get(symbol)
        if price is None or price <= 0:
            logger.warning(f"{symbol}: no price for stop check")
            continue

        reason: str | None = None
        if strategy.stop_loss:
            triggered, new_hwm = signals.stop_loss_triggered(
                "long",
                pos.entry_price,
                price,
                strategy.stop_loss,
                pos.high_water_mark,
                atr=atrs.get(symbol),
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


class ReconcileReport(BaseModel):
    """Drift between the ledger and the broker's actual positions."""

    in_sync: bool
    missing_in_ledger: dict[str, float] = Field(
        default_factory=dict,
        description="Broker holds these but the ledger doesn't — money floating, CRITICAL",
    )
    missing_at_broker: list[str] = Field(
        default_factory=list,
        description="Ledger thinks these are open but the broker shows nothing",
    )
    quantity_mismatch: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Symbol → {ledger, broker} quantities that disagree",
    )

    def describe(self) -> str:
        if self.in_sync:
            return "ledger and broker are in sync"
        lines = []
        for sym, qty in self.missing_in_ledger.items():
            lines.append(f"CRITICAL: broker holds {qty} {sym} unknown to the ledger")
        for sym in self.missing_at_broker:
            lines.append(f"{sym}: open in ledger but not held at broker")
        for sym, d in self.quantity_mismatch.items():
            lines.append(f"{sym}: ledger={d['ledger']} broker={d['broker']}")
        return "\n".join(lines)


def reconcile_positions(
    ledger: PaperLedger,
    broker_positions: dict[str, float],
    tolerance: float = 1e-4,
) -> ReconcileReport:
    """Compare ledger positions against the broker's actual holdings.

    MUST run (and pass) at the start of every live session before any
    signal generation. A previous session crashing between order placement
    and record-fill is exactly what this catches — nothing trades until a
    human (or an explicit record-fill) resolves the drift.

    Args:
        broker_positions: Symbol → share quantity from the broker
            (e.g. Robinhood MCP get_equity_positions).
    """
    broker = {s.upper(): q for s, q in broker_positions.items() if q > tolerance}
    report = ReconcileReport(in_sync=True)

    for symbol, qty in broker.items():
        pos = ledger.positions.get(symbol)
        if pos is None:
            report.missing_in_ledger[symbol] = qty
        elif abs(pos.quantity - qty) > tolerance:
            report.quantity_mismatch[symbol] = {"ledger": pos.quantity, "broker": qty}

    for symbol in ledger.positions:
        if symbol not in broker:
            report.missing_at_broker.append(symbol)

    report.in_sync = not (
        report.missing_in_ledger or report.missing_at_broker or report.quantity_mismatch
    )
    return report


def save_intents(intents: list[TradeIntent], directory: Path = Path("livetrade/intents")) -> Path:
    """Write intents to a timestamped JSON file for audit / live handoff."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"intents_{datetime.now(UTC).strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(json.dumps([json.loads(i.model_dump_json()) for i in intents], indent=2))
    return path


def _is_stale(last_bar: datetime, as_of: datetime) -> bool:
    return (as_of - last_bar) > timedelta(days=MAX_DATA_AGE_DAYS)
