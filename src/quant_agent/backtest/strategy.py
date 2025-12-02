"""Strategy configuration models - the DSL for defining strategies."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class IndicatorType(str, Enum):
    """Available indicator types."""
    
    SMA = "sma"
    EMA = "ema"
    RSI = "rsi"
    MACD = "macd"
    ATR = "atr"
    BBANDS = "bbands"  # Bollinger Bands
    STOCH = "stoch"    # Stochastic


class IndicatorConfig(BaseModel):
    """Configuration for a technical indicator."""
    
    type: IndicatorType
    name: str = Field(..., description="Unique name for this indicator instance")
    params: dict = Field(default_factory=dict, description="Indicator parameters")
    
    model_config = {"extra": "forbid"}


class Comparison(str, Enum):
    """Comparison operators for rules."""
    
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class RuleCondition(BaseModel):
    """A single condition in a rule.
    
    Examples:
        - RSI < 30
        - SMA_20 crosses_above SMA_50
        - close > SMA_200
    """
    
    left: str = Field(..., description="Left operand (indicator name or 'close', 'open', etc.)")
    comparison: Comparison
    right: str | float = Field(
        ..., 
        description="Right operand (indicator name, price field, or numeric value)"
    )


class Rule(BaseModel):
    """A rule combining multiple conditions."""
    
    conditions: list[RuleCondition] = Field(..., min_length=1)
    logic: Literal["AND", "OR"] = Field(default="AND")


class PositionSizeType(str, Enum):
    """Position sizing methods."""
    
    FIXED_QUANTITY = "fixed_quantity"
    FIXED_VALUE = "fixed_value"
    PERCENT_EQUITY = "percent_equity"


class PositionSizeConfig(BaseModel):
    """Position sizing configuration."""
    
    type: PositionSizeType
    value: float = Field(..., description="Size value (quantity, dollars, or percentage)")


class StopLossType(str, Enum):
    """Stop loss types."""
    
    PERCENT = "percent"
    ATR = "atr"
    FIXED = "fixed"


class StopLossConfig(BaseModel):
    """Stop loss configuration."""
    
    type: StopLossType
    value: float = Field(..., description="Stop loss value")


class TakeProfitType(str, Enum):
    """Take profit types."""
    
    PERCENT = "percent"
    ATR = "atr"
    FIXED = "fixed"
    RISK_MULTIPLE = "risk_multiple"  # Multiple of stop loss


class TakeProfitConfig(BaseModel):
    """Take profit configuration."""
    
    type: TakeProfitType
    value: float


class StrategyConfig(BaseModel):
    """Complete strategy configuration.
    
    This is the core DSL that the LLM generates. It's constrained enough
    to be validated and executed safely, while flexible enough to express
    most common strategies.
    """
    
    name: str = Field(..., description="Strategy name")
    description: str = Field(default="", description="Strategy description")
    version: str = Field(default="1.0", description="Strategy version")
    
    # Universe
    symbols: list[str] = Field(..., min_length=1, description="Symbols to trade")
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Field(
        default="1d", description="Bar timeframe"
    )
    
    # Indicators
    indicators: list[IndicatorConfig] = Field(
        default_factory=list, description="Technical indicators to compute"
    )
    
    # Entry/Exit Rules
    entry_rules: list[Rule] = Field(..., min_length=1, description="Entry rules (any can trigger)")
    exit_rules: list[Rule] = Field(default_factory=list, description="Exit rules (any can trigger)")
    
    # Position Management
    position_size: PositionSizeConfig = Field(
        default_factory=lambda: PositionSizeConfig(type=PositionSizeType.PERCENT_EQUITY, value=10)
    )
    max_positions: int = Field(default=1, description="Maximum concurrent positions")
    
    # Risk Management
    stop_loss: StopLossConfig | None = Field(default=None, description="Stop loss configuration")
    take_profit: TakeProfitConfig | None = Field(default=None, description="Take profit configuration")
    
    model_config = {"extra": "forbid"}
    
    def to_prompt_description(self) -> str:
        """Generate a human-readable description for LLM context."""
        lines = [
            f"Strategy: {self.name}",
            f"Description: {self.description}",
            f"Symbols: {', '.join(self.symbols)}",
            f"Timeframe: {self.timeframe}",
            "",
            "Indicators:",
        ]
        
        for ind in self.indicators:
            lines.append(f"  - {ind.name}: {ind.type.value}({ind.params})")
        
        lines.extend(["", "Entry Rules:"])
        for i, rule in enumerate(self.entry_rules, 1):
            conds = [f"{c.left} {c.comparison.value} {c.right}" for c in rule.conditions]
            lines.append(f"  Rule {i}: {f' {rule.logic} '.join(conds)}")
        
        if self.exit_rules:
            lines.extend(["", "Exit Rules:"])
            for i, rule in enumerate(self.exit_rules, 1):
                conds = [f"{c.left} {c.comparison.value} {c.right}" for c in rule.conditions]
                lines.append(f"  Rule {i}: {f' {rule.logic} '.join(conds)}")
        
        lines.extend([
            "",
            f"Position Size: {self.position_size.type.value} = {self.position_size.value}",
        ])
        
        if self.stop_loss:
            lines.append(f"Stop Loss: {self.stop_loss.type.value} = {self.stop_loss.value}")
        if self.take_profit:
            lines.append(f"Take Profit: {self.take_profit.type.value} = {self.take_profit.value}")
        
        return "\n".join(lines)

