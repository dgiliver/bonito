"""Build the dashboard state payload from ledger + universe + stored bars.

Pure functions over their inputs — no network, no globals — so the whole
payload is unit-testable with a fake store.
"""

import logging
from bisect import bisect_right
from datetime import UTC, datetime, timedelta

import numpy as np

from bonito.backtest.strategy import StrategyConfig
from bonito.data.store import MarketDataStore
from bonito.trading import signals
from bonito.trading.live_runner import (
    MAX_DATA_AGE_DAYS,
    REGIME_WARMUP_DAYS,
    UniverseConfig,
)
from bonito.trading.paper import PaperLedger, PaperPosition
from bonito.trading.validation import strategy_hash

logger = logging.getLogger(__name__)

FILLS_SHOWN = 20


def build_dashboard_state(
    universe: UniverseConfig,
    ledger: PaperLedger,
    store: MarketDataStore,
    as_of: datetime | None = None,
) -> dict:
    """Assemble everything the dashboard renders into one JSON-able dict."""
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")

    bars_cache: dict[str, object] = {}

    def bars_for(symbol: str):
        if symbol not in bars_cache:
            bars_cache[symbol] = store.get_bars(symbol, start, as_of, universe.data.timeframe)
        return bars_cache[symbol]

    positions = []
    prices: dict[str, float] = {}
    last_bar: datetime | None = None
    for symbol, pos in sorted(ledger.positions.items()):
        data = bars_for(symbol)
        price = None
        price_as_of = None
        if data is not None and len(data) > 0:
            price = float(data.closes[-1])
            price_as_of = data.timestamps[-1]
            prices[symbol] = price
            if last_bar is None or price_as_of > last_bar:
                last_bar = price_as_of
        positions.append(_position_row(pos, universe, data, price, price_as_of, as_of))

    default_strategy = universe.load_strategy()
    account = _account_summary(ledger, prices)
    regime = _regime_status(default_strategy, store, start, as_of, universe.data.timeframe)

    return {
        "generated_at": as_of.isoformat(),
        "mode": universe.mode,
        "live_enabled": universe.live_enabled,
        "universe": {
            "name": universe.name,
            "symbols": len(universe.symbols),
            "strategy_name": default_strategy.name,
            "strategy_hash": strategy_hash(default_strategy),
            "strategy_description": default_strategy.description,
        },
        "risk": {
            "max_position_usd": universe.risk.max_position_usd,
            "max_positions": universe.risk.max_positions,
            "max_daily_buys": universe.risk.max_daily_buys,
            "min_cash_buffer_usd": universe.risk.min_cash_buffer_usd,
            "max_drawdown_halt": universe.risk.max_drawdown_halt,
        },
        "account": account,
        "regime": regime,
        "positions": positions,
        "fills": _recent_fills(ledger),
        "equity_curve": _equity_curve(ledger, store, start, as_of, universe.data.timeframe),
        "data_freshness": {
            "last_bar": last_bar.isoformat() if last_bar else None,
            "stale": bool(last_bar and (as_of - last_bar) > timedelta(days=MAX_DATA_AGE_DAYS)),
        },
    }


