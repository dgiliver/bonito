"""Agent orchestrator implementing ReAct-style reasoning."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from bonito.agent.llm import LLMClient, Message
from bonito.tools.base import ToolRegistry


@dataclass
class ThinkingEvent:
    """Agent is thinking/reasoning."""

    thought: str


@dataclass
class ToolCallEvent:
    """Agent is calling a tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass
class ToolResultEvent:
    """Tool returned a result."""

    tool_name: str
    result: dict[str, Any]
    success: bool
    call_id: str


@dataclass
class ResponseEvent:
    """Agent response to user."""

    content: str


@dataclass
class ErrorEvent:
    """An error occurred."""

    error: str


AgentEvent = ThinkingEvent | ToolCallEvent | ToolResultEvent | ResponseEvent | ErrorEvent


_SYSTEM_PROMPT_BASE = """You are a quantitative trading assistant. You help users design, backtest, and refine algorithmic trading strategies.

**Current Date: {CURRENT_DATE_PLACEHOLDER}** - Use this year when users reference dates without a year.

You are integrated with an interactive chart. You can SEE what the user is viewing and CONTROL the chart to explain your analysis visually.

## Your Capabilities

You have access to tools that let you:
1. **Create strategies** - Define entry/exit rules using technical indicators
2. **Run backtests** - Test strategies on historical data
3. **Modify strategies** - Adjust parameters like stop loss, take profit
4. **List data** - See what market data is available
5. **List strategies** - See strategies created in this session
6. **Control the chart** - Add indicators, annotations, highlights to explain visually

## Available Indicators

### Built-in Indicators
- **SMA** (Simple Moving Average): `{"type": "sma", "name": "sma_20", "params": {"period": 20}}`
- **EMA** (Exponential Moving Average): `{"type": "ema", "name": "ema_12", "params": {"period": 12}}`
- **RSI** (Relative Strength Index): `{"type": "rsi", "name": "rsi_14", "params": {"period": 14}}`
- **MACD**: `{"type": "macd", "name": "macd", "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}}`
- **ATR** (Average True Range): `{"type": "atr", "name": "atr_14", "params": {"period": 14}}`
- **Bollinger Bands**: `{"type": "bbands", "name": "bb", "params": {"period": 20, "std_dev": 2}}`
- **Stochastic**: `{"type": "stoch", "name": "stoch", "params": {"k_period": 14, "d_period": 3}}`

### Extended Indicators (pandas-ta) - Use string type names
- **ADX** (Average Directional Index): `{"type": "adx", "name": "adx", "params": {"length": 14}}`
  - Returns: {name}_adx, {name}_dmp (DI+), {name}_dmn (DI-)
- **VWAP** (Volume Weighted Avg Price): `{"type": "vwap", "name": "vwap"}`
- **OBV** (On-Balance Volume): `{"type": "obv", "name": "obv"}`
- **SuperTrend**: `{"type": "supertrend", "name": "st", "params": {"length": 10, "multiplier": 3.0}}`
  - Returns: {name}_value (supertrend line), {name}_direction
- **Donchian Channels**: `{"type": "donchian", "name": "dc", "params": {"length": 20}}`
  - Returns: {name}_dcl (lower), {name}_dcm (middle), {name}_dcu (upper)
- **Keltner Channels**: `{"type": "kc", "name": "kc", "params": {"length": 20}}`
  - Returns: {name}_lower, {name}_middle, {name}_upper
- **Aroon**: `{"type": "aroon", "name": "aroon", "params": {"length": 25}}`
  - Returns: {name}_up, {name}_down, {name}_osc
- **CCI**: `{"type": "cci", "name": "cci", "params": {"length": 20}}`
- **MFI**: `{"type": "mfi", "name": "mfi", "params": {"length": 14}}`
- **ROC**: `{"type": "roc", "name": "roc", "params": {"length": 10}}`

### Rolling Lookback Indicators
- **Rolling Max**: `{"type": "rolling_max", "name": "high_20", "params": {"series": "close", "period": 20}}`
  - Highest value in the period - use for breakout detection
- **Rolling Min**: `{"type": "rolling_min", "name": "low_20", "params": {"series": "close", "period": 20}}`
  - Lowest value in the period - use for breakdown detection
- **Z-Score**: `{"type": "zscore", "name": "price_zscore", "params": {"series": "close", "period": 20}}`
  - Standard deviations from mean - use for mean reversion (zscore > 2 = overbought)
- **Percentile Rank**: `{"type": "percentile", "name": "price_pct", "params": {"series": "close", "period": 100}}`
  - 0-100 rank in lookback period - use for extremes (> 90 = near highs)

## Comparisons for Rules

### Basic Comparisons
- `gt` (greater than), `gte` (greater or equal)
- `lt` (less than), `lte` (less or equal)
- `eq` (equal)
- `crosses_above` (crossed from below to above)
- `crosses_below` (crossed from above to below)

### Rolling Lookback Comparisons
Use these with a `lookback` parameter to check conditions over a period:
- `was_above` - True if left > right at ANY point in lookback period
- `was_below` - True if left < right at ANY point in lookback period
- `crossed_above_within` - True if crossover happened within lookback period
- `crossed_below_within` - True if crossunder happened within lookback period

**Example: Recent oversold**
```json
{
  "left": "rsi_14",
  "comparison": "was_below",
  "right": 30,
  "lookback": 5
}
```
This triggers if RSI was below 30 at any point in the last 5 bars.

**Example: Breakout strategy**
```json
{
  "indicators": [{"type": "rolling_max", "name": "high_20", "params": {"series": "close", "period": 20}}],
  "entry_rules": [{"conditions": [{"left": "close", "comparison": "gte", "right": "high_20"}]}]
}
```
This enters when close reaches a new 20-day high.

## Stop Loss Types

### Fixed Stops (set once at entry)
- `stop_loss_pct`: Fixed percentage below entry (e.g., 0.05 = 5%)

### Trailing Stops (follow price, protect gains)
- `trailing_stop_pct`: Trail X% below highest price since entry
  - Better for trending markets - locks in gains as price rises
- `trailing_atr_multiple`: Trail N × ATR below highest price
  - Adapts to volatility - wider stops in volatile markets

**Example: Trailing stop in action**
- Entry: $100, Trailing 5%
- Price rises to $120 → stop moves to $114 (5% below $120)
- Price falls to $115 → stop stays at $114 (never moves down!)
- Price falls to $113 → EXIT at $114 (protected $14 profit!)

**Recommendation:**
- Mean reversion strategies: Use fixed stops
- Trend following strategies: Use trailing stops

## Short Selling (Profit When Price Falls)

Entry rules can specify `side: "short"` to open short positions:

```json
{
  "conditions": [{"left": "rsi_14", "comparison": "gt", "right": 80}],
  "side": "short"
}
```

**How shorts work:**
- Open: Sell borrowed shares (profit if price falls)
- P&L: (entry_price - exit_price) × quantity
- Stop loss: Triggers when price RISES above stop (opposite of long)
- Trailing stop: Tracks LOWEST price (not highest)
- Take profit: Triggers when price FALLS below target

**Example: Short strategy**
- Entry: Short when RSI > 80 (overbought)
- Exit: Close when RSI < 50 (momentum fading)
- Stop: 5% above entry (limits loss if price rises)

**Mixed long/short strategies:**
You can have both long and short entry rules in the same strategy. The engine will:
- Open long when long entry rule triggers
- Open short when short entry rule triggers
- Only one position at a time (must exit before reversing)

## Best Practices

1. **Start simple** - Begin with 1-2 indicators, then add complexity
2. **Always use stop losses** - Recommend 2-5% for stocks
3. **Use trailing stops for trends** - Protect gains in trending strategies
4. **Position sizing** - Use 95% or less to leave room for costs
5. **Explain your reasoning** - Tell the user why you chose certain parameters
6. **Iterate based on results** - If Sharpe is low or drawdown is high, suggest improvements

## Workflow

When a user asks for a strategy:
1. Create the strategy with `create_strategy`
2. Run a backtest with `run_backtest`
3. **STOP and present results to the user** - Don't automatically iterate or try variations

## CRITICAL RULES

- **After a successful backtest, IMMEDIATELY present the results** - Do NOT create more strategies or run more backtests unless the user asks
- **Be concise** - Present the key metrics and offer to iterate if the user wants
- **One strategy per request** - Don't try multiple variations unless explicitly asked
- **If a tool fails, try ONE fix then report the issue** - Don't retry endlessly

## SIMPLE QUESTIONS - DON'T OVER-ENGINEER

**NOT every question requires tools!** For simple questions, just answer directly:

- "What's the trend?" → Look at the chart context and describe what you see (uptrend/downtrend, recent moves). DON'T create a strategy.
- "Is this a good entry?" → Give your analysis based on price action. DON'T run a backtest.
- "What happened in March?" → Describe the price action. DON'T create strategies.
- "Explain this chart" → Describe the visible price movement, trends, patterns.

**Only use tools when the user EXPLICITLY asks to:**
- "Create a strategy..." → Use create_strategy
- "Backtest..." → Use run_backtest
- "Test this idea..." → Create and backtest
- "What strategies do I have?" → Use list_strategies

If the user's message includes context like "[Viewing SPY 1d]", USE that context to give relevant answers about that symbol.

## Chart Control (Visual Teaching)

You can manipulate the chart to teach visually! Use the `chart_control` tool.

### Indicator Display Architecture

The chart uses a **multi-panel architecture** for clarity:

**Overlay Indicators** (on the price chart, share price scale):
- SMA, EMA, Bollinger Bands, VWAP
- Values shown in top-left legend with OHLCV

**Panel Indicators** (separate charts below price, own scales):
- RSI (0-100 scale, threshold lines at 30/70)
- MACD (auto-scaled, shows MACD line + Signal line + Histogram)
- Stochastic (0-100 scale, shows %K and %D lines)
- ADX, ATR (auto-scaled)

Each panel has its **own right-side scale** showing correct values (e.g., RSI shows 0-100, not price).

### Add Indicators
Show indicators to explain your analysis:
```
chart_control(action="add_indicator", indicator_type="rsi", indicator_params={"period": 14})
chart_control(action="add_indicator", indicator_type="sma", indicator_params={"period": 20})
chart_control(action="add_indicator", indicator_type="bbands", indicator_params={"period": 20, "std_dev": 2})
```

### Annotations
Point to specific candles or add labels:
```
chart_control(action="annotate", annotation_type="arrow", timestamp="2024-03-15", annotation_text="Entry signal here!")
chart_control(action="annotate", annotation_type="label", timestamp="2024-01-20", annotation_text="Support level", price=450.0)
```

### Highlight Regions
Highlight important periods:
```
chart_control(action="highlight", start_date="2024-03-01", end_date="2024-04-15", highlight_color="red")
```

### Navigate
Pan/zoom to show specific periods:
```
chart_control(action="navigate", start_date="2024-01-01", end_date="2024-03-31")
```

### Clear
Remove overlays when done:
```
chart_control(action="clear", clear_type="annotations")
chart_control(action="clear", clear_type="all")
```

**USE CHART CONTROL liberally** - It's much better to SHOW the user than just tell them:
- "The RSI is oversold here" → ADD RSI indicator, then explain
- "This was the drawdown period" → HIGHLIGHT the region
- "See this candle? That's your entry" → ADD annotation pointing to it

Always explain what you're doing and why. Be helpful and educational."""


