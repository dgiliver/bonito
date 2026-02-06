"""Trading API endpoints for bot management."""

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from bonito.trading.alpaca_broker import AlpacaBroker
from bonito.trading.bot import TradingBot
from bonito.trading.bot_registry import BotRegistry
from bonito.trading.credential_store import CredentialStore
from bonito.trading.credential_validator import CredentialValidator
from bonito.trading.credentials import AlpacaCredentials
from bonito.trading.models import BotConfig, ExecutionModel, TradingConfig
from bonito.trading.risk import calculate_risk_score, should_require_acknowledgment

logger = logging.getLogger(__name__)

# Initialize credential store with password from environment
# In development, use a default password. In production, MUST set BONITO_CREDENTIAL_PASSWORD
_CREDENTIAL_PASSWORD = os.environ.get("BONITO_CREDENTIAL_PASSWORD", "dev-password-change-in-prod")
_credential_store = CredentialStore()

# Cache for account info (not credentials)
_account_info: dict | None = None


def get_credentials() -> AlpacaCredentials | None:
    """Get stored credentials from encrypted store or environment."""
    # Try loading from encrypted store first
    credentials = _credential_store.load_credentials(_CREDENTIAL_PASSWORD)
    if credentials:
        return credentials

    # Fallback to environment variables (for backward compatibility)
    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")
    is_paper = bool(
        os.environ.get("ALPACA_PAPER_API_KEY")
        or os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    )

    if api_key and secret_key:
        try:
            return AlpacaCredentials(
                api_key=api_key,
                secret_key=secret_key,
                is_paper=is_paper,
            )
        except ValueError:
            return None
    return None


router = APIRouter(prefix="/api/trading", tags=["trading"])


# Request/Response Models
class DeployBotRequest(BaseModel):
    """Request to deploy a new trading bot."""

    strategy_name: str
    strategy_config: dict
    mode: Literal["paper", "live"] = "paper"
    execution_model: Literal["scheduled", "continuous", "event_driven"]
    schedule: str | None = None
    max_position_pct: float = Field(default=10.0, ge=0.1, le=100.0)
    max_daily_loss_pct: float | None = Field(default=None, ge=0.1, le=100.0)
    acknowledge_risks: bool = False


class DeployBotResponse(BaseModel):
    """Response from deploying a bot."""

    bot_id: str
    name: str
    status: str
    mode: str
    risk_score: str
    risk_warnings: list[str]


class BotSummary(BaseModel):
    """Summary of a trading bot."""

    id: str
    name: str
    status: str
    mode: str
    strategy: str
    total_trades: int
    realized_pnl: float
    unrealized_pnl: float


class BotListResponse(BaseModel):
    """Response from listing bots."""

    total: int
    bots: list[BotSummary]


class BotDetailResponse(BaseModel):
    """Detailed bot information."""

    id: str
    name: str
    status: str
    mode: str
    strategy: str
    broker_connected: bool
    start_time: str
    positions: list[dict]
    pending_orders: list[dict]
    performance: dict
    risk: dict


class ModifyBotRequest(BaseModel):
    """Request to modify bot configuration."""

    max_position_pct: float | None = None
    max_daily_loss_pct: float | None = None


class LinkAccountRequest(BaseModel):
    """Request to link Alpaca account."""

    api_key: str
    secret_key: str
    is_paper: bool = True


class AccountInfoResponse(BaseModel):
    """Response with account info (no secrets)."""

    linked: bool
    account_id: str | None = None
    account_type: str | None = None
    buying_power: float | None = None
    api_key_preview: str | None = None


# Bot Management Endpoints
@router.post("/bots", response_model=DeployBotResponse, status_code=status.HTTP_201_CREATED)
async def deploy_bot(request: DeployBotRequest):
    """Deploy a new trading bot."""
    # Load credentials from store
    credentials = get_credentials()
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No credentials linked. Please link your Alpaca account first.",
        )

    # Create trading config
    trading_config = TradingConfig(
        mode=request.mode,
        execution_model=ExecutionModel(request.execution_model),
        schedule=request.schedule,
        max_position_pct=request.max_position_pct,
        max_daily_loss_pct=request.max_daily_loss_pct,
    )

    # Create bot config
    bot_config = BotConfig(
        id=str(uuid.uuid4()),
        name=f"{request.strategy_name}_bot",
        strategy_name=request.strategy_name,
        strategy_config=request.strategy_config,
        trading_config=trading_config,
        created_at=datetime.now(UTC),
    )

    # Calculate risk
    risk_score, warnings = calculate_risk_score(bot_config)
    bot_config.risk_score = risk_score
    bot_config.risk_warnings = warnings

    # Check if acknowledgment required
    if should_require_acknowledgment(risk_score) and not request.acknowledge_risks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Risk acknowledgment required",
                "risk_score": risk_score,
                "warnings": warnings,
                "message": "Set acknowledge_risks=true to proceed",
            },
        )

    # Create broker with real credentials
    broker = AlpacaBroker(
        api_key=credentials.api_key.get_secret_value(),
        secret_key=credentials.secret_key.get_secret_value(),
        mode=trading_config.mode,
    )

    # Create and register bot
    bot = TradingBot(bot_config, broker)
    registry = BotRegistry()
    registry.register(bot)

    # Start bot
    await bot.start()

    return DeployBotResponse(
        bot_id=bot_config.id,
        name=bot_config.name,
        status=bot.status,
        mode=trading_config.mode,
        risk_score=risk_score,
        risk_warnings=warnings,
    )


