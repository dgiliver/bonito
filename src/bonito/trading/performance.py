"""Ledger performance reporting: trailing-period returns vs. benchmark, closed-trade stats.

Built on `tracking.paper_equity_curve` (the same fills + stored-closes
reconstruction the fidelity check uses) so "what did the account actually
do" has one source of truth across the status skill and the tracking gate.
"""

from datetime import datetime

from pydantic import BaseModel

from bonito.trading.live_runner import UniverseConfig
from bonito.trading.paper import PaperLedger
from bonito.trading.tracking import paper_equity_curve

DEFAULT_WINDOWS: tuple[tuple[str, int | None], ...] = (
    ("1D", 1),
    ("1W", 5),
    ("Inception", None),
)


class ClosedTrade(BaseModel):
    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    reason: str


class PeriodReturn(BaseModel):
    label: str
    start_equity: float
    end_equity: float
    return_pct: float
    benchmark_return_pct: float | None = None
    alpha_pct: float | None = None


class PerformanceReport(BaseModel):
    as_of: datetime
    current_equity: float
    realized_pnl: float
    unrealized_pnl: float
    periods: list[PeriodReturn]
    closed_trades: list[ClosedTrade]
    win_rate_pct: float | None = None
    profit_factor: float | None = None


def closed_trades_from_fills(ledger: PaperLedger) -> list[ClosedTrade]:
    """FIFO-match buy/sell fills per symbol into closed round-trip trades."""
    lots: dict[str, list[list[float]]] = {}
    closed: list[ClosedTrade] = []
    for f in sorted(ledger.fills, key=lambda fill: fill.filled_at):
        symbol_lots = lots.setdefault(f.symbol, [])
        if f.side == "buy":
            symbol_lots.append([f.quantity, f.price])
            continue
        remaining = f.quantity
        while remaining > 1e-9 and symbol_lots:
            lot = symbol_lots[0]
            take = min(remaining, lot[0])
            pnl = (f.price - lot[1]) * take
            closed.append(
                ClosedTrade(
                    symbol=f.symbol,
                    quantity=take,
                    entry_price=lot[1],
                    exit_price=f.price,
                    pnl=round(pnl, 2),
                    return_pct=round((f.price / lot[1] - 1) * 100, 2),
                    reason=f.reason,
                )
            )
            lot[0] -= take
            remaining -= take
            if lot[0] < 1e-9:
                symbol_lots.pop(0)
    return closed


def trade_stats(closed_trades: list[ClosedTrade]) -> tuple[float | None, float | None]:
    """(win_rate_pct, profit_factor) — both None when there are no closed trades."""
    if not closed_trades:
        return None, None
    wins = [t.pnl for t in closed_trades if t.pnl > 0]
    losses = [t.pnl for t in closed_trades if t.pnl <= 0]
    win_rate = round(len(wins) / len(closed_trades) * 100, 1)
    gross_loss = abs(sum(losses))
    profit_factor = round(sum(wins) / gross_loss, 2) if gross_loss > 0 else None
    return win_rate, profit_factor


def _value_on_or_after(
    sorted_dates: list[datetime], target: datetime, values: dict
) -> float | None:
    for d in sorted_dates:
        if d >= target:
            return values[d]
    return None


def _value_on_or_before(
    sorted_dates: list[datetime], target: datetime, values: dict
) -> float | None:
    result = None
    for d in sorted_dates:
        if d <= target:
            result = values[d]
        else:
            break
    return result


def period_returns(
    dates: list[datetime],
    equity: list[float],
    benchmark: dict[datetime, float] | None = None,
    windows: tuple[tuple[str, int | None], ...] = DEFAULT_WINDOWS,
) -> list[PeriodReturn]:
    """Trailing returns over each window's trading-day lookback, with optional benchmark alpha.

    A window is skipped when the equity curve doesn't span it yet (e.g. "1W"
    needs >=6 days of history) rather than computed on a misleadingly short sample.
    """
    if not dates:
        return []
    results = []
    end_equity = equity[-1]
    end_date = dates[-1]
    bench_dates = sorted(benchmark) if benchmark else []
    for label, lookback in windows:
        if lookback is None:
            start_idx = 0
        else:
            if len(dates) <= lookback:
                continue
            start_idx = len(dates) - 1 - lookback
        start_equity = equity[start_idx]
        start_date = dates[start_idx]
        ret = (end_equity / start_equity - 1) * 100 if start_equity else 0.0
        bench_ret: float | None = None
        alpha: float | None = None
        if benchmark:
            bench_start = _value_on_or_after(bench_dates, start_date, benchmark)
            bench_end = _value_on_or_before(bench_dates, end_date, benchmark)
            if bench_start is not None and bench_end is not None and bench_start > 0:
                bench_ret = (bench_end / bench_start - 1) * 100
                alpha = round(ret - bench_ret, 2)
                bench_ret = round(bench_ret, 2)
        results.append(
            PeriodReturn(
                label=label,
                start_equity=round(start_equity, 2),
                end_equity=round(end_equity, 2),
                return_pct=round(ret, 2),
                benchmark_return_pct=bench_ret,
                alpha_pct=alpha,
            )
        )
    return results


def build_performance_report(
    universe: UniverseConfig,
    ledger: PaperLedger,
    store,
    current_prices: dict[str, float],
    end: datetime,
    benchmark_symbol: str = "SPY",
) -> PerformanceReport:
    """Assemble the full performance picture: period returns, alpha, closed-trade stats.

    The trailing-period curve is reconstructed from stored daily closes (the
    tracking module's source of truth); its final point is then replaced
    with the live mark-to-market equity when current prices are supplied, so
    the headline number reflects right-now prices instead of last close.
    """
    dates, equity = paper_equity_curve(ledger, store, universe, end=end)
    if dates and current_prices:
        equity[-1] = ledger.equity(current_prices)

    benchmark = None
    if dates:
        bars = store.get_bars(benchmark_symbol, dates[0], end, universe.data.timeframe)
        if bars is not None:
            benchmark = dict(zip(bars.timestamps, bars.closes, strict=True))

    periods = period_returns(dates, equity, benchmark)
    closed = closed_trades_from_fills(ledger)
    win_rate, profit_factor = trade_stats(closed)
    summary = ledger.summary(current_prices)
    return PerformanceReport(
        as_of=end,
        current_equity=summary["equity"],
        realized_pnl=summary["realized_pnl"],
        unrealized_pnl=summary["unrealized_pnl"],
        periods=periods,
        closed_trades=closed,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
    )
