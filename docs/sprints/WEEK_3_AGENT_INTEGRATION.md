# Week 3: Agent Integration Sprint

**Goal**: Build an AI agent that can generate, backtest, and iterate on trading strategies through natural language conversation.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        User (CLI)                           │
│                     "Build me a momentum strategy"          │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Orchestrator                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   ReAct Loop                         │    │
│  │  1. THINK: Analyze request, plan approach           │    │
│  │  2. ACT: Call tools (backtest, data, strategy)      │    │
│  │  3. OBSERVE: Process tool results                   │    │
│  │  4. DECIDE: Continue or respond to user             │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Memory     │  │   Context    │  │   Tracing    │       │
│  │ (chat hist)  │  │ (strategies) │  │  (debug)     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Tool Registry                          │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│ run_backtest│ list_data   │ create_     │ analyze_results   │
│             │             │ strategy    │                   │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ get_bars    │ validate_   │ modify_     │ compare_          │
│             │ strategy    │ strategy    │ strategies        │
└─────────────┴─────────────┴─────────────┴───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Existing Components                       │
│  BacktestEngine  │  MarketDataStore  │  StrategyConfig      │
└─────────────────────────────────────────────────────────────┘
```

---

## Tickets

### T1: Tool Protocol Enhancement
**Priority**: P0
**Effort**: 2 hours

Enhance existing tool base classes for agent compatibility.

**File**: `src/quant_agent/tools/base.py`

```python
from typing import Any
from pydantic import BaseModel

class ToolParameter(BaseModel):
    """Schema for a tool parameter."""
    name: str
    type: str  # "string", "number", "boolean", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None

class ToolDefinition(BaseModel):
    """Full tool definition for LLM."""
    name: str
    description: str
    parameters: list[ToolParameter]

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        ...

    def to_anthropic_schema(self) -> dict:
        """Convert to Anthropic tool use format."""
        ...
```

**Acceptance Criteria**:
- [ ] Tools can export their schema in OpenAI format
- [ ] Tools can export their schema in Anthropic format
- [ ] All existing tools have complete parameter descriptions

---

### T2: Agent Tools Implementation
**Priority**: P0
**Effort**: 4 hours

Create agent-friendly tool wrappers with rich context.

**Files**:
- `src/quant_agent/agent/tools.py`

**Tools to implement**:

```python
# 1. Strategy Creation
create_strategy(
    name: str,
    description: str,
    indicators: list[dict],  # [{"type": "ema", "name": "fast", "params": {"period": 12}}]
    entry_conditions: list[dict],
    exit_conditions: list[dict],
    position_size_pct: float = 95,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
) -> ToolResult  # Returns strategy JSON + validation status

# 2. Backtest Execution
run_backtest(
    strategy_name: str,  # Name of previously created strategy
    symbol: str = "SPY",
    start_date: str = "2020-01-01",
    end_date: str = "2024-01-01",
    initial_capital: float = 100000,
) -> ToolResult  # Returns full metrics + trade list

# 3. Data Queries
check_available_data(
    symbol: str | None = None,  # None = list all
) -> ToolResult  # Returns available symbols, date ranges

# 4. Strategy Analysis
analyze_backtest(
    backtest_id: str,
) -> ToolResult  # Returns insights: "High drawdown suggests...", "Consider adding..."

# 5. Strategy Modification
modify_strategy(
    strategy_name: str,
    changes: dict,  # {"stop_loss_pct": 0.03, "indicators.fast_ema.period": 10}
) -> ToolResult  # Returns updated strategy
```

**Acceptance Criteria**:
- [ ] Each tool returns structured ToolResult
- [ ] Tool errors are descriptive and actionable
- [ ] Results include trace_id for debugging

---

### T3: LLM Client Abstraction
**Priority**: P0
**Effort**: 3 hours

Create a unified interface for LLM providers.

**File**: `src/quant_agent/agent/llm.py`

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]

class LLMClient(ABC):
    """Abstract LLM client."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> Message:
        """Send messages and get response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens."""
        ...

class AnthropicClient(LLMClient):
    """Claude implementation."""
    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        ...

class OpenAIClient(LLMClient):
    """GPT implementation."""
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        ...
```

**Acceptance Criteria**:
- [ ] Both clients support tool calling
- [ ] Streaming works for both
- [ ] Graceful API key handling (env vars)
- [ ] Rate limiting / retry logic

---

### T4: Agent Orchestrator
**Priority**: P0
**Effort**: 6 hours

The core agent that coordinates thinking, tool use, and responses.

**File**: `src/quant_agent/agent/orchestrator.py`

```python
class AgentOrchestrator:
    """ReAct-style agent for quant strategy development."""

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        max_iterations: int = 10,
    ):
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.memory: list[Message] = []
        self.strategies: dict[str, StrategyConfig] = {}  # In-memory strategy store
        self.backtest_results: dict[str, BacktestResult] = {}

    async def process(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process user message and yield events."""
        # Yields: ThinkingEvent, ToolCallEvent, ToolResultEvent, ResponseEvent
        ...

    def _build_system_prompt(self) -> str:
        """Build context-aware system prompt."""
        ...
```

