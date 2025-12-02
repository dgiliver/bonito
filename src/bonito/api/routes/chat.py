"""Chat endpoint with SSE streaming."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bonito.agent.llm import get_llm_client
from bonito.agent.orchestrator import (
    AgentOrchestrator,
    ErrorEvent,
    ResponseEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from bonito.agent.tools import get_agent_tools

router = APIRouter()

# Store agent sessions (in production, use Redis or database)
_sessions: dict[str, AgentOrchestrator] = {}


class ChatRequest(BaseModel):
    """Chat request body."""

    message: str
    session_id: str | None = None
    model: str = "anthropic"  # "anthropic" or "openai"


class ChatMessage(BaseModel):
    """Chat message for history."""

    role: str
    content: str


def _get_or_create_session(session_id: str | None, model: str) -> tuple[str, AgentOrchestrator]:
    """Get existing session or create new one."""
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]

    # Create new session
    import uuid

    new_id = session_id or str(uuid.uuid4())[:8]
    llm = get_llm_client(model)
    registry, _, _ = get_agent_tools()
    agent = AgentOrchestrator(llm=llm, tools=registry)

    _sessions[new_id] = agent
    return new_id, agent


@router.post("")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Process chat message and stream response.

    Returns Server-Sent Events (SSE) with agent events.

    Event types:
    - tool_call: Agent is calling a tool
    - tool_result: Tool returned a result
    - response: Final agent response
    - error: An error occurred
    - done: Stream complete
    """

    async def generate() -> AsyncGenerator[str, None]:
        try:
            session_id, agent = _get_or_create_session(request.session_id, request.model)

            # Send session ID first
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            async for event in agent.process(request.message):
                if isinstance(event, ToolCallEvent):
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': event.tool_name, 'args': event.arguments})}\n\n"

                elif isinstance(event, ToolResultEvent):
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': event.tool_name, 'success': event.success, 'data': event.result})}\n\n"

                elif isinstance(event, ResponseEvent):
                    yield f"data: {json.dumps({'type': 'response', 'content': event.content})}\n\n"

                elif isinstance(event, ErrorEvent):
                    yield f"data: {json.dumps({'type': 'error', 'error': event.error})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """List active chat sessions."""
    sessions = []
    for session_id, agent in _sessions.items():
        sessions.append(
            {
                "session_id": session_id,
                "message_count": len(agent.messages),
            }
        )
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a chat session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    del _sessions[session_id]
    return {"status": "deleted", "session_id": session_id}


@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: str) -> dict[str, str]:
    """Reset a chat session (clear history)."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    _sessions[session_id].reset()
    return {"status": "reset", "session_id": session_id}
