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
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PrivateAttr

from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData
from bonito.data.store import MarketDataStore

from . import signals
from .paper import PaperFill, PaperLedger, PaperPosition
from .signals import TradeIntent

logger = logging.getLogger(__name__)


class LivePricingError(RuntimeError):
    """Raised when a live position cannot be priced (no market quote).

    Fail-closed: the kill switch must not mark equity off entry_price fallback
    for real-money accounts — abort the cycle instead.
    """


DEFAULT_UNIVERSE_PATH = Path("config/universe.json")

# Bars older than this are considered stale and the symbol is skipped.
MAX_DATA_AGE_DAYS = 5
# Robinhood's minimum dollar-based order is $1; below this we don't bother.
MIN_ORDER_USD = 1.0
# Drift beyond this fraction of the larger leg is a fatal entry-blocking divergence;
# exits are NEVER gated — only new entries are blocked.
DRIFT_TOLERANCE_PCT = 0.005
# Extra history ingested for regime symbols so the SMA is defined from the
# universe start (200 trading days ≈ 10 months; 550 calendar days is safe).
REGIME_WARMUP_DAYS = 550

# Eastern exchange clock for the settled-vs-forming guard.
_ET = ZoneInfo("America/New_York")
# Minutes after the 16:00 ET close before the daily bar is trusted as settled
# (lets Yahoo finalize the row). Below this on the bar's date, the bar is forming.
SETTLE_HOUR_ET = 16
SETTLE_MINUTE_ET = 15


