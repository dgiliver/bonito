"""Weekly cross-sectional momentum rotation over a point-in-time pool.

The strategy family pre-registered in docs/STRATEGY_SEARCH_2026-10.md, as data
(`RotationConfig`) rather than code, per the repo's strategy-as-data rule:

- Signal at the last session of each week (close); execution at the NEXT
  session's open — no look-ahead.
- Pool = point-in-time NASDAQ-100 membership on the signal date, unioned with
  extra symbols that only join from the date they were added (`PointInTimePool`).
- Score = total return from ``lookback_months`` ago to ``skip_months`` ago.
- Hold the top ``top_n`` equal-weight; every signal re-weights to equal weight.
- Trend exit: when the trend symbol (QQQ) closes at/below its SMA on the signal
  date, the target is all cash. No per-position stops (user decision).
- Costs: ``cost_bps`` per unit of traded notional. Long-only, unlevered,
  fractional shares.

Research-only: nothing here is imported by the trading path.
"""

import json
from bisect import bisect_right
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class RotationConfig(BaseModel):
    name: str
    lookback_months: int = Field(12, ge=2)
    skip_months: int = Field(1, ge=0)
    top_n: int = Field(5, ge=1)
    trend_symbol: str = "QQQ"
    trend_sma: int = Field(200, ge=2)
    cost_bps: float = Field(10.0, ge=0)
    min_history_days: int = Field(252, ge=1)


class PointInTimePool:
    """Membership as of a date: latest snapshot on/before it ∪ extras added by then."""

    def __init__(
        self,
        snapshots: dict[date, set[str]],
        additions: dict[str, date] | None = None,
    ) -> None:
        self._dates = sorted(snapshots)
        self._sets = [frozenset(snapshots[d]) for d in self._dates]
        self._additions = dict(additions or {})

    def members(self, on: date) -> set[str]:
        i = bisect_right(self._dates, on) - 1
        base = set(self._sets[i]) if i >= 0 else set()
        return base | {s for s, d in self._additions.items() if d <= on}

    def all_symbols(self) -> set[str]:
        out = set(self._additions)
        for s in self._sets:
            out |= s
        return out

    @classmethod
    def from_files(
        cls,
        membership_json: Path,
        additions_json: Path | None = None,
        renames: dict[str, str] | None = None,
    ) -> "PointInTimePool":
        renames = renames or {}
        raw = json.loads(Path(membership_json).read_text())["snapshots"]
        snaps = {
            date.fromisoformat(d): {renames.get(t, t) for t in v["tickers"]} for d, v in raw.items()
        }
        adds = {}
        if additions_json is not None:
            adds = {
                s: date.fromisoformat(d)
                for s, d in json.loads(Path(additions_json).read_text())["additions"].items()
            }
        return cls(snaps, adds)


class RotationResult(BaseModel):
    config: RotationConfig
    dates: list[date]
    equity: list[float]
    per_symbol_pnl: dict[str, float]
    rebalances: int
    weeks_in_cash: int
    turnover: float = Field(..., description="Total traded notional / average equity")
    holdings: dict[date, list[str]] = Field(
        default_factory=dict, description="Target set at each signal date"
    )


def _signal_days(index: pd.DatetimeIndex) -> set[pd.Timestamp]:
    """Last trading session of each ISO week."""
    iso = index.isocalendar()
    key = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    last = pd.Series(index, index=index).groupby(key.values).max()
    return set(last.values)


def momentum_scores(
    closes: pd.DataFrame, on: pd.Timestamp, symbols: set[str], cfg: RotationConfig
) -> dict[str, float]:
    """Return from ``lookback`` months before ``on`` to ``skip`` months before ``on``.

    Uses the last close at or before each anchor date; a symbol needs a close on
    the signal date and at least ``min_history_days`` sessions of history.
    """
    hist = closes.loc[:on]
    t_far = on - pd.DateOffset(months=cfg.lookback_months)
    t_near = on - pd.DateOffset(months=cfg.skip_months)
    far, near = hist.loc[:t_far], hist.loc[:t_near]
    if far.empty or near.empty:
        return {}
    out: dict[str, float] = {}
    for s in symbols:
        if s not in hist.columns:
            continue
        col = hist[s]
        if pd.isna(col.iloc[-1]) or col.notna().sum() < cfg.min_history_days:
            continue
        p_far = far[s].dropna()
        p_near = near[s].dropna()
        if p_far.empty or p_near.empty or p_far.iloc[-1] <= 0:
            continue
        # The far anchor must be close to the requested date, not a stale price
        # from years earlier (a symbol with a long gap).
        if (t_far - p_far.index[-1]).days > 10:
            continue
        out[s] = float(p_near.iloc[-1] / p_far.iloc[-1] - 1)
    return out


