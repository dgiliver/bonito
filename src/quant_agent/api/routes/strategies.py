"""Strategy management endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from quant_agent.storage.strategies import StrategyStore

router = APIRouter()


class StrategyCreate(BaseModel):
    """Request body for creating a strategy."""

    config: dict[str, Any]
    tags: list[str] = []


class StrategyUpdate(BaseModel):
    """Request body for updating a strategy."""

    tags: list[str] | None = None


@router.get("")
async def list_strategies(
    tags: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List all saved strategies.

    Args:
        tags: Comma-separated tags to filter by
        limit: Max number of results
    """
    store = StrategyStore()
    tag_list = tags.split(",") if tags else None
    strategies = store.list(tags=tag_list)[:limit]

    return {
        "strategies": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "tags": s.tags,
                "updated_at": s.updated_at.isoformat(),
                "last_backtest": {
                    "symbol": s.last_backtest.symbol,
                    "total_return": s.last_backtest.total_return,
                    "sharpe_ratio": s.last_backtest.sharpe_ratio,
                    "max_drawdown": s.last_backtest.max_drawdown,
                }
                if s.last_backtest
                else None,
            }
            for s in strategies
        ],
        "count": len(strategies),
    }


@router.get("/{name}")
async def get_strategy(name: str) -> dict[str, Any]:
    """Get a strategy by name."""
    store = StrategyStore()
    record = store.load(name)

    if record is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    return {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "version": record.version,
        "tags": record.tags,
        "config": record.config.model_dump(),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "last_backtest": {
            "symbol": record.last_backtest.symbol,
            "period": record.last_backtest.period,
            "total_return": record.last_backtest.total_return,
            "sharpe_ratio": record.last_backtest.sharpe_ratio,
            "max_drawdown": record.last_backtest.max_drawdown,
            "total_trades": record.last_backtest.total_trades,
            "win_rate": record.last_backtest.win_rate,
            "run_at": record.last_backtest.run_at.isoformat(),
        }
        if record.last_backtest
        else None,
    }


@router.post("")
async def create_strategy(body: StrategyCreate) -> dict[str, Any]:
    """Create a new strategy from config."""
    from quant_agent.backtest.strategy import StrategyConfig

    try:
        strategy = StrategyConfig(**body.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid strategy config: {e}") from None

    store = StrategyStore()
    record = store.save(strategy, tags=body.tags)

    return {
        "id": record.id,
        "name": record.name,
        "version": record.version,
        "message": f"Strategy '{record.name}' created",
    }


@router.delete("/{name}")
async def delete_strategy(name: str) -> dict[str, str]:
    """Delete a strategy."""
    store = StrategyStore()

    if not store.delete(name):
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    return {"status": "deleted", "name": name}


@router.get("/search/{query}")
async def search_strategies(query: str, limit: int = 10) -> dict[str, Any]:
    """Search strategies by name/description."""
    store = StrategyStore()
    results = store.search(query)[:limit]

    return {
        "query": query,
        "results": [
            {
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "last_backtest": {
                    "total_return": s.last_backtest.total_return,
                    "sharpe_ratio": s.last_backtest.sharpe_ratio,
                }
                if s.last_backtest
                else None,
            }
            for s in results
        ],
        "count": len(results),
    }
