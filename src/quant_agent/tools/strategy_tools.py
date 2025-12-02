"""Strategy validation and analysis tools."""

from typing import Any

from pydantic import ValidationError

from quant_agent.backtest.strategy import StrategyConfig
from quant_agent.tools.base import Tool, ToolResult


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
            indicator_names = {ind.name for ind in config.indicators}
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
                warnings.append(f"Large position size ({config.position_size.value}%) - high concentration risk")
            
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