class RiskConfig(BaseModel):
    """Hard caps applied to every generated intent."""

    starting_cash_usd: float = 150.0
    max_position_usd: float = 30.0
    position_pct_equity: float | None = Field(
        default=None,
        description="When set, position size = equity * this fraction, capped at "
        "max_position_usd. Allows gains to compound. E.g. 0.20 = 20% of current equity.",
    )
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
    entry_allowlist: list[str] | None = Field(
        default=None,
        description="If set, only these symbols may open NEW positions (exits are "
        "never gated). Pre-live lever: restrict entries to kill-filter passers.",
    )
    entry_blocklist: list[str] = Field(
        default_factory=list,
        description="Symbols benched from NEW entries (exits are never gated). "
        "Managed by the weekly auto-research: a symbol lands here when no grid "
        "candidate passes its train kill filter AND benching it survives the "
        "account-replay gate; it is unbenched the same way when it heals.",
    )
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
    symbols: list[str] | None = None,
) -> dict[str, int]:
    """Ingest fresh daily bars for every universe symbol.

    Args:
        symbols: Refresh only this subset (regime symbols are then skipped
            too) — used by the intraday sweep, which only needs ATR bars
            for open positions. None refreshes the full universe.

    Returns:
        Symbol → number of bars ingested. Failures are logged and return -1
        so one bad symbol doesn't abort the whole refresh.
    """
    end = end or datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    results: dict[str, int] = {}
    for symbol in symbols if symbols is not None else universe.symbols:
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
    if symbols is not None:
        return results

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
    require_settled: bool = True,
) -> tuple[list[TradeIntent], dict[str, float]]:
    """Evaluate per-symbol strategies across the universe and produce intents.

    Exits are evaluated for every open position using the strategy PINNED at
    entry (lock-until-exit); entries use the symbol's currently-assigned
    strategy, gated by the regime filter and risk caps. After exits are
    priced, the portfolio kill switch runs: if drawdown from peak equity
    reaches risk.max_drawdown_halt, every position is flattened and the
    ledger halts — no entries until `bonito live resume`.

    When `require_settled` is True (default), entries are skipped and exits
    held if the latest stored bar's session has not settled in ET (forming
    intraday bar); set False only for the account replay, whose `as_of` is
    itself a settled session date.

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
        if require_settled and _is_forming(data.timestamps[-1], as_of):
            logger.warning(f"{symbol}: latest bar is forming (pre-close), holding")
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

    # D1 §5.4: in live mode every open position must be priced so the kill switch
    # marks equity off current broker quotes, not the entry_price fallback.
    # Fail-closed: abort the cycle rather than let the halt threshold be silently
    # miscalculated.  Paper always has prices (it only holds what it bought), so
    # this guard is live-gated and paper is byte-identical.
    if universe.mode == "live":
        unpriced = [s for s in ledger.positions if s not in prices]
        if unpriced:
            raise LivePricingError(
                f"Cannot mark equity: no price for open position(s) {unpriced}. "
                "Run `bonito live refresh` and retry, or exit position(s) manually."
            )

    current_equity = ledger.equity(prices)
    threshold = universe.risk.max_drawdown_halt
    if threshold is not None:
        equity = current_equity
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
    allowset = (
        None if universe.entry_allowlist is None else {s.upper() for s in universe.entry_allowlist}
    )
    if allowset is not None:
        logger.info(f"entry allowlist active: {sorted(allowset)}")
    blockset = {s.upper() for s in universe.entry_blocklist}
    if blockset:
        logger.info(f"entry blocklist active: {sorted(blockset)}")

    # Universe-list order decides slot competition — a TESTED choice, not an
    # accident: momentum-ranked competition collapsed the holdout (-20%) and
    # tripped the kill switch. See docs/EXPERIMENT_LOG.md (2026-06-12).
    for symbol in universe.symbols:
        if buys >= universe.risk.max_daily_buys:
            break
        if open_after_exits + buys >= universe.risk.max_positions:
            break
        if symbol in ledger.positions:
            continue
        if allowset is not None and symbol.upper() not in allowset:
            continue
        if symbol.upper() in blockset:
            continue

        pct = universe.risk.position_pct_equity
        target = (current_equity * pct) if pct is not None else universe.risk.max_position_usd
        dollar = min(target, universe.risk.max_position_usd, available)
        if dollar < MIN_ORDER_USD:
            break

        strategy = universe.load_strategy_for(symbol)
        if not _regime_allows(
            strategy, store, universe, as_of, regime_cache, require_settled=require_settled
        ):
            logger.info(f"{symbol}: regime filter is risk-off, skipping entry")
            continue

        data = store.get_bars(symbol, start, as_of, universe.data.timeframe)
        if data is None or len(data) < 2:
            logger.warning(f"{symbol}: no data, skipping")
            continue
        if _is_stale(data.timestamps[-1], as_of):
            logger.warning(f"{symbol}: data is stale, skipping")
            continue
        if require_settled and _is_forming(data.timestamps[-1], as_of):
            logger.warning(f"{symbol}: latest bar is forming (pre-close), skipping entry")
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
        # TODO(D4): gate on settled buying power once the MCP `get_accounts` is wired
        # on the Routine side; for now log only so the broker is the backstop on
        # T+1 settlement — revisit if rejections appear.
        if universe.mode == "live":
            logger.info(
                f"D4 note: {symbol} buy ${dollar:.2f} queued — verify settled buying "
                "power before placing (T+1 settlement may block this order)"
            )

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
    require_settled: bool = True,
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
        elif (
            require_settled
            and regime_data is not None
            and len(regime_data) > 0
            and _is_forming(regime_data.timestamps[-1], as_of)
        ):
            logger.warning(f"{key[0]}: regime data is forming (pre-close), treating as risk-off")
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


def compute_position_atrs(
    universe: UniverseConfig,
    ledger: PaperLedger,
    store: MarketDataStore,
    as_of: datetime | None = None,
) -> dict[str, float]:
    """Current ATR for each open position whose pinned strategy uses an ATR stop.

    Positions without enough stored bars are omitted — check_stops then
    holds them with a warning instead of guessing a stop level.
    """
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")
    atrs: dict[str, float] = {}
    for symbol, pos in ledger.positions.items():
        strategy = _position_strategy(pos, universe)
        stop = strategy.stop_loss
        if stop is None or stop.type.value not in ("atr", "trailing_atr"):
            continue
        data = store.get_bars(symbol, start, as_of, universe.data.timeframe)
        if data is not None and len(data) >= 2:
            atrs[symbol] = signals.latest_atr(data, stop.atr_period)
        else:
            logger.warning(f"{symbol}: no bars for ATR — stop check will hold")
    return atrs


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
    fatal_drift: bool = Field(
        default=False,
        description=(
            "True when any position exceeds DRIFT_TOLERANCE_PCT mismatch. "
            "Blocks new entries; exits are never gated."
        ),
    )
    fatal_reasons: list[str] = Field(
        default_factory=list,
        description="Per-symbol descriptions of fatal drift (>0.5% of the larger leg)",
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
        for reason in self.fatal_reasons:
            lines.append(f"FATAL DRIFT: {reason}")
        return "\n".join(lines)


class PreflightReport(BaseModel):
    """Result of the pre-trade safety gate (see `preflight`)."""

    ok: bool = Field(..., description="False means ABORT — do not trade this cycle")
    reasons: list[str] = Field(default_factory=list, description="Hard failures that set ok=False")
    warnings: list[str] = Field(
        default_factory=list, description="Soft issues; proceed but surface them"
    )
    mode: str
    live_enabled: bool
    halted: bool
    halt_reason: str = ""
    fresh_symbols: list[str] = Field(default_factory=list)
    stale_symbols: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)
    stale_regime: list[str] = Field(default_factory=list)
    forming_symbols: list[str] = Field(default_factory=list)

    def describe(self) -> str:
        head = "PREFLIGHT OK" if self.ok else "PREFLIGHT ABORT"
        lines = [f"{head} (mode={self.mode}, live_enabled={self.live_enabled})"]
        lines += [f"  ABORT: {r}" for r in self.reasons]
        lines += [f"  warn: {w}" for w in self.warnings]
        lines.append(
            f"  data: {len(self.fresh_symbols)} fresh, "
            f"{len(self.stale_symbols)} stale, {len(self.missing_symbols)} missing, "
            f"{len(self.forming_symbols)} forming"
        )
        return "\n".join(lines)


def preflight(
    universe: UniverseConfig,
    ledger: PaperLedger,
    store: MarketDataStore,
    as_of: datetime | None = None,
) -> PreflightReport:
    """Fail-closed gate that must pass before any UNATTENDED cycle.

    The daily pipeline already fails *safe* — stale symbols are skipped and
    stale regime data reads risk-off — but a routine running with no human
    can't tell "did nothing because of a data outage" from "no signals
    today". This gate converts those silent no-ops into a loud abort so an
    autonomous run stops and notifies instead of trading on bad state.

    Checks only what needs no broker data (config consistency, kill switch,
    data freshness); reconciliation against the broker is a separate step.

    Hard failures (ok=False, abort): live-flag inconsistency, a latched kill
    switch, or zero fresh symbols (a total data outage). Individually stale
    symbols and stale regime data are warnings — the run should still
    proceed so exits and stops process — surfaced for the run summary.
    """
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    reasons: list[str] = []
    warnings: list[str] = []

    if universe.mode == "live" and not universe.live_enabled:
        reasons.append("mode is 'live' but live_enabled is false")

    if ledger.halted:
        reasons.append(f"kill switch latched: {ledger.halt_reason or 'drawdown halt'}")

    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")
    fresh: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    forming: list[str] = []
    for symbol in universe.symbols:
        data = store.get_bars(symbol, start, as_of, universe.data.timeframe)
        if data is None or len(data) == 0:
            missing.append(symbol)
        elif _is_stale(data.timestamps[-1], as_of):
            stale.append(symbol)
        else:
            fresh.append(symbol)
            if _is_forming(data.timestamps[-1], as_of):
                forming.append(symbol)
    if not fresh:
        reasons.append(
            f"no fresh market data for any of {len(universe.symbols)} symbols (data outage?)"
        )
    elif stale:
        warnings.append(f"{len(stale)} symbol(s) stale, will be skipped: {stale}")
    if missing:
        warnings.append(f"{len(missing)} symbol(s) missing data: {missing}")
    if forming:
        warnings.append(
            f"{len(forming)} symbol(s) have a forming (pre-close) latest bar; "
            f"entries skipped and exits held for those: {forming}"
        )

    regime_start = start - timedelta(days=REGIME_WARMUP_DAYS)
    stale_regime: list[str] = []
    for symbol in sorted(universe.regime_symbols()):
        data = store.get_bars(symbol, regime_start, as_of, universe.data.timeframe)
        if data is None or len(data) == 0 or _is_stale(data.timestamps[-1], as_of):
            stale_regime.append(symbol)
    if stale_regime:
        warnings.append(f"regime data stale/missing {stale_regime}: entries forced risk-off")

    return PreflightReport(
        ok=not reasons,
        reasons=reasons,
        warnings=warnings,
        mode=universe.mode,
        live_enabled=universe.live_enabled,
        halted=ledger.halted,
        halt_reason=ledger.halt_reason,
        fresh_symbols=fresh,
        stale_symbols=stale,
        missing_symbols=missing,
        stale_regime=stale_regime,
        forming_symbols=forming,
    )


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

    Populates both the fine-grained exact-match fields (`in_sync`,
    `missing_in_ledger`, `missing_at_broker`, `quantity_mismatch`) and the
    coarser D1 entry gate (`fatal_drift`, `fatal_reasons`).  `in_sync` retains
    its original exact-match (1e-4) meaning so the 6 existing TestReconcile
    tests are unchanged.  `fatal_drift` uses DRIFT_TOLERANCE_PCT (0.5%) and
    only blocks new entries — exits are never gated.

    Args:
        broker_positions: Symbol → share quantity from the broker
            (e.g. Robinhood MCP get_equity_positions).
    """
    dust = 1e-4  # below this treat a position as zero for exact-match and drift checks
    broker = {s.upper(): q for s, q in broker_positions.items() if q > dust}
    report = ReconcileReport(in_sync=True)

    for symbol, qty in broker.items():
        pos = ledger.positions.get(symbol)
        if pos is None:
            report.missing_in_ledger[symbol] = qty
        elif abs(pos.quantity - qty) > dust:
            report.quantity_mismatch[symbol] = {"ledger": pos.quantity, "broker": qty}

    for symbol in ledger.positions:
        if symbol not in broker:
            report.missing_at_broker.append(symbol)

    report.in_sync = not (
        report.missing_in_ledger or report.missing_at_broker or report.quantity_mismatch
    )

    # --- D1 fatal-drift gate (entry-only, DRIFT_TOLERANCE_PCT) ---
    # Compute over the union of all ledger+broker symbols with meaningful qty.
    all_symbols = set(broker.keys()) | {s for s, p in ledger.positions.items() if p.quantity > dust}
    for symbol in sorted(all_symbols):
        ledger_qty = ledger.positions[symbol].quantity if symbol in ledger.positions else 0.0
        broker_qty = broker.get(symbol, 0.0)
        larger = max(ledger_qty, broker_qty)
        if larger <= dust:
            continue  # both sides are dust — not fatal
        diff = abs(ledger_qty - broker_qty)
        if diff > DRIFT_TOLERANCE_PCT * larger:
            report.fatal_reasons.append(
                f"{symbol}: ledger={ledger_qty:.4f} broker={broker_qty:.4f} "
                f"diff={diff:.4f} ({diff/larger:.2%} of {larger:.4f})"
            )
    report.fatal_drift = bool(report.fatal_reasons)
    return report