@router.get("/bots", response_model=BotListResponse)
async def list_bots(status_filter: str = "all"):
    """List all trading bots."""
    registry = BotRegistry()
    bots = registry.list_all() if status_filter == "all" else registry.list_by_status(status_filter)

    summaries = []
    for bot in bots:
        state = bot.get_deployed_bot_state()
        summaries.append(
            BotSummary(
                id=state.id,
                name=state.config.name,
                status=state.status,
                mode=state.config.trading_config.mode,
                strategy=state.config.strategy_name,
                total_trades=state.total_trades,
                realized_pnl=state.realized_pnl,
                unrealized_pnl=state.unrealized_pnl,
            )
        )

    return BotListResponse(total=len(summaries), bots=summaries)


@router.get("/bots/{bot_id}", response_model=BotDetailResponse)
async def get_bot(bot_id: str):
    """Get detailed bot information."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot {bot_id} not found")

    state = bot.get_deployed_bot_state()

    return BotDetailResponse(
        id=state.id,
        name=state.config.name,
        status=state.status,
        mode=state.config.trading_config.mode,
        strategy=state.config.strategy_name,
        broker_connected=state.broker_connected,
        start_time=state.start_time.isoformat(),
        positions=[p.model_dump() for p in state.open_positions],
        pending_orders=[o.model_dump() for o in state.pending_orders],
        performance={
            "total_trades": state.total_trades,
            "realized_pnl": state.realized_pnl,
            "unrealized_pnl": state.unrealized_pnl,
            "daily_pnl": state.daily_pnl,
            "current_equity": state.current_equity,
        },
        risk={
            "score": state.config.risk_score,
            "warnings": state.config.risk_warnings,
        },
    )


@router.put("/bots/{bot_id}")
async def modify_bot(bot_id: str, request: ModifyBotRequest):
    """Modify bot configuration."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot {bot_id} not found")

    modified = []
    if request.max_position_pct is not None:
        bot.config.trading_config.max_position_pct = request.max_position_pct
        modified.append("max_position_pct")

    if request.max_daily_loss_pct is not None:
        bot.config.trading_config.max_daily_loss_pct = request.max_daily_loss_pct
        modified.append("max_daily_loss_pct")

    # Recalculate risk
    risk_score, warnings = calculate_risk_score(bot.config)
    bot.config.risk_score = risk_score
    bot.config.risk_warnings = warnings

    return {
        "bot_id": bot_id,
        "modified": modified,
        "new_risk_score": risk_score,
    }


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str, close_positions: bool = False):
    """Stop and remove a bot."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot {bot_id} not found")

    await bot.stop(close_positions=close_positions)
    registry.unregister(bot_id)

    return {"bot_id": bot_id, "status": "stopped", "positions_closed": close_positions}


@router.post("/bots/{bot_id}/pause")
async def pause_bot(bot_id: str):
    """Pause a running bot."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    try:
        await bot.pause()
        return {"bot_id": bot_id, "status": bot.status}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/bots/{bot_id}/resume")
async def resume_bot(bot_id: str):
    """Resume a paused bot."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    try:
        await bot.resume()
        return {"bot_id": bot_id, "status": bot.status}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str, close_positions: bool = False):
    """Stop a bot (keep in registry)."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    await bot.stop(close_positions=close_positions)
    return {"bot_id": bot_id, "status": bot.status, "positions_closed": close_positions}


# Position and Trade Endpoints
@router.get("/bots/{bot_id}/positions")
async def get_positions(bot_id: str):
    """Get current positions for a bot."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    state = bot.get_deployed_bot_state()
    return {"positions": [p.model_dump() for p in state.open_positions]}


@router.get("/bots/{bot_id}/trades")
async def get_trades(bot_id: str, limit: int = 50):
    """Get trade history for a bot."""
    registry = BotRegistry()
    bot = registry.get(bot_id)

    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    # TODO: Implement trade history storage
    return {"trades": [], "total": 0}


# Account Endpoints
@router.get("/account", response_model=AccountInfoResponse)
async def get_account():
    """Get linked Alpaca account info."""
    global _account_info

    # Check for cached account info first
    if _account_info:
        return AccountInfoResponse(**_account_info)

    # Try to load credentials
    credentials = get_credentials()
    if not credentials:
        return AccountInfoResponse(linked=False)

    # Validate and cache account info
    try:
        validator = CredentialValidator()
        result = await validator.validate_and_test(credentials)

        if result.valid:
            _account_info = {
                "linked": True,
                "account_id": result.account_id,
                "account_type": result.account_type,
                "buying_power": result.buying_power,
                "api_key_preview": credentials.get_redacted_display(),
            }
            return AccountInfoResponse(**_account_info)
    except Exception:
        logger.debug("No stored credentials found")

    return AccountInfoResponse(linked=False)


@router.post("/account/link", response_model=AccountInfoResponse)
async def link_account(request: LinkAccountRequest):
    """Link an Alpaca account."""
    global _account_info

    try:
        # Create credentials (validation happens in Pydantic)
        credentials = AlpacaCredentials(
            api_key=request.api_key,
            secret_key=request.secret_key,
            is_paper=request.is_paper,
        )

        # Validate against API
        validator = CredentialValidator()
        result = await validator.validate_and_test(credentials)

        if not result.valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)

        # Store credentials in encrypted store
        _credential_store.store_credentials(credentials, _CREDENTIAL_PASSWORD)

        # Cache account info
        _account_info = {
            "linked": True,
            "account_id": result.account_id,
            "account_type": result.account_type,
            "buying_power": result.buying_power,
            "api_key_preview": credentials.get_redacted_display(),
        }

        return AccountInfoResponse(**_account_info)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.delete("/account/link")
async def unlink_account():
    """Unlink the Alpaca account."""
    global _account_info

    # Delete from encrypted store
    deleted = _credential_store.delete_credentials()

    # Clear cached account info
    _account_info = None

    return {"unlinked": deleted}
