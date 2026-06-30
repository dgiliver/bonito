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

from bonito.backtest.strategy import StrategyConfig

from .signals import TradeIntent
from .validation import strategy_hash

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
    broker_order_id: str | None = None


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
    strategy_hash: str = Field(
        default="", description="Content hash of the strategy that opened this position"
    )
    strategy_config: dict | None = Field(
        default=None,
        description="Pinned strategy snapshot — the position is managed by the exact "
        "config that opened it until exit, even if the deployed strategy changes",
    )

    def pinned_strategy(self) -> StrategyConfig | None:
        """The exact strategy config that opened this position, if pinned."""
        if self.strategy_config is None:
            return None
        return StrategyConfig(**self.strategy_config)


class PaperLedger(BaseModel):
    """Full paper account state."""

    cash: float
    starting_cash: float
    positions: dict[str, PaperPosition] = Field(default_factory=dict)
    fills: list[PaperFill] = Field(default_factory=list)
    realized_pnl: float = 0.0
    peak_equity: float | None = Field(
        default=None, description="Highest marked equity seen (drives the kill switch)"
    )
    halted: bool = Field(
        default=False,
        description="Kill switch: no new entries until a human runs `bonito live resume`",
    )
    halt_reason: str = ""
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

    def apply_buy(
        self,
        intent: TradeIntent,
        fill_price: float,
        strategy: StrategyConfig | None = None,
        *,
        fill_quantity: float | None = None,
    ) -> PaperFill:
        """Execute a dollar-based buy at fill_price.

        Args:
            strategy: When given, pinned to the position — exits use this
                exact config until the position closes (lock-until-exit).
            fill_quantity: Actual shares filled by the broker (D3).  When
                provided the position is opened at this exact quantity;
                ``intent.dollar_amount`` still governs the cash debit so the
                notional accounting stays consistent.  Must be > 0.
                When None (default) the quantity is derived from
                ``intent.dollar_amount / fill_price`` — byte-identical to
                the original behaviour.

        Raises:
            ValueError: on insufficient cash, existing position, halted
                ledger, bad intent, or non-positive fill_quantity.
        """
        if intent.side != "buy":
            raise ValueError(f"apply_buy got a {intent.side} intent")
        if self.halted:
            raise ValueError(f"ledger is halted ({self.halt_reason}); no new entries")
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
        if fill_quantity is not None and fill_quantity <= 0:
            raise ValueError(f"fill_quantity must be positive, got {fill_quantity}")

        quantity = fill_quantity if fill_quantity is not None else intent.dollar_amount / fill_price
        self.cash -= intent.dollar_amount
        now = datetime.now(UTC)
        self.positions[intent.symbol] = PaperPosition(
            symbol=intent.symbol,
            quantity=quantity,
            entry_price=fill_price,
            entry_date=now,
            high_water_mark=fill_price,
            strategy_name=intent.strategy_name,
            strategy_hash=strategy_hash(strategy) if strategy else "",
            strategy_config=strategy.model_dump(mode="json") if strategy else None,
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
            broker_order_id=intent.broker_order_id,
        )
        self.fills.append(fill)
        logger.info(
            f"Paper BUY {intent.symbol}: {quantity:.4f} @ ${fill_price:.2f} "
            f"(${intent.dollar_amount:.2f}) — {intent.reason}"
        )
        return fill

    def apply_sell(
        self,
        intent: TradeIntent,
        fill_price: float,
        *,
        fill_quantity: float | None = None,
    ) -> PaperFill:
        """Close (or partially close) the position in intent.symbol at fill_price.

        Args:
            fill_quantity: Actual shares sold by the broker (D3).  When
                provided and less than the full position (minus dust), a
                partial exit is recorded: PnL and cash are adjusted for
                the sold quantity only and the remaining position is kept
                at the original entry_price.  When >= pos.quantity (within
                dust) the position is fully closed (existing behaviour).
                When None (default) the full position is closed —
                byte-identical to the original behaviour.

        Raises:
            ValueError: if no position is open or the intent is malformed.
        """
        dust = 1e-4
        if intent.side != "sell":
            raise ValueError(f"apply_sell got a {intent.side} intent")
        pos = self.positions.get(intent.symbol)
        if pos is None:
            raise ValueError(f"no open position in {intent.symbol}")
        if fill_price <= 0:
            raise ValueError(f"invalid fill price {fill_price}")

        # Determine sold quantity: full close when fill_quantity is None or covers the whole position.
        sold_qty: float
        full_close: bool
        if fill_quantity is None or fill_quantity >= pos.quantity - dust:
            sold_qty = pos.quantity
            full_close = True
        else:
            sold_qty = fill_quantity
            full_close = False

        notional = sold_qty * fill_price
        pnl = (fill_price - pos.entry_price) * sold_qty
        self.cash += notional
        self.realized_pnl += pnl

        if full_close:
            del self.positions[intent.symbol]
        else:
            pos.quantity -= sold_qty  # keep the position open at original entry_price

        fill = PaperFill(
            symbol=intent.symbol,
            side="sell",
            quantity=sold_qty,
            price=fill_price,
            notional=notional,
            reason=intent.reason,
            filled_at=datetime.now(UTC),
            strategy_name=intent.strategy_name or pos.strategy_name,
            broker_order_id=intent.broker_order_id,
        )
        self.fills.append(fill)
        logger.info(
            f"Paper SELL {intent.symbol}: {sold_qty:.4f} @ ${fill_price:.2f} "
            f"(P&L ${pnl:+.2f}{'  partial' if not full_close else ''}) — {intent.reason}"
        )
        return fill

    def record_no_fill(
        self,
        symbol: str,
        side: str,
        reason: str,
        broker_order_id: str | None,
        signal_price: float,
    ) -> "PaperFill":
        """Record an intent that was rejected or did not fill (D3).

        No cash or position change — this is a pure audit event so
        ``bonito live tracking`` can distinguish "chose not to trade" from
        "tried and couldn't fill".  The fill lands in ``self.fills`` with
        ``quantity=0.0`` and ``notional=0.0`` so zero-qty filters can
        exclude it from bps calculations.

        Returns the sentinel PaperFill for the caller to inspect/log.
        """
        now = datetime.now(UTC)
        fill = PaperFill(
            symbol=symbol.upper(),
            side=side,  # type: ignore[arg-type]
            quantity=0.0,
            price=signal_price,
            notional=0.0,
            reason=f"no_fill: {reason}",
            filled_at=now,
            strategy_name="live",
            broker_order_id=broker_order_id,
        )
        self.fills.append(fill)
        logger.info(f"NO FILL recorded {side.upper()} {symbol.upper()} @ ${signal_price:.2f} — {reason}")
        return fill

    def update_high_water_mark(self, symbol: str, price: float) -> None:
        """Record a new high for trailing-stop tracking."""
        pos = self.positions.get(symbol)
        if pos and price > pos.high_water_mark:
            pos.high_water_mark = price

    def note_equity(self, equity: float) -> float:
        """Update the peak-equity watermark and return current drawdown.

        Returns:
            Drawdown from peak as a fraction (0.0 = at peak).
        """
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity
        if self.peak_equity <= 0:
            return 0.0
        return 1 - equity / self.peak_equity

    def halt(self, reason: str) -> None:
        """Trip the kill switch: block all new entries until resume()."""
        self.halted = True
        self.halt_reason = reason
        logger.error(f"LEDGER HALTED: {reason}")

    def resume(self, *, confirm: bool = False) -> None:
        """Clear the kill switch (explicit human action only)."""
        if confirm is not True:
            raise ValueError(
                "PaperLedger.resume() requires confirm=True — kill-switch clearance is a "
                "human-only action (see bonito live resume)"
            )
        self.halted = False
        self.halt_reason = ""

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
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }
