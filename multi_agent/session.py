"""Per-thread session bookkeeping on top of ONE shared MemorySaver/compiled
graph (both built once in MultiAgentService.setup()): the checkpointer already
partitions state by thread_id via config, so there's no need for a saver or a
compile() per thread. This module only tracks which threads are "warm"
(hydrated from Mongo) and for how long, so a thread hydrates once and its
checkpoint entry is dropped from the shared saver after SESSION_TTL_SECONDS of
inactivity. Expired sessions are swept lazily (on the next request from
anyone) so their preferences can be updated once, over the whole conversation,
instead of on every turn.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages import BaseMessage

from .entity import Message, Role, UserPreferences


def message_to_base_message(message: Message) -> BaseMessage:
    """Converts a persisted Message into the BaseMessage LangGraph expects."""

    if message.role == Role.USER:
        return HumanMessage(content=message.content)
    if message.role == Role.ASSISTANT:
        return AIMessage(content=message.content)
    return SystemMessage(content=message.content)


def render_preferences(preferences: UserPreferences) -> str:
    """Renders UserPreferences into the plain-text block injected into State.user_preferences."""

    parts = []
    if preferences.writing_style:
        parts.append(f"Estilo de escrita: {preferences.writing_style}")
    if preferences.company_context:
        parts.append(f"Contexto na empresa: {preferences.company_context}")
    if preferences.frequent_requests:
        parts.append(f"Pedidos frequentes: {', '.join(preferences.frequent_requests)}")
    return " | ".join(parts)


@dataclass
class Session:
    user_id: UUID
    thread_id: UUID
    last_access: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.last_access = datetime.now(timezone.utc)


class SessionStore:
    """In-process cache of Session by thread_id.

    # ponytail: plain dict with lazy sweep on access; move to Redis if this
    # ever runs with more than one replica.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[UUID, Session] = {}

    def get(self, thread_id: UUID) -> Session | None:
        session = self._sessions.get(thread_id)
        if session is None:
            return None
        if self._is_expired(session):
            return None
        session.touch()
        return session

    def put(self, session: Session) -> None:
        self._sessions[session.thread_id] = session

    def sweep(self) -> list[Session]:
        """Removes and returns every session whose TTL has expired."""

        expired = [s for s in self._sessions.values() if self._is_expired(s)]
        for session in expired:
            del self._sessions[session.thread_id]
        return expired

    def _is_expired(self, session: Session) -> bool:
        return datetime.now(timezone.utc) - session.last_access > self._ttl
