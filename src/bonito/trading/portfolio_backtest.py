"""Account-level backtest: replay the live pipeline over history.

This is NOT another strategy simulator. Each trading day it calls the
exact code the paper account runs every evening — generate_intents →
execute_paper against a PaperLedger — with data sliced to that day, so
position caps, daily-buy limits, the cash buffer, regime gating, strategy
pinning, and the portfolio kill switch all behave precisely as they do in
production. If live_runner changes, this backtest changes with it.

Look-ahead is prevented structurally: ReplayStore serves point-in-time
slices of preloaded bars, so signal code physically cannot see the future.

Execution model (mirrors the deployed system):
- Daily cycle fills at the signal bar's close — exactly how the paper
  ledger fills after the evening run (NOT the engine's next-open rule).
- The 15-minute intraday stop sweep is approximated from daily bars:
  a stop fires if the day's low touches the level computed from the PRIOR
  high-water mark (the intraday ordering of high vs low is unknowable, so
  same-day ratcheting never saves a position — conservative). Fills happen
  at the level, or at the open when the bar gaps through it. Take profits
  mirror with the day's high. When both fire in one bar the stop wins.
- ATR for intraday stops uses bars through the previous close.
"""

import bisect
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from bonito.backtest.strategy import StrategyConfig
from bonito.data.models import BarData

from . import signals
from .live_runner import (
    REGIME_WARMUP_DAYS,
    UniverseConfig,
    _position_strategy,
    execute_paper,
    generate_intents,
)
from .paper import PaperLedger
from .signals import TradeIntent
from .validation import WindowMetrics, kill_verdict

logger = logging.getLogger(__name__)

TRADING_DAYS = 252


class ReplayStore:
    """Point-in-time view over preloaded bars.

    get_bars() only ever returns bars with timestamp <= end, so replayed
    signal code structurally cannot look ahead.
    """

    def __init__(self, bars: dict[str, BarData]):
        self.bars = {s.upper(): b for s, b in bars.items()}

    @classmethod
    def from_store(
        cls,
        store,
        universe: UniverseConfig,
        end: datetime,
    ) -> "ReplayStore":
        """Preload every universe + regime symbol from the real data store."""
        start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")
        regime_start = start - timedelta(days=REGIME_WARMUP_DAYS)
        bars: dict[str, BarData] = {}
        for symbol in universe.symbols:
            data = store.get_bars(symbol, start, end, universe.data.timeframe)
            if data is not None and len(data) > 0:
                bars[symbol] = data
            else:
                logger.warning(f"{symbol}: no stored bars — excluded from replay")
        for symbol in sorted(universe.regime_symbols() - set(universe.symbols)):
            data = store.get_bars(symbol, regime_start, end, universe.data.timeframe)
            if data is not None and len(data) > 0:
                bars[symbol] = data
            else:
                logger.warning(f"{symbol}: no regime bars — regime will read risk-off")
        return cls(bars)

    def get_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str = "1d"):
        data = self.bars.get(symbol.upper())
        if data is None:
            return None
        lo = bisect.bisect_left(data.timestamps, start)
        hi = bisect.bisect_right(data.timestamps, end)
        if hi - lo <= 0:
            return None
        return BarData(
            symbol=data.symbol,
            timeframe=data.timeframe,
            timestamps=data.timestamps[lo:hi],
            opens=data.opens[lo:hi],
            highs=data.highs[lo:hi],
            lows=data.lows[lo:hi],
            closes=data.closes[lo:hi],
            volumes=data.volumes[lo:hi],
        )

    def bar_at(self, symbol: str, day: datetime) -> dict | None:
        """OHLC of the exact bar on `day`, or None."""
        data = self.bars.get(symbol.upper())
        if data is None:
            return None
        i = bisect.bisect_left(data.timestamps, day)
        if i >= len(data.timestamps) or data.timestamps[i] != day:
            return None
        return {
            "open": data.opens[i],
            "high": data.highs[i],
            "low": data.lows[i],
            "close": data.closes[i],
        }

    def trading_days(self, symbols: list[str], start: datetime, end: datetime) -> list[datetime]:
        """Sorted union of bar timestamps across symbols within [start, end]."""
        days: set[datetime] = set()
        for symbol in symbols:
            data = self.bars.get(symbol.upper())
            if data is None:
                continue
            for ts in data.timestamps:
                if start <= ts <= end:
                    days.add(ts)
        return sorted(days)


