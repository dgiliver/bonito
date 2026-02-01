"""Strategy plugins directory.

Place your custom Python strategy plugins here. Each plugin should subclass
StrategyPlugin from bonito.backtest.plugins and implement compute_signals().

Example:
    from bonito.backtest.plugins import ParameterSpec, SignalOutput, StrategyPlugin
    from bonito.data.models import BarData

    class MyStrategy(StrategyPlugin):
        name = "my_strategy"
        description = "My custom strategy"
        parameters = {
            "period": ParameterSpec(type="int", default=20, min=5, max=100),
        }

        def compute_signals(self, data: BarData, params: dict) -> SignalOutput:
            # Your signal generation logic here
            ...
"""
