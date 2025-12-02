"""Base classes for the tool system."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result from a tool execution."""
    
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "trace_id": self.trace_id,
        }


class Tool(ABC):
    """Base class for all tools.
    
    Tools are the interface between the agent and the underlying systems.
    They provide a standard way to:
    - Describe what the tool does (for LLM)
    - Define parameters (JSON Schema for validation)
    - Execute operations
    - Return structured results
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM."""
        ...
    
    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for tool parameters."""
        ...
    
    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given parameters."""
        ...
    
    def to_openai_function(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
    
    def to_anthropic_tool(self) -> dict:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    """Registry for managing tools."""
    
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def get_openai_functions(self) -> list[dict]:
        """Get all tools in OpenAI function format."""
        return [tool.to_openai_function() for tool in self._tools.values()]
    
    def get_anthropic_tools(self) -> list[dict]:
        """Get all tools in Anthropic tool format."""
        return [tool.to_anthropic_tool() for tool in self._tools.values()]
    
    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool by name."""
        tool = self.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {name}",
            )
        
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}",
            )