class ClosedTrade(BaseModel):
    """A completed round trip reconstructed from the replay's fills."""

    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    reason: str


class AccountBacktestResult(BaseModel):
    """Everything the account replay produced."""

    universe_name: str
    start: datetime
    end: datetime
    starting_cash: float
    final_equity: float
    total_return: float
    realized_pnl: float
    unrealized_pnl: float

    equity_dates: list[datetime]
    equity_curve: list[float]

    max_drawdown: float
    sharpe: float = Field(..., description="All-days Sharpe on the account curve, sqrt(252)")
    trades: list[ClosedTrade]
    win_rate: float
    profit_factor: float

    max_concurrent_positions: int
    avg_concurrent_positions: float
    pct_days_in_market: float

    halted: bool
    halt_date: datetime | None = None
    halt_reason: str = ""
    open_positions: dict[str, float] = Field(
        default_factory=dict, description="Symbol → unrealized P&L of positions open at end"
    )
    per_symbol_pnl: dict[str, float] = Field(
        default_factory=dict, description="Symbol → realized P&L over the replay"
    )
    rejected_intents: int = 0
    intraday_stops_modeled: bool = True

    def window_metrics(self, start: datetime, end: datetime) -> WindowMetrics:
        """Metrics over a date slice of the account curve (for holdout splits)."""
        idx = [i for i, d in enumerate(self.equity_dates) if start <= d <= end]
        years = max((end - start).days / 365.25, 1 / 365.25)
        trades = [t for t in self.trades if start <= t.exit_date <= end]
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = wins / len(trades) if trades else 0.0

        if len(idx) < 2:
            return WindowMetrics(
                start=start,
                end=end,
                years=years,
                trades=len(trades),
                win_rate=win_rate,
                total_return=0.0,
                sharpe=0.0,
                max_drawdown=0.0,
            )

        equity = np.array([self.equity_curve[i] for i in idx])
        total_return = equity[-1] / equity[0] - 1 if equity[0] > 0 else 0.0
        peak = np.maximum.accumulate(equity)
        max_dd = float(np.max((peak - equity) / peak)) if np.all(peak > 0) else 0.0
        returns = np.diff(equity) / equity[:-1]
        sharpe = (
            float(np.mean(returns) / np.std(returns) * np.sqrt(TRADING_DAYS))
            if len(returns) > 1 and np.std(returns) > 0
            else 0.0
        )
        return WindowMetrics(
            start=start,
            end=end,
            years=years,
            trades=len(trades),
            win_rate=win_rate,
            total_return=total_return,
            sharpe=sharpe,
            max_drawdown=max_dd,
        )

    def verdict(self, start: datetime | None = None, end: datetime | None = None) -> list[str]:
        """Kill-filter reasons for a window of the account curve (empty = PASS)."""
        m = self.window_metrics(start or self.start, end or self.end)
        return kill_verdict(m)


