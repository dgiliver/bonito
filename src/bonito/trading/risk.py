"""Risk scoring and warnings for trading configurations."""

from typing import Literal

from .models import BotConfig


def calculate_risk_score(
    config: BotConfig,
) -> tuple[Literal["low", "medium", "high", "extreme"], list[str]]:
    """Calculate risk score and generate warnings."""
    warnings = []
    score_points = 0

    trading_config = config.trading_config
    strategy_config = config.strategy_config

    # Position size warnings
    if trading_config.max_position_pct > 50:
        warnings.append("⚠️ Large position size (>50% of portfolio per trade)")
        score_points += 2
    if trading_config.max_position_pct > 90:
        warnings.append("🚨 Extreme position size (>90% of portfolio per trade)")
        score_points += 3

    # No stop loss
    if not strategy_config.get("stop_loss"):
        warnings.append("⚠️ No stop loss configured - unlimited downside risk")
        score_points += 2

    # No daily loss limit
    if trading_config.max_daily_loss_pct is None:
        warnings.append("⚠️ No daily loss limit - bot won't auto-stop on bad days")
        score_points += 1

    # Live trading
    if trading_config.mode == "live":
        warnings.append("💰 LIVE TRADING - Real money at risk")
        score_points += 2

    # No position limit
    if trading_config.max_positions >= 100:
        warnings.append("⚠️ No position limit - could open many simultaneous positions")
        score_points += 1

    # Determine score
    if score_points >= 6:
        risk_level = "extreme"
    elif score_points >= 4:
        risk_level = "high"
    elif score_points >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    return risk_level, warnings


def should_require_acknowledgment(risk_score: str) -> bool:
    """Check if risk level requires explicit user acknowledgment."""
    return risk_score in ("high", "extreme")
