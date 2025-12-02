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


SYSTEM_PROMPT = """You are a quantitative trading assistant. You help users design, backtest, and refine algorithmic trading strategies.

## Your Capabilities

You have access to tools that let you:
1. **Create strategies** - Define entry/exit rules using technical indicators
2. **Run backtests** - Test strategies on historical data
3. **Modify strategies** - Adjust parameters like stop loss, take profit
4. **List data** - See what market data is available
5. **List strategies** - See strategies created in this session

## Available Indicators

- **SMA** (Simple Moving Average): `{"type": "sma", "name": "sma_20", "params": {"period": 20}}`
- **EMA** (Exponential Moving Average): `{"type": "ema", "name": "ema_12", "params": {"period": 12}}`
- **RSI** (Relative Strength Index): `{"type": "rsi", "name": "rsi_14", "params": {"period": 14}}`
- **MACD**: `{"type": "macd", "name": "macd", "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}}`
- **ATR** (Average True Range): `{"type": "atr", "name": "atr_14", "params": {"period": 14}}`
- **Bollinger Bands**: `{"type": "bbands", "name": "bb", "params": {"period": 20, "std_dev": 2}}`
- **Stochastic**: `{"type": "stoch", "name": "stoch", "params": {"k_period": 14, "d_period": 3}}`

## Comparisons for Rules

- `gt` (greater than), `gte` (greater or equal)
- `lt` (less than), `lte` (less or equal)
- `eq` (equal)
- `crosses_above` (crossed from below to above)
- `crosses_below` (crossed from above to below)

## Best Practices

1. **Start simple** - Begin with 1-2 indicators, then add complexity
2. **Always use stop losses** - Recommend 2-5% for stocks
3. **Position sizing** - Use 95% or less to leave room for costs
4. **Explain your reasoning** - Tell the user why you chose certain parameters
5. **Iterate based on results** - If Sharpe is low or drawdown is high, suggest improvements

## Workflow

When a user asks for a strategy:
1. First, check what data is available with `list_data`
2. Create the strategy with `create_strategy`
3. Run a backtest with `run_backtest`
4. Present results and offer to iterate

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
        max_iterations: int = 10,
    ):
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]

    async def process(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield events.

        Args:
            user_message: The user's input

        Yields:
            AgentEvent instances as the agent thinks and acts
        """
        # Add user message to history
        self.messages.append(Message(role="user", content=user_message))

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
            yield ErrorEvent(error="Max iterations reached. Please try a simpler request.")

    def reset(self) -> None:
        """Reset conversation history (keep system prompt)."""
        self.messages = [Message(role="system", content=SYSTEM_PROMPT)]

    def get_context_summary(self) -> dict[str, Any]:
        """Get a summary of the current context."""
        return {
            "message_count": len(self.messages),
            "tool_calls": sum(len(m.tool_calls) for m in self.messages if m.tool_calls is not None),
        }