def backtest_account(
    universe: UniverseConfig,
    replay: ReplayStore,
    start: datetime,
    end: datetime,
    intraday_stops: bool = True,
) -> AccountBacktestResult:
    """Replay the daily live pipeline over [start, end] and report account metrics.

    The ledger starts fresh at universe.risk.starting_cash_usd. Every day:
    intraday stop/TP pass (optional) → the real generate_intents →
    the real execute_paper (with strategy pinning) → mark to market.
    A kill-switch halt persists to the end of the replay, exactly as it
    would in production until a human runs `bonito live resume`.
    """
    ledger = PaperLedger(
        cash=universe.risk.starting_cash_usd, starting_cash=universe.risk.starting_cash_usd
    )
    days = replay.trading_days(universe.symbols, start, end)
    if not days:
        raise ValueError("no trading days with data in the requested window")

    equity_dates: list[datetime] = []
    equity_curve: list[float] = []
    concurrent: list[int] = []
    rejected = 0
    halt_date: datetime | None = None

    for day in days:
        if intraday_stops:
            _intraday_pass(universe, replay, ledger, day)

        intents, prices = generate_intents(universe, replay, ledger, as_of=day)
        buy_strategies = {
            i.symbol: universe.load_strategy_for(i.symbol) for i in intents if i.side == "buy"
        }
        n_before = len(ledger.fills)
        _, errors = execute_paper(ledger, intents, prices, strategies=buy_strategies)
        rejected += len(errors)
        for e in errors:
            logger.warning(f"{day.date()}: rejected intent — {e}")
        _restamp(ledger, n_before, day)

        if ledger.halted and halt_date is None:
            halt_date = day

        closes = {
            s: bar["close"] for s in ledger.positions if (bar := replay.bar_at(s, day)) is not None
        }
        equity_dates.append(day)
        equity_curve.append(ledger.equity(closes))
        concurrent.append(len(ledger.positions))

    return _build_result(
        universe,
        ledger,
        replay,
        start,
        end,
        equity_dates,
        equity_curve,
        concurrent,
        rejected,
        halt_date,
        intraday_stops,
    )


def _intraday_pass(
    universe: UniverseConfig,
    replay: ReplayStore,
    ledger: PaperLedger,
    day: datetime,
) -> None:
    """Approximate the 15-minute stop sweep from day's OHLC.

    Stops trigger off the low against the level from the PRIOR high-water
    mark; take profits off the high. Fill at the level, or at the open when
    the bar gaps through it. Survivors ratchet their HWM to the day's high,
    mirroring what repeated quote sweeps would have recorded.
    """
    for symbol, pos in sorted(ledger.positions.items()):
        bar = replay.bar_at(symbol, day)
        if bar is None:
            continue
        strategy = _position_strategy(pos, universe)

        exit_price: float | None = None
        reason = ""
        if strategy.stop_loss is not None:
            atr = _prior_atr(replay, universe, symbol, strategy, day)
            level = signals.stop_level(
                "long", pos.entry_price, strategy.stop_loss, pos.high_water_mark, atr=atr
            )
            if level is not None and bar["low"] <= level:
                exit_price = bar["open"] if bar["open"] <= level else level
                reason = "stop loss triggered (intraday)"

        if exit_price is None and strategy.take_profit is not None:
            level = signals.take_profit_level("long", pos.entry_price, strategy.take_profit)
            if level is not None and signals.take_profit_triggered(
                "long", pos.entry_price, bar["high"], strategy.take_profit
            ):
                exit_price = bar["open"] if bar["open"] >= level else level
                reason = "take profit triggered (intraday)"

        if exit_price is not None:
            n_before = len(ledger.fills)
            ledger.apply_sell(
                TradeIntent(
                    symbol=symbol,
                    side="sell",
                    quantity=pos.quantity,
                    reason=reason,
                    signal_price=exit_price,
                    signal_date=day,
                    strategy_name=strategy.name,
                ),
                exit_price,
            )
            _restamp(ledger, n_before, day)
        else:
            ledger.update_high_water_mark(symbol, bar["high"])


def _prior_atr(
    replay: ReplayStore,
    universe: UniverseConfig,
    symbol: str,
    strategy: StrategyConfig,
    day: datetime,
) -> float | None:
    """ATR from bars strictly before `day` (the sweep can't see today's bar)."""
    if strategy.stop_loss is None or strategy.stop_loss.type.value not in ("atr", "trailing_atr"):
        return None
    start = datetime.strptime(universe.data.start_date, "%Y-%m-%d")
    data = replay.get_bars(symbol, start, day - timedelta(days=1), universe.data.timeframe)
    if data is None or len(data) < 2:
        return None
    return signals.latest_atr(data, strategy.stop_loss.atr_period)


