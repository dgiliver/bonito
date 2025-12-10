"""Strategy validation and analysis tools."""

from typing import Any

from pydantic import ValidationError

from bonito.backtest.strategy import StrategyConfig
from bonito.tools.base import Tool, ToolResult


class ValidateStrategyTool(Tool):
    """Validate a strategy configuration."""

    @property
    def name(self) -> str:
        return "validate_strategy"

    @property
    def description(self) -> str:
        return """Validate a strategy configuration before backtesting.

Checks:
- Required fields are present
- Indicator configurations are valid
- Rules reference valid indicators
- Position sizing is reasonable

Returns validation errors if any issues found."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "object",
                    "description": "The strategy configuration to validate",
                },
            },
            "required": ["strategy"],
        }

    async def execute(self, strategy: dict, **kwargs: Any) -> ToolResult:
        """Validate the strategy."""
        errors: list[str] = []
        warnings: list[str] = []

        try:
            config = StrategyConfig(**strategy)

            # Additional semantic validation
            # Include base indicator names and potential multi-column suffixes
            indicator_names = set()
            for ind in config.indicators:
                indicator_names.add(ind.name)
                # Add common multi-column indicator suffixes
                ind_type = str(ind.type).lower()
                if ind_type in ("macd",):
                    indicator_names.update(
                        [f"{ind.name}_line", f"{ind.name}_signal", f"{ind.name}_hist"]
                    )
                elif ind_type in ("bbands",):
                    indicator_names.update(
                        [f"{ind.name}_upper", f"{ind.name}_middle", f"{ind.name}_lower"]
                    )
                elif ind_type in ("stoch",):
                    indicator_names.update([f"{ind.name}_k", f"{ind.name}_d"])
                elif ind_type in ("adx",):
                    indicator_names.update(
                        [
                            f"{ind.name}_adx",
                            f"{ind.name}_dmp",
                            f"{ind.name}_dmn",
                            f"{ind.name}_adxr",
                        ]
                    )
                elif ind_type in ("donchian",):
                    indicator_names.update(
                        [f"{ind.name}_dcl", f"{ind.name}_dcm", f"{ind.name}_dcu"]
                    )
                elif ind_type in ("supertrend",):
                    indicator_names.update(
                        [
                            f"{ind.name}_value",
                            f"{ind.name}_direction",
                            f"{ind.name}_long",
                            f"{ind.name}_short",
                        ]
                    )
                elif ind_type in ("aroon",):
                    indicator_names.update(
                        [f"{ind.name}_up", f"{ind.name}_down", f"{ind.name}_osc"]
                    )
                elif ind_type in ("kc",):
                    indicator_names.update(
                        [f"{ind.name}_lower", f"{ind.name}_middle", f"{ind.name}_upper"]
                    )
                elif ind_type in ("psar",):
                    indicator_names.update(
                        [
                            f"{ind.name}_long",
                            f"{ind.name}_short",
                            f"{ind.name}_af",
                            f"{ind.name}_reversal",
                        ]
                    )

            indicator_names.update({"open", "high", "low", "close", "volume"})

            # Check entry rules reference valid indicators
            for rule in config.entry_rules:
                for cond in rule.conditions:
                    if cond.left not in indicator_names:
                        errors.append(f"Entry rule references unknown indicator: {cond.left}")
                    if isinstance(cond.right, str) and cond.right not in indicator_names:
                        try:
                            float(cond.right)
                        except ValueError:
                            errors.append(f"Entry rule references unknown indicator: {cond.right}")

            # Check exit rules
            for rule in config.exit_rules:
                for cond in rule.conditions:
                    if cond.left not in indicator_names:
                        errors.append(f"Exit rule references unknown indicator: {cond.left}")
                    if isinstance(cond.right, str) and cond.right not in indicator_names:
                        try:
                            float(cond.right)
                        except ValueError:
                            errors.append(f"Exit rule references unknown indicator: {cond.right}")

            # Warnings
            if not config.stop_loss:
                warnings.append("No stop loss configured - unlimited downside risk")

            if not config.exit_rules and not config.take_profit:
                warnings.append("No exit rules or take profit - positions may never close")

            if config.position_size.value > 50:
                warnings.append(
                    f"Large position size ({config.position_size.value}%) - high concentration risk"
                )

            if errors:
                return ToolResult(
                    success=False,
                    error="Validation failed",
                    data={
                        "errors": errors,
                        "warnings": warnings,
                    },
                )

            return ToolResult(
                success=True,
                data={
                    "valid": True,
                    "warnings": warnings,
                    "strategy_summary": config.to_prompt_description(),
                },
            )

        except ValidationError as e:
            return ToolResult(
                success=False,
                error="Strategy configuration invalid",
                data={
                    "errors": [err["msg"] for err in e.errors()],
                    "details": e.errors(),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Validation error: {str(e)}",
            )
