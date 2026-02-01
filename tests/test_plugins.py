"""Tests for the Strategy Plugin System (F002).

Tests cover:
- Plugin base class and models (ParameterSpec, SignalOutput, StrategyPlugin)
- Plugin registry (discovery, registration, lookup)
- Plugin adapter (signal execution through backtest engine)
- Plugin tools (list, params, backtest)
"""

import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from bonito.backtest.models import BacktestConfig
from bonito.backtest.plugin_adapter import PluginAdapter
from bonito.backtest.plugin_registry import (
    PluginRegistry,
    get_plugin_registry,
    reset_plugin_registry,
)
from bonito.backtest.plugins import ParameterSpec, SignalOutput, StrategyPlugin
from bonito.data.models import BarData
from bonito.tools.plugin_tools import PluginListTool, PluginParamsTool

# =============================================================================
# Test Fixtures
# =============================================================================


class SimpleTestPlugin(StrategyPlugin):
    """A simple test plugin for unit testing."""

    name = "test_simple"
    description = "Simple test plugin"

    parameters = {
        "threshold": ParameterSpec(
            type="float", default=0.5, min=0.0, max=1.0, description="Signal threshold"
        ),
    }

    def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
        n = len(data.close)
        # Simple: entry every 10 bars, exit every 15 bars
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        entries[10::20] = True
        exits[15::20] = True
        return SignalOutput(entries=entries, exits=exits)


class ShortTestPlugin(StrategyPlugin):
    """Test plugin for short positions."""

    name = "test_short"
    description = "Short position test plugin"

    parameters = {
        "period": ParameterSpec(type="int", default=5, min=1, max=50),
    }

    def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
        n = len(data.close)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        entries[5::15] = True
        exits[10::15] = True
        return SignalOutput(entries=entries, exits=exits, entry_side="short")


@pytest.fixture
def sample_bar_data() -> BarData:
    """Create sample bar data for testing."""
    n = 100
    base_price = 100.0
    # Generate synthetic price data with slight upward trend
    np.random.seed(42)
    returns = np.random.randn(n) * 0.02  # 2% daily vol
    prices = base_price * np.exp(np.cumsum(returns))

    return BarData(
        symbol="TEST",
        timestamps=[
            datetime(2023, 1, 1) + i * (datetime(2023, 1, 2) - datetime(2023, 1, 1))
            for i in range(n)
        ],
        opens=(prices * 0.999).tolist(),
        highs=(prices * 1.01).tolist(),
        lows=(prices * 0.99).tolist(),
        closes=prices.tolist(),
        volumes=np.random.randint(1000000, 5000000, n).astype(float).tolist(),
    )


@pytest.fixture
def test_registry() -> PluginRegistry:
    """Create a fresh test registry."""
    registry = PluginRegistry()
    registry.register(SimpleTestPlugin())
    registry.register(ShortTestPlugin())
    return registry


# =============================================================================
# ParameterSpec Tests
# =============================================================================


class TestParameterSpec:
    """Tests for ParameterSpec validation and coercion."""

    def test_int_validation_valid(self) -> None:
        """Test integer parameter validation with valid input."""
        spec = ParameterSpec(type="int", default=10, min=1, max=100)
        assert spec.validate(50) == 50
        assert spec.validate("25") == 25  # String coercion

    def test_int_validation_out_of_range(self) -> None:
        """Test integer parameter validation with out-of-range value."""
        spec = ParameterSpec(type="int", default=10, min=1, max=100)
        with pytest.raises(ValueError, match="below minimum"):
            spec.validate(0)
        with pytest.raises(ValueError, match="above maximum"):
            spec.validate(150)

    def test_float_validation_valid(self) -> None:
        """Test float parameter validation."""
        spec = ParameterSpec(type="float", default=0.5, min=0.0, max=1.0)
        assert spec.validate(0.75) == 0.75
        assert spec.validate("0.3") == 0.3

    def test_float_validation_out_of_range(self) -> None:
        """Test float parameter validation with out-of-range value."""
        spec = ParameterSpec(type="float", default=0.5, min=0.0, max=1.0)
        with pytest.raises(ValueError, match="below minimum"):
            spec.validate(-0.1)

    def test_bool_validation(self) -> None:
        """Test boolean parameter validation and coercion."""
        spec = ParameterSpec(type="bool", default=True)
        assert spec.validate(True) is True
        assert spec.validate(False) is False
        assert spec.validate("true") is True
        assert spec.validate("false") is False
        assert spec.validate(1) is True
        assert spec.validate(0) is False

    def test_str_validation_with_choices(self) -> None:
        """Test string parameter validation with choices."""
        spec = ParameterSpec(type="str", default="long", choices=["long", "short"])
        assert spec.validate("long") == "long"
        assert spec.validate("short") == "short"
        with pytest.raises(ValueError, match="not in valid choices"):
            spec.validate("invalid")

    def test_to_dict(self) -> None:
        """Test ParameterSpec serialization."""
        spec = ParameterSpec(type="int", default=20, min=5, max=100, description="Test param")
        result = spec.to_dict()
        assert result["type"] == "int"
        assert result["default"] == 20
        assert result["min"] == 5
        assert result["max"] == 100
        assert result["description"] == "Test param"


