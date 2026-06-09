"""Paper trading ledger — simulates the Robinhood Agentic account.

The ledger is a plain JSON file committed to the repo so state survives
ephemeral Claude sessions. It mirrors how live execution behaves:
dollar-based buys (fractional shares), full-position sells, cash-account
semantics (no margin, no shorts).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from .signals import TradeIntent

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = Path("livetrade/paper_ledger.json")


def ledger_path_for_mode(mode: str) -> Path:
    """Paper and live bookkeeping never share a file."""
    return Path(f"livetrade/{mode}_ledger.json")


class PaperFill(BaseModel):
    """An executed (simulated) order."""

    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    notional: float
    reason: str
    filled_at: datetime
    strategy_name: str = ""


class PaperPosition(BaseModel):
    """An open simulated position."""

    symbol: str
    quantity: float
    entry_price: float
    entry_date: datetime
    high_water_mark: float = Field(
        ..., description="Highest price seen since entry (drives trailing stops)"
    )
    strategy_name: str = Field(
        default="", description="Strategy that opened this position (audit trail)"
    )


class PaperLedger(BaseModel):
    """Full paper account state."""

    cash: float
    starting_cash: float
    positions: dict[str, PaperPosition] = Field(default_factory=dict)
    fills: list[PaperFill] = Field(default_factory=list)
    realized_pnl: float = 0.0
    updated_at: datetime | None = None

    _path: Path | None = PrivateAttr(default=None)

    @classmethod
    def load(cls, path: Path = DEFAULT_LEDGER_PATH) -> "PaperLedger":
        """Load ledger from JSON, or raise FileNotFoundError."""
        ledger = cls.model_validate_json(path.read_text())
        ledger._path = path
        return ledger

    @classmethod
    def load_or_create(
        cls, path: Path = DEFAULT_LEDGER_PATH, starting_cash: float = 150.0
    ) -> "PaperLedger":
        """Load ledger, creating a fresh one if the file doesn't exist."""
        if path.exists():
            return cls.load(path)
        ledger = cls(cash=starting_cash, starting_cash=starting_cash)
        ledger._path = path
        return ledger

    def save(self, path: Path | None = None) -> None:
        """Persist ledger to JSON (defaults to wherever it was loaded from)."""
        target = path or self._path or DEFAULT_LEDGER_PATH
        self.updated_at = datetime.now(UTC)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.model_dump_json(indent=2))

    def equity(self, prices: dict[str, float]) -> float:
        """Total account value at the given prices.

        Positions missing from `prices` are valued at entry price.
        """
        value = self.cash
        for symbol, pos in self.positions.items():
            value += pos.quantity * prices.get(symbol, pos.entry_price)
        return value

    def apply_buy(self, intent: TradeIntent, fill_price: float) -> PaperFill:
        """Execute a dollar-based buy at fill_price.

        Raises:
            ValueError: on insufficient cash, existing position, or bad intent.
        """
        if intent.side != "buy":
            raise ValueError(f"apply_buy got a {intent.side} intent")
        if intent.dollar_amount is None or intent.dollar_amount <= 0:
            raise ValueError("buy intent requires a positive dollar_amount")
        if intent.symbol in self.positions:
            raise ValueError(f"position already open in {intent.symbol}")
        if intent.dollar_amount > self.cash + 1e-9:
            raise ValueError(
                f"insufficient cash: need ${intent.dollar_amount:.2f}, have ${self.cash:.2f}"
            )
        if fill_price <= 0:
            raise ValueError(f"invalid fill price {fill_price}")

        quantity = intent.dollar_amount / fill_price
        self.cash -= intent.dollar_amount
        now = datetime.now(UTC)
        self.positions[intent.symbol] = PaperPosition(
            symbol=intent.symbol,
            quantity=quantity,
            entry_price=fill_price,
            entry_date=now,
            high_water_mark=fill_price,
            strategy_name=intent.strategy_name,
        )
        fill = PaperFill(
            symbol=intent.symbol,
            side="buy",
            quantity=quantity,
            price=fill_price,
            notional=intent.dollar_amount,
            reason=intent.reason,
            filled_at=now,
            strategy_name=intent.strategy_name,
        )
        self.fills.append(fill)
        logger.info(
            f"Paper BUY {intent.symbol}: {quantity:.4f} @ ${fill_price:.2f} "
            f"(${intent.dollar_amount:.2f}) — {intent.reason}"
        )
        return fill

    def apply_sell(self, intent: TradeIntent, fill_price: float) -> PaperFill:
        """Close the full position in intent.symbol at fill_price.

        Raises:
            ValueError: if no position is open or the intent is malformed.
        """
        if intent.side != "sell":
            raise ValueError(f"apply_sell got a {intent.side} intent")
        pos = self.positions.get(intent.symbol)
        if pos is None:
            raise ValueError(f"no open position in {intent.symbol}")
        if fill_price <= 0:
            raise ValueError(f"invalid fill price {fill_price}")

        notional = pos.quantity * fill_price
        pnl = (fill_price - pos.entry_price) * pos.quantity
        self.cash += notional
        self.realized_pnl += pnl
        del self.positions[intent.symbol]

        fill = PaperFill(
            symbol=intent.symbol,
            side="sell",
            quantity=pos.quantity,
            price=fill_price,
            notional=notional,
            reason=intent.reason,
            filled_at=datetime.now(UTC),
            strategy_name=intent.strategy_name or pos.strategy_name,
        )
        self.fills.append(fill)
        logger.info(
            f"Paper SELL {intent.symbol}: {pos.quantity:.4f} @ ${fill_price:.2f} "
            f"(P&L ${pnl:+.2f}) — {intent.reason}"
        )
        return fill

    def update_high_water_mark(self, symbol: str, price: float) -> None:
        """Record a new high for trailing-stop tracking."""
        pos = self.positions.get(symbol)
        if pos and price > pos.high_water_mark:
            pos.high_water_mark = price

    def summary(self, prices: dict[str, float] | None = None) -> dict:
        """Human-readable account snapshot."""
        prices = prices or {}
        positions = []
        unrealized = 0.0
        for symbol, pos in sorted(self.positions.items()):
            price = prices.get(symbol, pos.entry_price)
            pnl = (price - pos.entry_price) * pos.quantity
            unrealized += pnl
            positions.append(
                {
                    "symbol": symbol,
                    "quantity": round(pos.quantity, 4),
                    "entry_price": round(pos.entry_price, 2),
                    "current_price": round(price, 2),
                    "market_value": round(pos.quantity * price, 2),
                    "unrealized_pnl": round(pnl, 2),
                    "entry_date": pos.entry_date.isoformat(),
                }
            )
        equity = self.equity(prices)
        return {
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "starting_cash": round(self.starting_cash, 2),
            "total_return_pct": round((equity / self.starting_cash - 1) * 100, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "open_positions": positions,
            "total_fills": len(self.fills),
        }
