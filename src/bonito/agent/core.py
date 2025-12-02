"""Core agent implementation."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from anthropic import Anthropic

from bonito.agent.prompts import SYSTEM_PROMPT
from bonito.config import settings
from bonito.tools import ToolRegistry, create_default_registry


@dataclass
class Message:
    """A conversation message."""

    role: Literal["user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass
class AgentSession:
    """Session state for an agent conversation."""

    messages: list[Message] = field(default_factory=list)
    strategies: dict[str, dict] = field(default_factory=dict)
    iteration_count: int = 0

    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self.messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message."""
        self.messages.append(Message(role="assistant", content=content))

    def to_anthropic_messages(self) -> list[dict]:
        """Convert to Anthropic message format."""
        return [
            {"role": m.role, "content": m.content}
            for m in self.messages
            if m.role in ("user", "assistant")
        ]


class QuantAgent:
    """AI agent for quantitative strategy development.

    Uses Claude to generate, test, and refine trading strategies
    through an iterative conversation with tool calling.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize the agent.

        Args:
            registry: Tool registry. Uses default if not provided.
            model: LLM model to use. Uses config default if not provided.
        """
        self.registry = registry or create_default_registry()
        self.model = model or settings.default_model

        if settings.anthropic_api_key:
            self.client = Anthropic(api_key=settings.anthropic_api_key)
        else:
            self.client = None

    async def chat(
        self,
        user_message: str,
        session: AgentSession | None = None,
    ) -> AsyncIterator[str]:
        """Process a user message and stream the response.

        Args:
            user_message: The user's message
            session: Existing session or None for new session

        Yields:
            Response text chunks as they're generated
        """
        if self.client is None:
            yield "Error: No API key configured. Please set ANTHROPIC_API_KEY in your .env file."
            return

        session = session or AgentSession()
        session.add_user_message(user_message)

        # Build messages for API
        messages = session.to_anthropic_messages()

        try:
            # Call Claude with tools
            response = self.client.messages.create(
                model=self.model,
                max_tokens=settings.max_tokens,
                system=SYSTEM_PROMPT,
                tools=self.registry.get_anthropic_tools(),
                messages=messages,
            )

            # Process response
            full_response = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    full_response += block.text
                    yield block.text
                elif block.type == "tool_use":
                    tool_calls.append(block)

            # Handle tool calls
            while tool_calls and session.iteration_count < settings.max_iterations:
                session.iteration_count += 1

                # Execute tools
                tool_results = []
                for tool_call in tool_calls:
                    yield f"\n\n🔧 *Running {tool_call.name}...*\n"

                    result = await self.registry.execute(
                        tool_call.name,
                        **tool_call.input,
                    )

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call.id,
                            "content": json.dumps(result.to_dict()),
                        }
                    )

                    if result.success:
                        yield f"✅ *{tool_call.name} completed*\n\n"
                    else:
                        yield f"❌ *{tool_call.name} failed: {result.error}*\n\n"

                # Continue conversation with tool results
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=settings.max_tokens,
                    system=SYSTEM_PROMPT,
                    tools=self.registry.get_anthropic_tools(),
                    messages=messages,
                )

                # Process new response
                tool_calls = []
                for block in response.content:
                    if block.type == "text":
                        full_response += block.text
                        yield block.text
                    elif block.type == "tool_use":
                        tool_calls.append(block)

            session.add_assistant_message(full_response)

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            yield error_msg
            session.add_assistant_message(error_msg)

    async def chat_sync(
        self,
        user_message: str,
        session: AgentSession | None = None,
    ) -> str:
        """Process a user message and return the complete response.

        Non-streaming version for simpler use cases.
        """
        response_parts = []
        async for chunk in self.chat(user_message, session):
            response_parts.append(chunk)
        return "".join(response_parts)