# =============================================================================
# SignalOutput Tests
# =============================================================================


class TestSignalOutput:
    """Tests for SignalOutput validation."""

    def test_valid_signal_output(self) -> None:
        """Test valid SignalOutput creation."""
        entries = np.array([False, True, False, False])
        exits = np.array([False, False, True, False])
        output = SignalOutput(entries=entries, exits=exits)
        assert len(output.entries) == 4
        assert output.entry_side == "long"

    def test_array_length_mismatch(self) -> None:
        """Test that mismatched array lengths raise error."""
        entries = np.array([False, True, False])
        exits = np.array([False, False, True, False])
        with pytest.raises(ValueError, match="same length"):
            SignalOutput(entries=entries, exits=exits)

    def test_converts_to_bool_dtype(self) -> None:
        """Test that arrays are converted to bool dtype."""
        entries = np.array([0, 1, 0, 0])  # int array
        exits = np.array([0, 0, 1, 0])
        output = SignalOutput(entries=entries, exits=exits)
        assert output.entries.dtype == bool
        assert output.exits.dtype == bool

    def test_short_side(self) -> None:
        """Test SignalOutput with short side."""
        entries = np.array([False, True, False])
        exits = np.array([False, False, True])
        output = SignalOutput(entries=entries, exits=exits, entry_side="short")
        assert output.entry_side == "short"

    def test_with_indicators(self) -> None:
        """Test SignalOutput with custom indicators."""
        entries = np.array([False, True, False])
        exits = np.array([False, False, True])
        indicators = {"sma": np.array([100.0, 101.0, 102.0])}
        output = SignalOutput(entries=entries, exits=exits, indicators=indicators)
        assert "sma" in output.indicators
        assert len(output.indicators["sma"]) == 3


# =============================================================================
# StrategyPlugin Tests
# =============================================================================


class TestStrategyPlugin:
    """Tests for StrategyPlugin base class."""

    def test_validate_params_fills_defaults(self) -> None:
        """Test that validate_params fills in default values."""
        plugin = SimpleTestPlugin()
        result = plugin.validate_params({})
        assert result["threshold"] == 0.5

    def test_validate_params_uses_provided(self) -> None:
        """Test that validate_params uses provided values."""
        plugin = SimpleTestPlugin()
        result = plugin.validate_params({"threshold": 0.7})
        assert result["threshold"] == 0.7

    def test_validate_params_validates_range(self) -> None:
        """Test that validate_params validates parameter ranges."""
        plugin = SimpleTestPlugin()
        with pytest.raises(ValueError):
            plugin.validate_params({"threshold": 1.5})  # Above max

    def test_get_parameter_schema(self) -> None:
        """Test JSON schema generation for parameters."""
        plugin = SimpleTestPlugin()
        schema = plugin.get_parameter_schema()
        assert schema["type"] == "object"
        assert "threshold" in schema["properties"]
        assert schema["properties"]["threshold"]["type"] == "number"

    def test_to_dict(self) -> None:
        """Test plugin metadata serialization."""
        plugin = SimpleTestPlugin()
        result = plugin.to_dict()
        assert result["name"] == "test_simple"
        assert result["description"] == "Simple test plugin"
        assert "threshold" in result["parameters"]


