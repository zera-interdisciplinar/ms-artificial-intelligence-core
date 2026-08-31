"""Tracks which LangGraph threads are "warm" (hydrated from Mongo into the
shared MemorySaver/compiled graph, both built once in MultiAgentService.setup())
and for how long. A thread is the LangGraph unit of conversation identity
(thread_id); this module has no concept of its own beyond that — it just
caches, per thread_id, whether that thread's checkpoint is already seeded and
since when, so a thread hydrates once and its checkpoint entry is dropped from
the shared saver after TTL_SECONDS of inactivity. Expired entries are swept
lazily (on the next request from anyone) so preferences can be updated once,
over the whole conversation, instead of on every turn.
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
class ThreadCacheEntry:
    user_id: UUID
    thread_id: UUID
    last_access: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.last_access = datetime.now(timezone.utc)


class ThreadCache:
    """In-process map of thread_id -> ThreadCacheEntry.

    # ponytail: plain dict with lazy sweep on access; move to Redis if this
    # ever runs with more than one replica.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._entries: dict[UUID, ThreadCacheEntry] = {}

    def get(self, thread_id: UUID) -> ThreadCacheEntry | None:
        entry = self._entries.get(thread_id)
        if entry is None:
            return None
        if self._is_expired(entry):
            return None
        entry.touch()
        return entry

    def put(self, entry: ThreadCacheEntry) -> None:
        self._entries[entry.thread_id] = entry

    def sweep(self) -> list[ThreadCacheEntry]:
        """Removes and returns every entry whose TTL has expired."""

        expired = [e for e in self._entries.values() if self._is_expired(e)]
        for entry in expired:
            del self._entries[entry.thread_id]
        return expired

    def _is_expired(self, entry: ThreadCacheEntry) -> bool:
        return datetime.now(timezone.utc) - entry.last_access > self._ttl
