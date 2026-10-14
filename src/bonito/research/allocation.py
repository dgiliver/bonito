"""Target-weight allocation simulator + the trend-timed QQQ leverage family.

Pre-registered in docs/STRATEGY_SEARCH_2026-10b_TREND_LEVERAGE.md. Conventions are
the ones reviewed for `rotation.py`:

- Decide at the last session of each ISO week (that day's close); execute at the
  NEXT session's open, rebalancing exactly to the target weights.
- Sessions = the trend symbol's real trading days (stray rows can't create
  sessions or poison its SMA).
- A HELD symbol with no open is valued/sold at its last close; a symbol being
  newly bought with no open is skipped (its weight stays in cash) — never filled
  at a stale price.
- ``cost_bps`` per unit of traded notional.

Research-only: not imported by the trading path.
"""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from bonito.research.rotation import _signal_days

Weights = dict[str, float]


class AllocationResult(BaseModel):
    name: str
    dates: list[date]
    equity: list[float]
    rebalances: int
    turnover: float = Field(..., description="Total traded notional / average equity")
    targets: dict[date, Weights] = Field(default_factory=dict)


def run_allocation(
    name: str,
    decide: Callable[[pd.Timestamp], Weights],
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    start: date,
    end: date,
    *,
    calendar_symbol: str = "QQQ",
    cost_bps: float = 10.0,
    starting_cash: float = 10_000.0,
) -> AllocationResult:
    """Simulate weekly target weights. ``decide(day)`` must only use data up to
    ``day``'s close; weights are fractions of equity (sum ≤ 1, remainder is cash)."""
    closes = closes.sort_index()
    opens = opens.reindex(index=closes.index, columns=closes.columns)
    sessions = closes[calendar_symbol].dropna().index
    days = sessions[(sessions >= pd.Timestamp(start)) & (sessions <= pd.Timestamp(end))]
    signals = _signal_days(days)
    cost = cost_bps / 10_000

    cash = starting_cash
    shares: dict[str, float] = {}
    last_px: dict[str, float] = {}
    pending: Weights | None = None
    equity_out: list[float] = []
    traded = 0.0
    rebalances = 0
    targets: dict[date, Weights] = {}

    for day in days:
        if pending is not None:
            px_open: dict[str, float] = {}
            for s in set(shares) | set(pending):
                o = opens.at[day, s] if s in opens.columns else np.nan
                if pd.isna(o) and s in shares:
                    o = last_px[s]
                px_open[s] = float(o)
            for s in shares:
                if not np.isnan(px_open[s]):
                    last_px[s] = px_open[s]
            equity_open = cash + sum(q * last_px[s] for s, q in shares.items())
            new_shares = {
                s: w * equity_open / px_open[s]
                for s, w in pending.items()
                if w > 0 and not np.isnan(px_open[s])
            }
            notional = sum(
                abs(new_shares.get(s, 0.0) - shares.get(s, 0.0))
                * (px_open[s] if not np.isnan(px_open[s]) else last_px.get(s, 0.0))
                for s in set(shares) | set(new_shares)
            )
            fee = notional * cost
            invested = sum(q * px_open[s] for s, q in new_shares.items())
            cash = equity_open - invested - fee
            for s in set(shares) - set(new_shares):
                last_px.pop(s, None)
            shares = new_shares
            for s in shares:
                last_px[s] = px_open[s]
            traded += notional
            rebalances += 1
            pending = None

        for s in shares:
            c = closes.at[day, s] if s in closes.columns else np.nan
            if not pd.isna(c):
                last_px[s] = float(c)
        equity_out.append(cash + sum(q * last_px[s] for s, q in shares.items()))

        if day in signals and day != days[-1]:
            target = {s: w for s, w in decide(day).items() if w > 0}
            if sum(target.values()) > 1 + 1e-9:
                raise ValueError(f"weights sum to {sum(target.values()):.3f} > 1 on {day.date()}")
            targets[day.date()] = target
            if target or shares:
                pending = target

    avg_eq = float(np.mean(equity_out)) if equity_out else starting_cash
    return AllocationResult(
        name=name,
        dates=[d.date() for d in days],
        equity=[round(e, 6) for e in equity_out],
        rebalances=rebalances,
        turnover=round(traded / avg_eq, 3) if avg_eq else 0.0,
        targets=targets,
    )


# --- the pre-registered trend-timed leverage family ---------------------------------

VARIANTS: dict[str, tuple[Weights, Weights]] = {
    # name: (weights when QQQ > SMA, weights when QQQ <= SMA)
    "L2-QQQ": ({"QLD": 1.0}, {"QQQ": 1.0}),
    "L2-CASH": ({"QLD": 1.0}, {}),
    "L15-CASH": ({"QLD": 0.5, "QQQ": 0.5}, {}),
    "L3-CASH": ({"TQQQ": 1.0}, {}),
}


def trend_decider(
    closes: pd.DataFrame, variant: str, sma_period: int = 200, trend_symbol: str = "QQQ"
) -> Callable[[pd.Timestamp], Weights]:
    """Weights for ``variant`` from trend_symbol's close vs its SMA on the signal day.

    The SMA is computed on the trend symbol's real sessions; an undefined SMA (not
    enough history) reads as "not above" — the defensive leg.
    """
    above, below = VARIANTS[variant]
    trend = closes[trend_symbol].dropna()
    sma = trend.rolling(sma_period, min_periods=sma_period).mean()

    def decide(day: pd.Timestamp) -> Weights:
        up = day in sma.index and not pd.isna(sma.at[day]) and trend.at[day] > sma.at[day]
        return dict(above if up else below)

    return decide
