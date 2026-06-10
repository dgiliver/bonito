"""Strategy validation: kill filters and windowed (train/holdout) metrics.

The kill filter rejects ticker/strategy pairs that shouldn't trade live:
too few trades to be statistically meaningful, drawdowns beyond what the
account can stomach, or a Sharpe high enough to scream overfitting. The
thresholds generalize the autoresearch loop's filter
(research/autoresearch_trading.py: 30 trades over a ~4-year window, 25%
max drawdown, 3.0 Sharpe ceiling) so they apply to windows of any length.

Windowed metrics let one full-range simulation serve both the train and
holdout verdicts: the equity curve and trade list are sliced by date, so
indicator warmup never bleeds into the holdout numbers and positions open
across the boundary are handled naturally.
"""

import hashlib
import math
from datetime import datetime

import numpy as np
from pydantic import BaseModel, Field

from bonito.backtest.models import BacktestResult
from bonito.backtest.strategy import StrategyConfig

# ~30 trades over the original 4.4-year research window
MIN_TRADES_PER_YEAR = 7.0
MAX_DRAWDOWN = 0.25
MAX_SHARPE = 3.0  # Overfitting ceiling

TRADING_DAYS = 252


class WindowMetrics(BaseModel):
    """Performance metrics computed over a date slice of a backtest."""

    start: datetime
    end: datetime
    years: float = Field(..., description="Window length in calendar years")
    trades: int
    win_rate: float
    total_return: float
    sharpe: float
    max_drawdown: float


def strategy_hash(strategy: StrategyConfig) -> str:
    """Short content hash identifying a strategy's trading behavior.

    Excludes name/description/version so cosmetic edits don't change the
    hash. Matches the convention used by the autoresearch loop.
    """
    config_str = strategy.model_dump_json(exclude={"name", "description", "version"})
    return hashlib.sha256(config_str.encode()).hexdigest()[:12]


def window_metrics(result: BacktestResult, start: datetime, end: datetime) -> WindowMetrics:
    """Slice a backtest result to [start, end] and recompute key metrics.

    Sharpe follows the engine's convention: only returns from days where a
    position was held (reconstructed from trade entry/exit spans), annualized
    by sqrt(252). Drawdown peaks reset at the window start.
    """
    dates = result.equity_dates
    idx = [i for i, d in enumerate(dates) if start <= d <= end]
    years = max((end - start).days / 365.25, 1 / 365.25)

    trades = [t for t in result.trades if start <= t.exit_time <= end]
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

    equity = np.array([result.equity_curve[i] for i in idx])
    window_dates = [dates[i] for i in idx]

    total_return = equity[-1] / equity[0] - 1 if equity[0] > 0 else 0.0

    peak = np.maximum.accumulate(equity)
    max_drawdown = float(np.max((peak - equity) / peak)) if np.all(peak > 0) else 0.0

    daily_returns = np.diff(equity) / equity[:-1]
    held = np.array(
        [any(t.entry_time <= d <= t.exit_time for t in result.trades) for d in window_dates[1:]]
    )
    active = daily_returns[held] if held.any() else daily_returns
    if len(active) > 1 and np.std(active) > 0:
        sharpe = float(np.mean(active) / np.std(active) * np.sqrt(TRADING_DAYS))
    else:
        sharpe = 0.0

    return WindowMetrics(
        start=start,
        end=end,
        years=years,
        trades=len(trades),
        win_rate=win_rate,
        total_return=total_return,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
    )


def kill_verdict(
    m: WindowMetrics,
    *,
    min_trades_per_year: float = MIN_TRADES_PER_YEAR,
    max_drawdown: float = MAX_DRAWDOWN,
    max_sharpe: float = MAX_SHARPE,
) -> list[str]:
    """Apply the kill filter to windowed metrics.

    Returns:
        Failure reasons; empty list means the window PASSES.
    """
    reasons: list[str] = []
    min_trades = math.ceil(min_trades_per_year * m.years)
    if m.trades < min_trades:
        reasons.append(f"trades {m.trades}<{min_trades}")
    if m.max_drawdown > max_drawdown:
        reasons.append(f"DD {m.max_drawdown:.0%}>{max_drawdown:.0%}")
    if m.sharpe > max_sharpe:
        reasons.append(f"Sharpe {m.sharpe:.2f}>{max_sharpe:.1f}")
    return reasons