def run_rotation(
    cfg: RotationConfig,
    pool: PointInTimePool,
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    start: date,
    end: date,
    *,
    starting_cash: float = 10_000.0,
    exclude: frozenset[str] = frozenset(),
) -> RotationResult:
    """Simulate the rotation. ``opens``/``closes`` are date-indexed, one column per symbol
    (including the trend symbol); missing prices are NaN."""
    closes = closes.sort_index()
    opens = opens.reindex(index=closes.index, columns=closes.columns)
    trend = closes[cfg.trend_symbol]
    sma = trend.rolling(cfg.trend_sma, min_periods=cfg.trend_sma).mean()
    days = closes.index[(closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))]
    signals = _signal_days(days)

    cash = starting_cash
    shares: dict[str, float] = {}
    last_px: dict[str, float] = {}
    pnl: dict[str, float] = {}
    pending: list[str] | None = None  # target decided at last close, executed at this open
    equity_out: list[float] = []
    traded = 0.0
    rebalances = weeks_cash = 0
    holdings: dict[date, list[str]] = {}
    cost = cfg.cost_bps / 10_000

    for day in days:
        # 1) execute yesterday's signal at today's open
        if pending is not None:
            px_open = {}
            for s in set(shares) | set(pending):
                o = opens.at[day, s] if s in opens.columns else np.nan
                if pd.isna(o):
                    o = last_px.get(s, np.nan)  # no open (halt/delisting): last known close
                px_open[s] = float(o)
            # mark held names from last close to this open (gap attribution)
            for s, q in shares.items():
                if not np.isnan(px_open[s]):
                    pnl[s] = pnl.get(s, 0.0) + q * (px_open[s] - last_px[s])
                    last_px[s] = px_open[s]
            equity_open = cash + sum(q * last_px[s] for s, q in shares.items())
            tradable = [s for s in pending if not np.isnan(px_open[s])]
            target_val = equity_open / len(tradable) if tradable else 0.0
            new_shares: dict[str, float] = {}
            for s in tradable:
                new_shares[s] = target_val / px_open[s]
            notional = 0.0
            for s in set(shares) | set(new_shares):
                px = px_open[s] if not np.isnan(px_open[s]) else last_px.get(s, 0.0)
                notional += abs(new_shares.get(s, 0.0) - shares.get(s, 0.0)) * px
            fee = notional * cost
            # charge the fee pro rata to the names traded, so attribution sums to P&L
            for s in set(shares) | set(new_shares):
                px = px_open[s] if not np.isnan(px_open[s]) else last_px.get(s, 0.0)
                share = abs(new_shares.get(s, 0.0) - shares.get(s, 0.0)) * px
                if notional > 0:
                    pnl[s] = pnl.get(s, 0.0) - fee * share / notional
            invested = sum(new_shares[s] * px_open[s] for s in new_shares)
            cash = equity_open - invested - fee
            shares = new_shares
            for s in shares:
                last_px[s] = px_open[s]
            traded += notional
            rebalances += 1
            pending = None

        # 2) mark at close
        for s, q in shares.items():
            c = closes.at[day, s] if s in closes.columns else np.nan
            if not pd.isna(c):
                pnl[s] = pnl.get(s, 0.0) + q * (float(c) - last_px[s])
                last_px[s] = float(c)
        equity_out.append(cash + sum(q * last_px[s] for s, q in shares.items()))

        # 3) decide at this close (executed next session)
        if day in signals and day != days[-1]:
            trend_ok = not pd.isna(sma.at[day]) and trend.at[day] > sma.at[day]
            if not trend_ok:
                target: list[str] = []
                weeks_cash += 1
            else:
                members = pool.members(day.date()) - set(exclude) - {cfg.trend_symbol}
                scores = momentum_scores(closes, day, members, cfg)
                target = sorted(scores, key=lambda s: (-scores[s], s))[: cfg.top_n]
            holdings[day.date()] = target
            if sorted(target) != sorted(shares) or target:
                pending = target

    avg_eq = float(np.mean(equity_out)) if equity_out else starting_cash
    return RotationResult(
        config=cfg,
        dates=[d.date() for d in days],
        equity=[round(e, 6) for e in equity_out],
        per_symbol_pnl={s: round(v, 2) for s, v in pnl.items()},
        rebalances=rebalances,
        weeks_in_cash=weeks_cash,
        turnover=round(traded / avg_eq, 3) if avg_eq else 0.0,
        holdings=holdings,
    )
