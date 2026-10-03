"""HTTP-facing DTOs, decoupled from the domain entities in multi_agent/entity.py."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from multi_agent.entity import Role


class ProcessMessageRequest(BaseModel):
    """Body of POST /multi-agent/process-message."""

    user_id: UUID
    thread_id: UUID
    unit_id: UUID  # proposed by the caller, validated against ms-administrative-core
    content: str = Field(min_length=1, max_length=8000)


class ProcessMessageResponse(BaseModel):
    """Response of POST /multi-agent/process-message."""

    content: str
    blocked: bool = False
    blocked_reason: str | None = None
    agent_trace: list[str] = []
    report_url: str | None = None


class ConversationPreviewResponse(BaseModel):
    """One row of GET /multi-agent/conversations."""

    thread_id: UUID
    last_message_at: datetime
    preview: str


class ConversationListResponse(BaseModel):
    """A page of GET /multi-agent/conversations."""

    items: list[ConversationPreviewResponse]
    page: int
    page_size: int
    total: int


class ConversationMessageResponse(BaseModel):
    """One message of GET /multi-agent/conversations/{thread_id}."""

    role: Role
    content: str
    created_at: datetime