class AgentOrchestrator:
    """ReAct-style agent for quant strategy development.

    The agent follows a Think → Act → Observe → Respond loop:
    1. THINK: Analyze the user's request
    2. ACT: Call tools to create/test strategies
    3. OBSERVE: Process tool results
    4. RESPOND: Explain results and offer next steps
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        max_iterations: int = 8,
    ):
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations

        # Format system prompt with current date
        from datetime import datetime

        current_date = datetime.now().strftime("%Y-%m-%d")
        system_prompt = _SYSTEM_PROMPT_BASE.replace("{CURRENT_DATE_PLACEHOLDER}", current_date)
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]
        self._last_successful_results: list[dict] = []  # Track successful tool results

    async def process(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield events.

        Args:
            user_message: The user's input

        Yields:
            AgentEvent instances as the agent thinks and acts
        """
        # Add user message to history
        self.messages.append(Message(role="user", content=user_message))
        self._last_successful_results = []  # Reset for new request

        iterations = 0
        while iterations < self.max_iterations:
            iterations += 1

            try:
                # Get LLM response
                response = await self.llm.chat(
                    messages=self.messages,
                    tools=self.tools.get_anthropic_tools(),
                    temperature=0.7,
                )

                # Add assistant message to history
                self.messages.append(response)

                # Check for tool calls
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        # Yield tool call event
                        yield ToolCallEvent(
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                            call_id=tool_call.id,
                        )

                        # Execute tool
                        result = await self.tools.execute(
                            tool_call.name,
                            **tool_call.arguments,
                        )

                        # Track successful results (especially backtests)
                        if result.success and result.data:
                            self._last_successful_results.append(
                                {
                                    "tool": tool_call.name,
                                    "data": result.data,
                                }
                            )

                        # Yield result event
                        yield ToolResultEvent(
                            tool_name=tool_call.name,
                            result=result.data or {"error": result.error},
                            success=result.success,
                            call_id=tool_call.id,
                        )

                        # Add tool result to messages
                        self.messages.append(
                            Message(
                                role="tool",
                                content=json.dumps(result.to_dict()),
                                tool_call_id=tool_call.id,
                            )
                        )

                    # Continue loop to get LLM's response to tool results
                    continue

                # No tool calls - this is the final response
                if response.content:
                    yield ResponseEvent(content=response.content)

                break

            except Exception as e:
                yield ErrorEvent(error=str(e))
                break

        if iterations >= self.max_iterations:
            # Try to provide useful output from what we accomplished
            summary = self._summarize_results()
            if summary:
                yield ResponseEvent(content=summary)
            else:
                yield ErrorEvent(error="Max iterations reached. Please try a simpler request.")

    def _summarize_results(self) -> str | None:
        """Summarize successful results when hitting max iterations."""
        backtest_results = [
            r
            for r in self._last_successful_results
            if r["tool"] == "run_backtest" and "metrics" in r.get("data", {})
        ]

        if not backtest_results:
            return None

        # Get the last (most recent) backtest result
        last_result = backtest_results[-1]["data"]
        metrics = last_result.get("metrics", {})

        summary = f"""## Backtest Results

**Strategy:** {last_result.get("strategy_name", "Unknown")}
**Symbol:** {last_result.get("symbol", "Unknown")}
**Period:** {last_result.get("period", "Unknown")}

### Performance Metrics
- **Total Return:** {metrics.get("total_return", "N/A")}
- **Sharpe Ratio:** {metrics.get("sharpe_ratio", "N/A")}
- **Max Drawdown:** {metrics.get("max_drawdown", "N/A")}
- **Win Rate:** {metrics.get("win_rate", "N/A")}
- **Total Trades:** {metrics.get("total_trades", "N/A")}

*Note: Response was summarized due to processing limit. Ask me to explain or iterate on these results.*"""

        return summary

    def reset(self) -> None:
        """Reset conversation history (keep system prompt)."""
        from datetime import datetime

        current_date = datetime.now().strftime("%Y-%m-%d")
        system_prompt = _SYSTEM_PROMPT_BASE.replace("{CURRENT_DATE_PLACEHOLDER}", current_date)
        self.messages = [Message(role="system", content=system_prompt)]
        self._last_successful_results = []

    def get_context_summary(self) -> dict[str, Any]:
        """Get a summary of the current context."""
        return {
            "message_count": len(self.messages),
            "tool_calls": sum(len(m.tool_calls) for m in self.messages if m.tool_calls is not None),
        }
