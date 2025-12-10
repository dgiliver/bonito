"""Backtest execution endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bonito.backtest.engine import BacktestEngine
from bonito.backtest.models import BacktestConfig
from bonito.backtest.strategy import StrategyConfig
from bonito.data.store import MarketDataStore
from bonito.storage.strategies import StrategyStore

router = APIRouter()


class BacktestRequest(BaseModel):
    """Request body for running a backtest."""

    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    initial_capital: float = 100000.0
    commission: float = 0.001
    strategy_config: dict[str, Any] | None = None
    strategy_name: str | None = None


class QuickBacktestRequest(BaseModel):
    """Request body for quick backtest with a saved strategy."""

    strategy_name: str
    symbol: str
    days: int = 365
    initial_capital: float = 100000.0


@router.post("/run")
async def run_backtest(request: BacktestRequest) -> dict[str, Any]:
    """Run a backtest with a strategy config or saved strategy.

    Provide either strategy_config (inline JSON) or strategy_name (saved).
    """
    # Load strategy from config or storage
    if request.strategy_config:
        try:
            strategy = StrategyConfig(**request.strategy_config)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid strategy config: {e}") from None
    elif request.strategy_name:
        store = StrategyStore()
        record = store.load(request.strategy_name)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"Strategy '{request.strategy_name}' not found"
            )
        strategy = record.config
    else:
        raise HTTPException(
            status_code=400,
            detail="Either strategy_config or strategy_name is required",
        )

    # Load market data with date parsing
    data_store = MarketDataStore()
    start_dt = (
        datetime.strptime(request.start_date, "%Y-%m-%d")
        if request.start_date
        else datetime(2020, 1, 1)
    )
    end_dt = datetime.strptime(request.end_date, "%Y-%m-%d") if request.end_date else datetime.now()

    bars = data_store.get_bars(
        symbol=request.symbol,
        start=start_dt,
        end=end_dt,
    )

    if bars is None or len(bars) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {request.symbol}. Ingest data first.",
        )

    data_store.close()

    # Create backtest config with actual data dates
    backtest_config = BacktestConfig(
        start_date=bars.timestamps[0],
        end_date=bars.timestamps[-1],
        initial_capital=request.initial_capital,
        commission=request.commission,
        slippage=0.0,
    )

    # Run backtest
    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, bars)

    return {
        "symbol": request.symbol,
        "strategy": strategy.name,
        "period": {
            "start": bars.timestamps[0].isoformat(),
            "end": bars.timestamps[-1].isoformat(),
            "bars": len(bars),
        },
        "performance": {
            "total_return": round(result.metrics.total_return * 100, 2),
            "total_return_pct": f"{result.metrics.total_return * 100:.2f}%",
            "sharpe_ratio": round(result.metrics.sharpe_ratio, 3),
            "max_drawdown": round(result.metrics.max_drawdown * 100, 2),
            "max_drawdown_pct": f"{result.metrics.max_drawdown * 100:.2f}%",
            "win_rate": round(result.metrics.win_rate * 100, 2),
            "win_rate_pct": f"{result.metrics.win_rate * 100:.2f}%",
            "profit_factor": round(result.metrics.profit_factor, 3),
        },
        "trades": {
            "total": result.metrics.total_trades,
            "winning": result.metrics.winning_trades,
            "losing": result.metrics.losing_trades,
        },
        "capital": {
            "initial": request.initial_capital,
            "final": round(result.final_capital, 2),
            "profit": round(result.final_capital - request.initial_capital, 2),
        },
        "trade_log": [
            {
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "side": t.side.value,
                "quantity": t.quantity,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "pnl": round(t.pnl, 2),
                "return_pct": f"{t.pnl_percent * 100:.2f}%",
            }
            for t in result.trades  # All trades (frontend handles virtualization)
        ],
        "equity_curve": [
            {
                "date": result.equity_dates[i].isoformat(),
                "equity": round(result.equity_curve[i], 2),
                "drawdown": round(result.drawdown_curve[i] * 100, 2),
                # Buy & hold benchmark: what if we just held the stock?
                "benchmark": round(request.initial_capital * (bars.closes[i] / bars.closes[0]), 2),
            }
            for i in range(0, len(result.equity_curve), max(1, len(result.equity_curve) // 200))
        ],
    }


@router.post("/quick")
async def quick_backtest(request: QuickBacktestRequest) -> dict[str, Any]:
    """Quick backtest a saved strategy on recent data.

    Simplified endpoint for testing strategies with minimal config.
    """
    # Load strategy
    store = StrategyStore()
    record = store.load(request.strategy_name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{request.strategy_name}' not found")

    # Load market data (all available)
    data_store = MarketDataStore()
    bars = data_store.get_bars(
        symbol=request.symbol,
        start=datetime(2010, 1, 1),
        end=datetime.now(),
    )
    data_store.close()

    if bars is None or len(bars) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {request.symbol}. Ingest data first.",
        )

    # Use last N days of data
    if len(bars) > request.days:
        bars = bars.slice(-request.days)

    # Run backtest
    backtest_config = BacktestConfig(
        start_date=bars.timestamps[0],
        end_date=bars.timestamps[-1],
        initial_capital=request.initial_capital,
        commission=0.001,
        slippage=0.0,
    )
    engine = BacktestEngine(backtest_config)
    result = engine.run(record.config, bars)

    return {
        "strategy": request.strategy_name,
        "symbol": request.symbol,
        "days": len(bars),
        "total_return": f"{result.metrics.total_return * 100:.2f}%",
        "sharpe_ratio": round(result.metrics.sharpe_ratio, 3),
        "max_drawdown": f"{result.metrics.max_drawdown * 100:.2f}%",
        "total_trades": result.metrics.total_trades,
        "win_rate": f"{result.metrics.win_rate * 100:.2f}%",
        "final_capital": round(result.metrics.final_capital, 2),
    }


@router.get("/compare")
async def compare_strategies(
    strategies: str,
    symbol: str,
    days: int = 365,
) -> dict[str, Any]:
    """Compare multiple strategies on the same data.

    Args:
        strategies: Comma-separated strategy names
        symbol: Symbol to backtest on
        days: Number of days of data to use
    """
    strategy_names = [s.strip() for s in strategies.split(",")]

    if len(strategy_names) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 strategies to compare")

    # Load market data once (all available)
    data_store = MarketDataStore()
    bars = data_store.get_bars(
        symbol=symbol,
        start=datetime(2010, 1, 1),
        end=datetime.now(),
    )
    data_store.close()

    if bars is None or len(bars) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {symbol}. Ingest data first.",
        )

    if len(bars) > days:
        bars = bars.slice(-days)

    # Run backtests
    results = []
    store = StrategyStore()
    backtest_config = BacktestConfig(
        start_date=bars.timestamps[0],
        end_date=bars.timestamps[-1],
        initial_capital=100000.0,
        commission=0.001,
    )

    for name in strategy_names:
        record = store.load(name)
        if record is None:
            results.append({"name": name, "error": "Not found"})
            continue

        engine = BacktestEngine(backtest_config)
        result = engine.run(record.config, bars)

        results.append(
            {
                "name": name,
                "total_return": f"{result.metrics.total_return * 100:.2f}%",
                "sharpe_ratio": round(result.metrics.sharpe_ratio, 3),
                "max_drawdown": f"{result.metrics.max_drawdown * 100:.2f}%",
                "total_trades": result.metrics.total_trades,
                "win_rate": f"{result.metrics.win_rate * 100:.2f}%",
            }
        )

    # Sort by return
    valid_results = [r for r in results if "error" not in r]
    valid_results.sort(key=lambda x: float(x["total_return"].replace("%", "")), reverse=True)

    return {
        "symbol": symbol,
        "days": len(bars),
        "comparison": valid_results + [r for r in results if "error" in r],
        "winner": valid_results[0]["name"] if valid_results else None,
    }