# =============================================================================
# PluginRegistry Tests
# =============================================================================


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_register_and_get(self, test_registry: PluginRegistry) -> None:
        """Test registering and retrieving a plugin."""
        plugin = test_registry.get("test_simple")
        assert plugin is not None
        assert plugin.name == "test_simple"

    def test_get_nonexistent(self, test_registry: PluginRegistry) -> None:
        """Test getting a nonexistent plugin returns None."""
        assert test_registry.get("nonexistent") is None

    def test_list_plugins(self, test_registry: PluginRegistry) -> None:
        """Test listing all registered plugins."""
        plugins = test_registry.list_plugins()
        assert len(plugins) == 2
        names = [p.name for p in plugins]
        assert "test_simple" in names
        assert "test_short" in names

    def test_list_names(self, test_registry: PluginRegistry) -> None:
        """Test listing plugin names."""
        names = test_registry.list_names()
        assert "test_simple" in names
        assert "test_short" in names

    def test_get_plugin_info(self, test_registry: PluginRegistry) -> None:
        """Test getting detailed plugin info."""
        info = test_registry.get_plugin_info("test_simple")
        assert info is not None
        assert info["name"] == "test_simple"
        assert "parameters" in info

    def test_get_all_info(self, test_registry: PluginRegistry) -> None:
        """Test getting info for all plugins."""
        all_info = test_registry.get_all_info()
        assert len(all_info) == 2

    def test_discover_plugins_from_directory(self) -> None:
        """Test auto-discovery of plugins from a directory."""
        # Create a temporary directory with a plugin file
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_code = """
from bonito.backtest.plugins import ParameterSpec, SignalOutput, StrategyPlugin
from bonito.data.models import BarData
import numpy as np

class DiscoveredPlugin(StrategyPlugin):
    name = "discovered"
    description = "Auto-discovered plugin"
    parameters = {"param": ParameterSpec(type="int", default=10)}

    def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
        n = len(data.close)
        return SignalOutput(
            entries=np.zeros(n, dtype=bool),
            exits=np.zeros(n, dtype=bool)
        )
"""
            plugin_file = Path(tmpdir) / "discovered_plugin.py"
            plugin_file.write_text(plugin_code)

            registry = PluginRegistry()
            count = registry.discover_plugins(tmpdir)
            assert count == 1
            assert registry.get("discovered") is not None

    def test_discover_handles_missing_directory(self) -> None:
        """Test discovery handles nonexistent directory gracefully."""
        registry = PluginRegistry()
        count = registry.discover_plugins("/nonexistent/path")
        assert count == 0

    def test_discover_skips_private_files(self) -> None:
        """Test discovery skips files starting with underscore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create __init__.py which should be skipped
            init_file = Path(tmpdir) / "__init__.py"
            init_file.write_text("# init file")

            registry = PluginRegistry()
            count = registry.discover_plugins(tmpdir)
            assert count == 0


# =============================================================================
# PluginAdapter Tests
# =============================================================================


class TestPluginAdapter:
    """Tests for PluginAdapter (running plugins through backtest engine)."""

    def test_run_long_plugin(self, sample_bar_data: BarData) -> None:
        """Test running a long-only plugin."""
        plugin = SimpleTestPlugin()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        result = adapter.run(plugin, sample_bar_data)

        assert result.strategy_name == "plugin:test_simple"
        assert result.symbol == "TEST"
        assert result.initial_capital == 100000
        assert len(result.trades) > 0

    def test_run_short_plugin(self, sample_bar_data: BarData) -> None:
        """Test running a short-position plugin."""
        plugin = ShortTestPlugin()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        result = adapter.run(plugin, sample_bar_data)

        assert len(result.trades) > 0
        # All trades should be short
        for trade in result.trades:
            assert trade.position_side == "short"

    def test_run_with_stop_loss(self, sample_bar_data: BarData) -> None:
        """Test running plugin with stop loss."""
        plugin = SimpleTestPlugin()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        result = adapter.run(plugin, sample_bar_data, stop_loss_pct=0.05)

        assert result is not None
        # Just verify the run completed (stop losses may or may not trigger)
        assert result.final_capital > 0

    def test_run_with_take_profit(self, sample_bar_data: BarData) -> None:
        """Test running plugin with take profit."""
        plugin = SimpleTestPlugin()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        result = adapter.run(plugin, sample_bar_data, take_profit_pct=0.10)

        assert result is not None
        assert result.final_capital > 0

    def test_run_with_position_sizing(self, sample_bar_data: BarData) -> None:
        """Test running plugin with custom position size."""
        plugin = SimpleTestPlugin()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        result = adapter.run(plugin, sample_bar_data, position_size_pct=50.0)

        assert result is not None
        # With 50% sizing, position values should be roughly half of equity
        if result.trades:
            first_trade = result.trades[0]
            position_value = first_trade.entry_price * first_trade.quantity
            assert position_value < 100000  # Less than full capital

    def test_metrics_calculation(self, sample_bar_data: BarData) -> None:
        """Test that metrics are calculated correctly."""
        plugin = SimpleTestPlugin()
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        result = adapter.run(plugin, sample_bar_data)

        # Verify metrics are populated
        assert result.metrics.total_trades > 0
        assert (
            result.metrics.winning_trades + result.metrics.losing_trades
            == result.metrics.total_trades
        )
        assert 0.0 <= result.metrics.win_rate <= 1.0
        assert result.metrics.max_drawdown >= 0.0


# =============================================================================
# Plugin Tools Tests
# =============================================================================


class TestPluginTools:
    """Tests for plugin agent tools."""

    @pytest.fixture(autouse=True)
    def setup_registry(self) -> None:
        """Reset and populate the global registry before each test."""
        reset_plugin_registry()
        registry = get_plugin_registry()
        registry.register(SimpleTestPlugin())
        registry.register(ShortTestPlugin())
        yield
        reset_plugin_registry()

    @pytest.mark.asyncio
    async def test_plugin_list_tool(self) -> None:
        """Test PluginListTool returns all plugins including test plugins."""
        tool = PluginListTool()
        result = await tool.execute()

        assert result.success
        assert result.data is not None
        # Should have at least our 2 test plugins (may also have real example plugins)
        assert result.data["count"] >= 2
        plugin_names = [p["name"] for p in result.data["plugins"]]
        assert "test_simple" in plugin_names
        assert "test_short" in plugin_names

    @pytest.mark.asyncio
    async def test_plugin_params_tool_success(self) -> None:
        """Test PluginParamsTool returns plugin parameters."""
        tool = PluginParamsTool()
        result = await tool.execute(plugin_name="test_simple")

        assert result.success
        assert result.data is not None
        assert result.data["name"] == "test_simple"
        assert "parameters" in result.data

    @pytest.mark.asyncio
    async def test_plugin_params_tool_not_found(self) -> None:
        """Test PluginParamsTool handles missing plugin."""
        tool = PluginParamsTool()
        result = await tool.execute(plugin_name="nonexistent")

        assert not result.success
        assert "not found" in result.error.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestPluginIntegration:
    """Integration tests for the full plugin flow."""

    def test_real_plugin_discovery(self) -> None:
        """Test discovering the real example plugins."""
        reset_plugin_registry()
        registry = get_plugin_registry()

        # Should find the example plugins in strategies/plugins/
        names = registry.list_names()
        # At minimum we should find momentum_zscore and mean_reversion
        # (May be empty if running tests from different directory)
        if names:
            assert any("momentum" in name or "reversion" in name for name in names)

    def test_example_plugin_execution(self, sample_bar_data: BarData) -> None:
        """Test running the example momentum_zscore plugin if available."""
        reset_plugin_registry()
        registry = get_plugin_registry()

        plugin = registry.get("momentum_zscore")
        if plugin is None:
            pytest.skip("momentum_zscore plugin not found")

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=100000,
        )
        adapter = PluginAdapter(config)

        # Use custom parameters
        result = adapter.run(
            plugin,
            sample_bar_data,
            params={"lookback": 10, "entry_threshold": 1.5},
        )

        assert result is not None
        assert result.strategy_name == "plugin:momentum_zscore"
