"""Persistent strategy storage."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from quant_agent.backtest.models import BacktestResult
from quant_agent.backtest.strategy import StrategyConfig


class BacktestSummary(BaseModel):
    """Cached backtest summary for quick display."""

    symbol: str
    period: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    run_at: datetime

    @classmethod
    def from_result(cls, result: BacktestResult) -> BacktestSummary:
        """Create summary from full backtest result."""
        return cls(
            symbol=result.symbol,
            period=f"{result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}",
            total_return=result.metrics.total_return,
            sharpe_ratio=result.metrics.sharpe_ratio,
            max_drawdown=result.metrics.max_drawdown,
            total_trades=result.metrics.total_trades,
            win_rate=result.metrics.win_rate,
            run_at=datetime.now(),
        )


class StrategyRecord(BaseModel):
    """Persisted strategy with metadata."""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    version: int = 1

    # The actual strategy config
    config: StrategyConfig

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)

    # Performance (cached from last backtest)
    last_backtest: BacktestSummary | None = None


class StrategyStore:
    """Persistent strategy storage using JSON files."""

    def __init__(self, base_dir: Path | str | None = None):
        """Initialize the strategy store.

        Args:
            base_dir: Directory for storing strategies. Defaults to ./strategies/
        """
        if base_dir is None:
            base_dir = Path("strategies")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        strategy: StrategyConfig,
        backtest_result: BacktestResult | None = None,
        tags: list[str] | None = None,
    ) -> StrategyRecord:
        """Save a strategy to disk.

        Args:
            strategy: The strategy configuration
            backtest_result: Optional backtest result to cache
            tags: Optional tags for categorization

        Returns:
            The saved strategy record
        """
        # Check if strategy already exists
        existing = self.load(strategy.name)

        if existing:
            # Update existing
            record = existing
            record.config = strategy
            record.description = strategy.description
            record.updated_at = datetime.now()
            record.version += 1
            if backtest_result:
                record.last_backtest = BacktestSummary.from_result(backtest_result)
            if tags:
                record.tags = tags
        else:
            # Create new
            record = StrategyRecord(
                name=strategy.name,
                description=strategy.description,
                config=strategy,
                tags=tags or [],
                last_backtest=BacktestSummary.from_result(backtest_result)
                if backtest_result
                else None,
            )

        # Save to file
        path = self._get_path(strategy.name)
        path.write_text(record.model_dump_json(indent=2))

        return record

    def load(self, name: str) -> StrategyRecord | None:
        """Load a strategy by name.

        Args:
            name: Strategy name

        Returns:
            Strategy record or None if not found
        """
        path = self._get_path(name)
        if not path.exists():
            return None
        return StrategyRecord.model_validate_json(path.read_text())

    def delete(self, name: str) -> bool:
        """Delete a strategy.

        Args:
            name: Strategy name

        Returns:
            True if deleted, False if not found
        """
        path = self._get_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self, tags: list[str] | None = None) -> list[StrategyRecord]:
        """List all saved strategies.

        Args:
            tags: Optional filter by tags

        Returns:
            List of strategy records, sorted by updated_at descending
        """
        strategies = []
        for path in self.base_dir.glob("*.json"):
            try:
                record = StrategyRecord.model_validate_json(path.read_text())
                if tags is None or any(t in record.tags for t in tags):
                    strategies.append(record)
            except Exception:  # nosec B112 - intentionally skip corrupt strategy files
                continue

        return sorted(strategies, key=lambda s: s.updated_at, reverse=True)

    def search(self, query: str) -> list[StrategyRecord]:
        """Simple text search across strategies.

        Args:
            query: Search query

        Returns:
            Matching strategies
        """
        query_lower = query.lower()
        results = []

        for strategy in self.list():
            # Search in name, description, and tags
            if (
                query_lower in strategy.name.lower()
                or query_lower in strategy.description.lower()
                or any(query_lower in tag.lower() for tag in strategy.tags)
            ):
                results.append(strategy)

        return results

    def get_by_performance(
        self,
        metric: str = "sharpe_ratio",
        limit: int = 10,
    ) -> list[StrategyRecord]:
        """Get top strategies by performance metric.

        Args:
            metric: Metric to sort by (sharpe_ratio, total_return, etc.)
            limit: Max results

        Returns:
            Top performing strategies
        """
        strategies = [s for s in self.list() if s.last_backtest is not None]

        def get_metric(s: StrategyRecord) -> float:
            if s.last_backtest is None:
                return float("-inf")
            return getattr(s.last_backtest, metric, 0)

        return sorted(strategies, key=get_metric, reverse=True)[:limit]

    def _get_path(self, name: str) -> Path:
        """Get file path for a strategy."""
        # Sanitize name for filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.base_dir / f"{safe_name}.json"