def _account_summary(ledger: PaperLedger, prices: dict[str, float]) -> dict:
    s = ledger.summary(prices)
    equity = s["equity"]
    peak = ledger.peak_equity if ledger.peak_equity is not None else equity
    peak = max(peak, equity)
    drawdown_pct = (1 - equity / peak) * 100 if peak > 0 else 0.0
    return {
        **{
            k: s[k]
            for k in (
                "cash",
                "equity",
                "starting_cash",
                "total_return_pct",
                "realized_pnl",
                "unrealized_pnl",
                "total_fills",
                "halted",
                "halt_reason",
            )
        },
        "peak_equity": round(peak, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "open_positions": len(ledger.positions),
    }


def _position_row(
    pos: PaperPosition,
    universe: UniverseConfig,
    data,
    price: float | None,
    price_as_of: datetime | None,
    as_of: datetime,
) -> dict:
    strategy = pos.pinned_strategy() or universe.load_strategy_for(pos.symbol)
    price = price if price is not None else pos.entry_price

    stop_price = _stop_price(pos, strategy, data)
    tp_price = None
    if strategy.take_profit and strategy.take_profit.type.value == "percent":
        tp_price = pos.entry_price * (1 + strategy.take_profit.value)

    market_value = pos.quantity * price
    pnl = (price - pos.entry_price) * pos.quantity
    return {
        "symbol": pos.symbol,
        "quantity": round(pos.quantity, 4),
        "entry_price": round(pos.entry_price, 2),
        "entry_date": pos.entry_date.isoformat(),
        "days_held": max((as_of.date() - pos.entry_date.date()).days, 0),
        "current_price": round(price, 2),
        "price_as_of": price_as_of.isoformat() if price_as_of else None,
        "stale": bool(price_as_of and (as_of - price_as_of) > timedelta(days=MAX_DATA_AGE_DAYS)),
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(pnl, 2),
        "unrealized_pct": round((price / pos.entry_price - 1) * 100, 2),
        "high_water_mark": round(pos.high_water_mark, 2),
        "stop_price": round(stop_price, 2) if stop_price is not None else None,
        "stop_distance_pct": (
            round((price - stop_price) / price * 100, 2) if stop_price is not None else None
        ),
        "take_profit_price": round(tp_price, 2) if tp_price is not None else None,
        "tp_distance_pct": (
            round((tp_price - price) / price * 100, 2) if tp_price is not None else None
        ),
        "strategy_name": pos.strategy_name or strategy.name,
        "strategy_hash": pos.strategy_hash,
    }


def _stop_price(pos: PaperPosition, strategy: StrategyConfig, data) -> float | None:
    """Current stop level for a long position, mirroring signals semantics."""
    stop = strategy.stop_loss
    if stop is None:
        return None
    stop_type = stop.type.value
    if stop_type == "percent":
        return pos.entry_price * (1 - stop.value)
    if stop_type == "trailing_percent":
        return pos.high_water_mark * (1 - stop.value)
    if stop_type in ("atr", "trailing_atr"):
        if data is None or len(data) < 2:
            return None
        atr = signals.latest_atr(data, stop.atr_period)
        base = pos.entry_price if stop_type == "atr" else pos.high_water_mark
        return base - stop.value * atr
    return None


def _regime_status(
    strategy: StrategyConfig,
    store: MarketDataStore,
    start: datetime,
    as_of: datetime,
    timeframe: str,
) -> dict | None:
    regime = strategy.regime_filter
    if regime is None:
        return None
    data = store.get_bars(
        regime.symbol.upper(), start - timedelta(days=REGIME_WARMUP_DAYS), as_of, timeframe
    )
    close = sma = None
    if data is not None and len(data) >= regime.sma_period:
        closes = np.asarray(data.closes, dtype=float)
        close = float(closes[-1])
        sma = float(np.mean(closes[-regime.sma_period :]))
    return {
        "symbol": regime.symbol.upper(),
        "sma_period": regime.sma_period,
        "close": round(close, 2) if close is not None else None,
        "sma": round(sma, 2) if sma is not None else None,
        "risk_on": signals.regime_allows_long(regime, data),
        "as_of": data.timestamps[-1].isoformat() if data is not None and len(data) else None,
    }


def _recent_fills(ledger: PaperLedger) -> list[dict]:
    fills = []
    for f in ledger.fills[-FILLS_SHOWN:][::-1]:
        fills.append(
            {
                "symbol": f.symbol,
                "side": f.side,
                "quantity": round(f.quantity, 4),
                "price": round(f.price, 2),
                "notional": round(f.notional, 2),
                "reason": f.reason,
                "filled_at": f.filled_at.isoformat(),
                "strategy_name": f.strategy_name,
            }
        )
    return fills


def _equity_curve(
    ledger: PaperLedger,
    store: MarketDataStore,
    start: datetime,
    as_of: datetime,
    timeframe: str,
) -> list[dict]:
    """Reconstruct daily account equity from fill history and stored closes.

    Positions are valued at the most recent close at or before each day;
    days before the first fill are omitted (equity was just starting cash).
    """
    if not ledger.fills:
        return []

    fills = sorted(ledger.fills, key=lambda f: f.filled_at)
    symbols = {f.symbol for f in fills}
    closes_by_symbol: dict[str, tuple[list, list]] = {}
    for symbol in symbols:
        data = store.get_bars(symbol, start, as_of, timeframe)
        if data is None or len(data) == 0:
            logger.warning(f"{symbol}: no bars for equity curve, valuing at fill price")
            closes_by_symbol[symbol] = ([], [])
        else:
            dates = [t.date() for t in data.timestamps]
            closes_by_symbol[symbol] = (dates, [float(c) for c in data.closes])

    def close_at(symbol: str, day, fallback: float) -> float:
        dates, closes = closes_by_symbol[symbol]
        i = bisect_right(dates, day)
        return closes[i - 1] if i else fallback

    curve = []
    cash = ledger.starting_cash
    holdings: dict[str, float] = {}
    entry_prices: dict[str, float] = {}
    fill_idx = 0
    day = fills[0].filled_at.date()
    end_day = as_of.date()

    while day <= end_day:
        while fill_idx < len(fills) and fills[fill_idx].filled_at.date() <= day:
            f = fills[fill_idx]
            if f.side == "buy":
                cash -= f.notional
                holdings[f.symbol] = holdings.get(f.symbol, 0.0) + f.quantity
                entry_prices[f.symbol] = f.price
            else:
                cash += f.notional
                remaining = holdings.get(f.symbol, 0.0) - f.quantity
                if remaining <= 1e-9:
                    holdings.pop(f.symbol, None)
                else:
                    holdings[f.symbol] = remaining
            fill_idx += 1

        value = cash
        for symbol, qty in holdings.items():
            value += qty * close_at(symbol, day, entry_prices.get(symbol, 0.0))
        curve.append({"date": day.isoformat(), "equity": round(value, 2)})
        day += timedelta(days=1)

    return curve
