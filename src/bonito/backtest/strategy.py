"""Strategy configuration models - the DSL for defining strategies."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


class IndicatorType(str, Enum):
    """Built-in indicator types (legacy - maintained for backward compatibility)."""

    SMA = "sma"
    EMA = "ema"
    RSI = "rsi"
    MACD = "macd"
    ATR = "atr"
    BBANDS = "bbands"  # Bollinger Bands
    STOCH = "stoch"  # Stochastic


# List of built-in indicator type values for validation
BUILTIN_INDICATOR_TYPES = {e.value for e in IndicatorType}

# pandas-ta supported indicators (subset of most commonly used)
# Full list: https://github.com/twopirllc/pandas-ta#indicators-by-category
PANDAS_TA_INDICATORS = {
    # Volume
    "vwap",
    "obv",
    "cmf",
    "mfi",
    "ad",
    "adosc",
    "pvol",
    "pvt",
    # Trend
    "adx",
    "aroon",
    "psar",
    "supertrend",
    "vortex",
    # Volatility / Channels
    "donchian",
    "kc",
    "massi",
    "natr",
    "pdist",
    "rvi",
    "ui",
    # Momentum
    "ao",
    "cci",
    "cmo",
    "coppock",
    "fisher",
    "kst",
    "mom",
    "ppo",
    "roc",
    "rsi_pandas",
    "stochrsi",
    "trix",
    "tsi",
    "uo",
    "willr",
    # Overlap
    "dema",
    "ema_pandas",
    "fwma",
    "hma",
    "kama",
    "linreg",
    "midpoint",
    "midprice",
    "pwma",
    "rma",
    "sinwma",
    "sma_pandas",
    "ssf",
    "swma",
    "t3",
    "tema",
    "trima",
    "vidya",
    "vwma",
    "wma",
    "zlma",
    # Statistics
    "entropy",
    "kurtosis",
    "mad",
    "median",
    "quantile",
    "skew",
    "stdev",
    "variance",
    "zscore",
}


def _validate_indicator_type(value: str | IndicatorType) -> str | IndicatorType:
    """Validate indicator type - accepts enum or string for pandas-ta indicators."""
    if isinstance(value, IndicatorType):
        return value

    # Convert string to lowercase for comparison
    str_value = str(value).lower()

    # Check if it's a built-in type
    try:
        return IndicatorType(str_value)
    except ValueError:
        pass

    # Check if it's a valid pandas-ta indicator
    if str_value in PANDAS_TA_INDICATORS:
        return str_value

    # Allow any string for flexibility (pandas-ta has 130+ indicators)
    # The compute_indicators function will raise if truly invalid
    return str_value


# Type that accepts either IndicatorType enum or string for pandas-ta
FlexibleIndicatorType = Annotated[str | IndicatorType, BeforeValidator(_validate_indicator_type)]


class IndicatorConfig(BaseModel):
    """Configuration for a technical indicator.

    Supports both built-in indicators (SMA, EMA, RSI, etc.) and pandas-ta
    indicators (VWAP, ADX, Donchian, OBV, etc.).

    Examples:
        # Built-in indicator
        IndicatorConfig(type=IndicatorType.SMA, name="sma_20", params={"period": 20})

        # pandas-ta indicator
        IndicatorConfig(type="vwap", name="vwap")
        IndicatorConfig(type="adx", name="trend", params={"length": 14})
    """

    type: FlexibleIndicatorType
    name: str = Field(..., description="Unique name for this indicator instance")
    params: dict = Field(default_factory=dict, description="Indicator parameters")

    model_config = {"extra": "forbid"}


class Comparison(str, Enum):
    """Comparison operators for rules."""

    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    # Rolling lookback operators (F022)
    WAS_ABOVE = "was_above"  # True if condition was met in lookback period
    WAS_BELOW = "was_below"  # True if condition was met in lookback period
    CROSSED_ABOVE_WITHIN = "crossed_above_within"  # Crossover in lookback period
    CROSSED_BELOW_WITHIN = "crossed_below_within"  # Crossunder in lookback period


class RuleCondition(BaseModel):
    """A single condition in a rule.

    Examples:
        - RSI < 30
        - SMA_20 crosses_above SMA_50
        - close > SMA_200
        - rsi was_below 30 (with lookback=5)
        - close >= rolling_max_20 (breakout)
    """

    left: str = Field(..., description="Left operand (indicator name or 'close', 'open', etc.)")
    comparison: Comparison
    right: str | float = Field(
        ..., description="Right operand (indicator name, price field, or numeric value)"
    )
    lookback: int | None = Field(
        default=None,
        description="Lookback period for was_above/was_below/crossed_*_within operators",
        ge=1,
    )


class Rule(BaseModel):
    """A rule combining multiple conditions.

    For short selling, set side="short" on entry rules. The backtest engine will:
    - Open a short position (profit when price falls)
    - Invert stop loss direction (triggers on price RISE)
    - Invert trailing stop tracking (tracks LOW price instead of high)
    """

    conditions: list[RuleCondition] = Field(..., min_length=1)
    logic: Literal["AND", "OR"] = Field(default="AND")
    side: Literal["long", "short"] = Field(
        default="long",
        description="Position side: 'long' (buy low, sell high) or 'short' (sell high, buy low)",
    )


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

    # Fixed stops (set at entry, never move)
    PERCENT = "percent"
    ATR = "atr"
    FIXED = "fixed"

    # Trailing stops (follow price, protect profits)
    TRAILING_PERCENT = "trailing_percent"
    TRAILING_ATR = "trailing_atr"

    # Breakeven stop (move to entry after profit threshold)
    BREAKEVEN = "breakeven"


class StopLossConfig(BaseModel):
    """Stop loss configuration.

    Supports fixed stops, trailing stops, and breakeven stops.

    Examples:
        # Fixed 5% stop
        StopLossConfig(type=StopLossType.PERCENT, value=0.05)

        # Trailing 5% stop (follows price up, protects gains)
        StopLossConfig(type=StopLossType.TRAILING_PERCENT, value=0.05)

        # Trailing 2x ATR stop
        StopLossConfig(type=StopLossType.TRAILING_ATR, value=2.0, atr_period=14)

        # Breakeven stop (move to entry after 5% profit)
        StopLossConfig(type=StopLossType.BREAKEVEN, value=0.0, trigger_percent=0.05)
    """

    type: StopLossType
    value: float = Field(..., description="Stop loss value (percent, ATR multiple, or fixed price)")

    # For ATR-based stops
    atr_period: int = Field(default=14, description="ATR period for ATR-based stops")

    # For breakeven stops
    trigger_percent: float | None = Field(
        default=None,
        description="Profit threshold to trigger breakeven stop (e.g., 0.05 = 5%)",
    )


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
    take_profit: TakeProfitConfig | None = Field(
        default=None, description="Take profit configuration"
    )

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
            ind_type = ind.type.value if hasattr(ind.type, "value") else str(ind.type)
            lines.append(f"  - {ind.name}: {ind_type}({ind.params})")

        lines.extend(["", "Entry Rules:"])
        for i, rule in enumerate(self.entry_rules, 1):
            conds = [f"{c.left} {c.comparison.value} {c.right}" for c in rule.conditions]
            side_str = f" [{rule.side.upper()}]" if rule.side == "short" else ""
            lines.append(f"  Rule {i}{side_str}: {f' {rule.logic} '.join(conds)}")

        if self.exit_rules:
            lines.extend(["", "Exit Rules:"])
            for i, rule in enumerate(self.exit_rules, 1):
                conds = [f"{c.left} {c.comparison.value} {c.right}" for c in rule.conditions]
                lines.append(f"  Rule {i}: {f' {rule.logic} '.join(conds)}")

        lines.extend(
            [
                "",
                f"Position Size: {self.position_size.type.value} = {self.position_size.value}",
            ]
        )

        if self.stop_loss:
            lines.append(f"Stop Loss: {self.stop_loss.type.value} = {self.stop_loss.value}")
        if self.take_profit:
            lines.append(f"Take Profit: {self.take_profit.type.value} = {self.take_profit.value}")

        return "\n".join(lines)