def reconcile_gate(
    ledger: PaperLedger,
    broker_positions: dict[str, float],
    *,
    tolerance_pct: float = DRIFT_TOLERANCE_PCT,
) -> ReconcileReport:
    """Thin wrapper: call reconcile_positions and return the report.

    This is the single D1 entry point for the Routine and CLI.  The caller
    checks ``report.fatal_drift`` to block new entries; exits are always
    permitted regardless of the report result.

    Args:
        tolerance_pct: fraction of the larger leg used as the fatal-drift
            threshold.  Defaults to DRIFT_TOLERANCE_PCT (0.5%).
    """
    # tolerance_pct is passed through the module constant for now; the
    # function signature exposes it so callers can tighten for tests.
    report = reconcile_positions(ledger, broker_positions, tolerance=1e-4)
    # Re-evaluate fatal_reasons with the caller's tolerance_pct if it differs.
    if tolerance_pct != DRIFT_TOLERANCE_PCT:
        dust = 1e-4
        broker = {s.upper(): q for s, q in broker_positions.items() if q > dust}
        all_symbols = (
            set(broker.keys()) | {s for s, p in ledger.positions.items() if p.quantity > dust}
        )
        report.fatal_reasons = []
        for symbol in sorted(all_symbols):
            ledger_qty = ledger.positions[symbol].quantity if symbol in ledger.positions else 0.0
            broker_qty = broker.get(symbol, 0.0)
            larger = max(ledger_qty, broker_qty)
            if larger <= dust:
                continue
            diff = abs(ledger_qty - broker_qty)
            if diff > tolerance_pct * larger:
                report.fatal_reasons.append(
                    f"{symbol}: ledger={ledger_qty:.4f} broker={broker_qty:.4f} "
                    f"diff={diff:.4f} ({diff/larger:.2%} of {larger:.4f})"
                )
        report.fatal_drift = bool(report.fatal_reasons)
    return report


