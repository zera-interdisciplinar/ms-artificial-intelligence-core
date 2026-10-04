"""In-memory MCP login sessions. JWT never leaves this process."""

from dataclasses import dataclass
from time import monotonic
from uuid import UUID


@dataclass(frozen=True)
class McpAuthSession:
    authorization: str
    user_id: UUID
    unit_id: UUID
    expires_at: float


class McpSessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, McpAuthSession] = {}

    def put(self, session_id: str, authorization: str, user_id: UUID, unit_id: UUID) -> None:
        self._sessions[session_id] = McpAuthSession(
            authorization=authorization,
            user_id=user_id,
            unit_id=unit_id,
            expires_at=monotonic() + self._ttl_seconds,
        )

    def get(self, session_id: str) -> McpAuthSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if monotonic() >= session.expires_at:
            self._sessions.pop(session_id, None)
            return None
        return session
