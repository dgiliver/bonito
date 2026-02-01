"""Strategy Plugin Interface (F002).

This module provides an escape hatch for power users who need custom Python logic
that can't be expressed in the JSON DSL. Plugins allow arbitrary Python code to
generate trading signals while maintaining integration with the backtest engine.

Example plugin:
    class MomentumZscoreStrategy(StrategyPlugin):
        name = "momentum_zscore"
        description = "Z-score momentum strategy with dynamic thresholds"

        parameters = {
            "lookback": ParameterSpec(type="int", default=20, min=5, max=100),
            "entry_zscore": ParameterSpec(type="float", default=2.0, min=0.5, max=4.0),
        }

        def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
            # Custom Python logic here
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from bonito.data.models import BarData


@dataclass
class ParameterSpec:
    """Specification for a plugin parameter.

    Attributes:
        type: Parameter type ("int", "float", "str", "bool")
        default: Default value
        min: Minimum value (for numeric types)
        max: Maximum value (for numeric types)
        description: Human-readable description
        choices: Valid choices (for string types)
    """

    type: Literal["int", "float", "str", "bool"]
    default: Any
    min: float | None = None
    max: float | None = None
    description: str = ""
    choices: list[str] | None = None

    def validate(self, value: Any) -> Any:
        """Validate and coerce a parameter value.

        Args:
            value: Value to validate

        Returns:
            Validated and coerced value

        Raises:
            ValueError: If value is invalid
        """
        # Type coercion
        if self.type == "int":
            try:
                value = int(value)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Expected int, got {type(value).__name__}") from err
        elif self.type == "float":
            try:
                value = float(value)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Expected float, got {type(value).__name__}") from err
        elif self.type == "bool":
            value = value.lower() in ("true", "1", "yes") if isinstance(value, str) else bool(value)
        elif self.type == "str":
            value = str(value)

        # Range validation for numeric types
        if self.type in ("int", "float"):
            if self.min is not None and value < self.min:
                raise ValueError(f"Value {value} is below minimum {self.min}")
            if self.max is not None and value > self.max:
                raise ValueError(f"Value {value} is above maximum {self.max}")

        # Choices validation for string types
        if self.choices is not None and value not in self.choices:
            raise ValueError(f"Value '{value}' not in valid choices: {self.choices}")

        return value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type,
            "default": self.default,
            "description": self.description,
        }
        if self.min is not None:
            result["min"] = self.min
        if self.max is not None:
            result["max"] = self.max
        if self.choices is not None:
            result["choices"] = self.choices
        return result


@dataclass
class SignalOutput:
    """Output from a plugin's signal computation.

    This is the bridge between plugin Python code and the backtest engine.
    The engine will use these arrays to determine when to enter/exit positions.

    Attributes:
        entries: Boolean array - True where entry signal is generated
        exits: Boolean array - True where exit signal is generated
        entry_side: Position side for entries ("long" or "short")
        indicators: Optional dict of computed indicator values for charting
        metadata: Optional dict of any additional data to include in results
    """

    entries: np.ndarray
    exits: np.ndarray
    entry_side: Literal["long", "short"] = "long"
    indicators: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate signal arrays."""
        if len(self.entries) != len(self.exits):
            raise ValueError(
                f"Entry and exit arrays must be same length: "
                f"{len(self.entries)} vs {len(self.exits)}"
            )
        # Ensure boolean arrays
        self.entries = np.asarray(self.entries, dtype=bool)
        self.exits = np.asarray(self.exits, dtype=bool)


class StrategyPlugin(ABC):
    """Base class for strategy plugins.

    Subclass this to create a custom strategy that uses arbitrary Python logic.
    The plugin system provides:
    - Parameter definition and validation
    - Integration with the backtest engine
    - Exposure to the agent for tuning and execution

    Example:
        class MyStrategy(StrategyPlugin):
            name = "my_strategy"
            description = "My custom trading strategy"

            parameters = {
                "fast_period": ParameterSpec(type="int", default=10, min=2, max=50),
                "slow_period": ParameterSpec(type="int", default=30, min=10, max=200),
            }

            def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
                closes = data.close
                fast_ma = np.convolve(closes, np.ones(params["fast_period"]) /
                                      params["fast_period"], mode="same")
                slow_ma = np.convolve(closes, np.ones(params["slow_period"]) /
                                      params["slow_period"], mode="same")

                entries = np.zeros(len(closes), dtype=bool)
                exits = np.zeros(len(closes), dtype=bool)

                entries[1:] = (fast_ma[:-1] <= slow_ma[:-1]) & (fast_ma[1:] > slow_ma[1:])
                exits[1:] = (fast_ma[:-1] >= slow_ma[:-1]) & (fast_ma[1:] < slow_ma[1:])

                return SignalOutput(
                    entries=entries,
                    exits=exits,
                    indicators={"fast_ma": fast_ma, "slow_ma": slow_ma},
                )
    """

    # Subclasses must define these
    name: str
    description: str
    parameters: dict[str, ParameterSpec]

    @abstractmethod
    def compute_signals(self, data: BarData, params: dict[str, Any]) -> SignalOutput:
        """Compute entry and exit signals from bar data.

        Args:
            data: Historical bar data (OHLCV)
            params: Validated parameters dictionary

        Returns:
            SignalOutput with entry/exit boolean arrays and optional indicators
        """
        ...

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and fill in defaults for parameters.

        Args:
            params: User-provided parameters

        Returns:
            Complete parameters dict with defaults filled in

        Raises:
            ValueError: If any parameter is invalid
        """
        validated = {}
        for param_name, spec in self.parameters.items():
            if param_name in params:
                validated[param_name] = spec.validate(params[param_name])
            else:
                validated[param_name] = spec.default
        return validated

    def get_parameter_schema(self) -> dict[str, Any]:
        """Get JSON schema for parameters (for agent tool definition)."""
        properties = {}
        for name, spec in self.parameters.items():
            prop = {
                "type": "number" if spec.type in ("int", "float") else spec.type,
                "description": spec.description or f"Parameter: {name}",
                "default": spec.default,
            }
            if spec.min is not None:
                prop["minimum"] = spec.min
            if spec.max is not None:
                prop["maximum"] = spec.max
            if spec.choices:
                prop["enum"] = spec.choices
            properties[name] = prop

        return {
            "type": "object",
            "properties": properties,
            "required": [],  # All have defaults
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert plugin metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {name: spec.to_dict() for name, spec in self.parameters.items()},
        }