def save_intents(intents: list[TradeIntent], directory: Path = Path("livetrade/intents")) -> Path:
    """Write intents to a timestamped JSON file for audit / live handoff."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"intents_{datetime.now(UTC).strftime('%Y-%m-%d_%H%M%S')}.json"
    path.write_text(json.dumps([json.loads(i.model_dump_json()) for i in intents], indent=2))
    return path


def _is_stale(last_bar: datetime, as_of: datetime) -> bool:
    return (as_of - last_bar) > timedelta(days=MAX_DATA_AGE_DAYS)


def _is_forming(last_bar: datetime, as_of: datetime) -> bool:
    """True if last_bar's trading session has not settled at as_of.

    D1 heuristic (RFC §5.1): treats every session as closing 16:00 ET and
    trusts the bar 15 min later. Both args are naive-UTC (the live path's
    convention); stored daily timestamps are ET-midnight-of-D in UTC, so the
    UTC->ET conversion recovers the session date D in both EST and EDT.
    Half-days (~9/yr) are intentionally ignored: the only error is treating a
    13:00-settled bar as forming until 16:15, i.e. skip a trade — never act on
    a wrong price. Any resolution failure is treated as forming (fail-closed).
    """
    try:
        bar_et = last_bar.replace(tzinfo=UTC).astimezone(_ET)
        now_et = as_of.replace(tzinfo=UTC).astimezone(_ET)
    except (ValueError, OverflowError, OSError):
        return True
    settle = datetime(
        bar_et.year,
        bar_et.month,
        bar_et.day,
        SETTLE_HOUR_ET,
        SETTLE_MINUTE_ET,
        tzinfo=_ET,
    )
    return now_et < settle
