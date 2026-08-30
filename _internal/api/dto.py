"""HTTP-facing DTOs, decoupled from the domain entities in multi_agent/entity.py."""

from uuid import UUID

from pydantic import BaseModel, Field


class ProcessMessageRequest(BaseModel):
    """Body of POST /multi-agent/process-message."""

    user_id: UUID
    thread_id: UUID
    content: str = Field(min_length=1, max_length=8000)


class ProcessMessageResponse(BaseModel):
    """Response of POST /multi-agent/process-message."""

    content: str
    blocked: bool = False
    blocked_reason: str | None = None
    agent_trace: list[str] = []
    report_url: str | None = None
