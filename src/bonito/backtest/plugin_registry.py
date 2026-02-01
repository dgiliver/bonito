"""Plugin Registry - Auto-discovery and management of strategy plugins.

This module handles:
- Auto-discovery of plugins from the strategies/plugins/ directory
- Registration and lookup of plugins by name
- Parameter schema extraction for the agent

Plugins are discovered by scanning for Python files that contain subclasses
of StrategyPlugin.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from bonito.backtest.plugins import StrategyPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for managing strategy plugins.

    Provides auto-discovery from a plugins directory and manual registration.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, StrategyPlugin] = {}

    def register(self, plugin: StrategyPlugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: Plugin instance to register
        """
        if not hasattr(plugin, "name") or not plugin.name:
            raise ValueError("Plugin must have a non-empty 'name' attribute")
        if plugin.name in self._plugins:
            logger.warning(f"Overwriting existing plugin: {plugin.name}")
        self._plugins[plugin.name] = plugin
        logger.debug(f"Registered plugin: {plugin.name}")

    def get(self, name: str) -> StrategyPlugin | None:
        """Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(name)

    def list_plugins(self) -> list[StrategyPlugin]:
        """List all registered plugins.

        Returns:
            List of registered plugin instances
        """
        return list(self._plugins.values())

    def list_names(self) -> list[str]:
        """List all registered plugin names.

        Returns:
            List of plugin names
        """
        return list(self._plugins.keys())

    def get_plugin_info(self, name: str) -> dict[str, Any] | None:
        """Get detailed information about a plugin.

        Args:
            name: Plugin name

        Returns:
            Dict with plugin metadata, or None if not found
        """
        plugin = self.get(name)
        if plugin is None:
            return None
        return plugin.to_dict()

    def get_all_info(self) -> list[dict[str, Any]]:
        """Get information about all registered plugins.

        Returns:
            List of dicts with plugin metadata
        """
        return [p.to_dict() for p in self._plugins.values()]

    def discover_plugins(self, plugins_dir: Path | str) -> int:
        """Auto-discover and register plugins from a directory.

        Scans the directory for Python files and looks for StrategyPlugin subclasses.
        Each plugin class found is instantiated and registered.

        Args:
            plugins_dir: Path to the plugins directory

        Returns:
            Number of plugins discovered and registered
        """
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            logger.warning(f"Plugins directory does not exist: {plugins_path}")
            return 0

        count = 0
        for py_file in plugins_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue  # Skip __init__.py and private files

            try:
                plugins_found = self._load_plugins_from_file(py_file)
                count += plugins_found
            except Exception as e:
                logger.error(f"Failed to load plugins from {py_file}: {e}")

        logger.info(f"Discovered {count} plugins from {plugins_path}")
        return count

    def _load_plugins_from_file(self, file_path: Path) -> int:
        """Load plugin classes from a Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            Number of plugins loaded from the file
        """
        # Create a unique module name to avoid conflicts
        module_name = f"bonito_plugins.{file_path.stem}"

        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not create module spec for {file_path}")
            return 0

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Error executing module {file_path}: {e}")
            del sys.modules[module_name]
            return 0

        # Find StrategyPlugin subclasses
        count = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Skip if not a class
            if not isinstance(attr, type):
                continue

            # Skip the base class itself
            if attr is StrategyPlugin:
                continue

            # Check if it's a subclass of StrategyPlugin
            if issubclass(attr, StrategyPlugin):
                try:
                    # Instantiate and register
                    plugin_instance = attr()
                    self.register(plugin_instance)
                    count += 1
                    logger.debug(f"Loaded plugin '{plugin_instance.name}' from {file_path}")
                except Exception as e:
                    logger.error(f"Failed to instantiate {attr_name} from {file_path}: {e}")

        return count


# Global registry instance
_default_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Get the default global plugin registry.

    Creates the registry and discovers plugins on first call.

    Returns:
        The global PluginRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = PluginRegistry()

        # Try to discover plugins from the default location
        # This assumes the project root has a strategies/plugins/ directory
        default_plugins_dir = Path(__file__).parent.parent.parent.parent / "strategies" / "plugins"
        if default_plugins_dir.exists():
            _default_registry.discover_plugins(default_plugins_dir)
        else:
            logger.debug(f"Default plugins directory not found: {default_plugins_dir}")

    return _default_registry


def reset_plugin_registry() -> None:
    """Reset the global plugin registry (useful for testing)."""
    global _default_registry
    _default_registry = None