**System Prompt** (key parts):
```
You are a quantitative trading assistant. You help users:
1. Design trading strategies using technical indicators
2. Backtest strategies on historical data
3. Analyze results and suggest improvements
4. Iterate until the user is satisfied

Available indicators: SMA, EMA, RSI, MACD, ATR, Bollinger Bands, Stochastic

When creating strategies:
- Start simple (1-2 indicators)
- Always include a stop loss
- Use 95% position sizing to leave room for costs
- Explain your reasoning

Current context:
- Strategies created: {list}
- Data available: {symbols}
- Recent backtests: {summaries}
```

**Acceptance Criteria**:
- [ ] Agent can handle multi-turn conversations
- [ ] Agent calls tools appropriately
- [ ] Agent explains its reasoning
- [ ] Agent handles errors gracefully
- [ ] Max iteration limit prevents infinite loops

---

### T5: Chat CLI Integration
**Priority**: P1
**Effort**: 2 hours

Wire up the agent to the existing `quant chat` command.

**File**: `src/quant_agent/cli.py` (update existing)

```python
@app.command()
def chat(
    model: str = typer.Option("claude", help="LLM: claude, gpt4"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start an interactive chat with the quant agent."""
    import asyncio
    asyncio.run(_chat_loop(model, verbose))

async def _chat_loop(model: str, verbose: bool):
    # Initialize agent
    llm = AnthropicClient() if model == "claude" else OpenAIClient()
    agent = AgentOrchestrator(llm=llm, tools=get_agent_tools())

    console.print(Panel.fit("Quant Agent - AI Trading Assistant"))

    while True:
        user_input = Prompt.ask("[bold green]You")
        if user_input.lower() in ("quit", "exit"):
            break

        async for event in agent.process(user_input):
            if isinstance(event, ThinkingEvent):
                if verbose:
                    console.print(f"[dim]Thinking: {event.thought}[/dim]")
            elif isinstance(event, ToolCallEvent):
                console.print(f"[yellow]→ {event.tool_name}[/yellow]")
            elif isinstance(event, ResponseEvent):
                console.print(f"[bold blue]Agent:[/bold blue] {event.content}")
```

**Acceptance Criteria**:
- [ ] Chat command starts agent session
- [ ] Tool calls are displayed
- [ ] Verbose mode shows thinking
- [ ] Clean exit handling

---

### T6: Agent Testing
**Priority**: P1
**Effort**: 3 hours

Test the agent with realistic scenarios.

**File**: `tests/test_agent.py`

```python
class TestAgentTools:
    """Test individual tool operations."""

    async def test_create_strategy(self):
        """Agent can create a valid strategy."""
        ...

    async def test_run_backtest(self):
        """Agent can run a backtest."""
        ...

class TestAgentConversation:
    """Test multi-turn conversations."""

    async def test_strategy_creation_flow(self):
        """User asks for strategy, agent creates and tests it."""
        agent = AgentOrchestrator(llm=MockLLM(), tools=get_agent_tools())

        # Simulate: "Create a simple moving average crossover strategy"
        events = [e async for e in agent.process("Create a simple SMA crossover")]

        # Should have: strategy creation, backtest, response
        assert any(e.tool_name == "create_strategy" for e in events if isinstance(e, ToolCallEvent))

    async def test_iteration_flow(self):
        """Agent can modify strategy based on feedback."""
        ...
```

**Acceptance Criteria**:
- [ ] Tools tested in isolation
- [ ] Multi-turn flows tested
- [ ] Error handling tested
- [ ] Mock LLM for deterministic tests

---

## Example Agent Session

```
You: Create a momentum strategy for SPY

Agent: I'll create a momentum strategy using RSI to identify
       oversold conditions for entry.

       → create_strategy
       → run_backtest

       Here's what I built:

       **RSI Momentum Strategy**
       - Entry: RSI(14) < 30 (oversold)
       - Exit: RSI(14) > 70 (overbought)
       - Stop Loss: 5%

       **Backtest Results (2020-2024)**
       - Total Return: 45.2%
       - Sharpe Ratio: 1.24
       - Max Drawdown: 12.3%
       - Win Rate: 62%

       The strategy performed well with good risk-adjusted returns.
       Would you like me to:
       1. Adjust the RSI thresholds?
       2. Add a trend filter (like SMA)?
       3. Test on different symbols?

You: The drawdown is too high, can you add a stop loss?

Agent: → modify_strategy (adding 3% stop loss)
       → run_backtest

       With a 3% stop loss:
       - Max Drawdown: 8.1% (improved from 12.3%)
       - Total Return: 38.5% (slight decrease)
       - Sharpe Ratio: 1.31 (improved!)

       The tighter stop loss reduced drawdown significantly
       while actually improving risk-adjusted returns.
```

---

## Deliverables

By end of Week 3:
- [ ] Working `quant chat` with agent
- [ ] Agent can create strategies from description
- [ ] Agent can run and explain backtests
- [ ] Agent can iterate based on feedback
- [ ] Basic test coverage

---

## Dependencies

- `anthropic` - Claude API client
- `openai` - GPT API client (optional)

Already in `pyproject.toml`.

---

## Notes

- Start with Anthropic (Claude) - better at tool use
- Keep system prompt focused and concise
- Log all tool calls for debugging
- Store strategies in memory for session (persist to disk later)