def _restamp(ledger: PaperLedger, n_fills_before: int, day: datetime) -> None:
    """Stamp fills (and freshly opened positions) with the simulated date."""
    for fill in ledger.fills[n_fills_before:]:
        fill.filled_at = day
        if fill.side == "buy" and fill.symbol in ledger.positions:
            ledger.positions[fill.symbol].entry_date = day


def _build_result(
    universe: UniverseConfig,
    ledger: PaperLedger,
    replay: ReplayStore,
    start: datetime,
    end: datetime,
    equity_dates: list[datetime],
    equity_curve: list[float],
    concurrent: list[int],
    rejected: int,
    halt_date: datetime | None,
    intraday_stops: bool,
) -> AccountBacktestResult:
    trades = _closed_trades(ledger)
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [-t.pnl for t in trades if t.pnl < 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    profit_factor = (sum(wins) / sum(losses)) if losses else (float("inf") if wins else 0.0)

    equity = np.array(equity_curve)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.max((peak - equity) / peak)) if len(equity) and np.all(peak > 0) else 0.0
    returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
    sharpe = (
        float(np.mean(returns) / np.std(returns) * np.sqrt(TRADING_DAYS))
        if len(returns) > 1 and np.std(returns) > 0
        else 0.0
    )

    last_day = equity_dates[-1]
    open_pnl: dict[str, float] = {}
    for symbol, pos in ledger.positions.items():
        bar = replay.bar_at(symbol, last_day)
        price = bar["close"] if bar else pos.entry_price
        open_pnl[symbol] = round((price - pos.entry_price) * pos.quantity, 2)

    per_symbol: dict[str, float] = {}
    for t in trades:
        per_symbol[t.symbol] = round(per_symbol.get(t.symbol, 0.0) + t.pnl, 2)

    final_equity = float(equity[-1])
    return AccountBacktestResult(
        universe_name=universe.name,
        start=start,
        end=end,
        starting_cash=ledger.starting_cash,
        final_equity=final_equity,
        total_return=final_equity / ledger.starting_cash - 1,
        realized_pnl=ledger.realized_pnl,
        unrealized_pnl=round(sum(open_pnl.values()), 2),
        equity_dates=equity_dates,
        equity_curve=[float(e) for e in equity_curve],
        max_drawdown=max_dd,
        sharpe=sharpe,
        trades=trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_concurrent_positions=max(concurrent) if concurrent else 0,
        avg_concurrent_positions=float(np.mean(concurrent)) if concurrent else 0.0,
        pct_days_in_market=(
            sum(1 for c in concurrent if c > 0) / len(concurrent) if concurrent else 0.0
        ),
        halted=ledger.halted,
        halt_date=halt_date,
        halt_reason=ledger.halt_reason,
        open_positions=open_pnl,
        per_symbol_pnl=per_symbol,
        rejected_intents=rejected,
        intraday_stops_modeled=intraday_stops,
    )


def _closed_trades(ledger: PaperLedger) -> list[ClosedTrade]:
    """Pair each sell fill with its entry (one position per symbol at a time)."""
    entries: dict[str, tuple[datetime, float]] = {}
    trades: list[ClosedTrade] = []
    for fill in ledger.fills:
        if fill.side == "buy":
            entries[fill.symbol] = (fill.filled_at, fill.price)
        else:
            entry_date, entry_price = entries.pop(fill.symbol, (fill.filled_at, fill.price))
            trades.append(
                ClosedTrade(
                    symbol=fill.symbol,
                    entry_date=entry_date,
                    exit_date=fill.filled_at,
                    entry_price=entry_price,
                    exit_price=fill.price,
                    quantity=fill.quantity,
                    pnl=(fill.price - entry_price) * fill.quantity,
                    reason=fill.reason,
                )
            )
    return trades


def save_account_result(
    result: AccountBacktestResult, directory: Path = Path("livetrade/research")
) -> Path:
    """Persist the replay result for audit / later comparison."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    path = directory / f"account_backtest_{stamp}.json"
    path.write_text(json.dumps(json.loads(result.model_dump_json()), indent=2))
    return path
