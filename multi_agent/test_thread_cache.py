from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from langchain.messages import AIMessage, HumanMessage, SystemMessage

from .entity import Message, Role, UserPreferences
from .thread_cache import ThreadCacheEntry, ThreadCache, message_to_base_message, render_preferences

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")


def _entry(thread_id: UUID = THREAD_ID, last_access: datetime | None = None) -> ThreadCacheEntry:
    entry = ThreadCacheEntry(user_id=USER_ID, thread_id=thread_id)
    if last_access is not None:
        entry.last_access = last_access
    return entry


class TestMessageToBaseMessage:
    def test_user_role_becomes_human_message(self):
        message = Message(user_id=USER_ID, thread_id=THREAD_ID, role=Role.USER, content="oi", created_at=datetime.now(timezone.utc))
        assert isinstance(message_to_base_message(message), HumanMessage)

    def test_assistant_role_becomes_ai_message(self):
        message = Message(user_id=USER_ID, thread_id=THREAD_ID, role=Role.ASSISTANT, content="olá", created_at=datetime.now(timezone.utc))
        assert isinstance(message_to_base_message(message), AIMessage)

    def test_system_role_becomes_system_message(self):
        message = Message(user_id=USER_ID, thread_id=THREAD_ID, role=Role.SYSTEM, content="aviso", created_at=datetime.now(timezone.utc))
        assert isinstance(message_to_base_message(message), SystemMessage)


class TestRenderPreferences:
    def test_renders_every_known_field(self):
        preferences = UserPreferences(
            user_id=USER_ID,
            writing_style="Informal",
            company_context="TI",
            frequent_requests=["relatório mensal"],
            updated_at=datetime.now(timezone.utc),
        )
        text = render_preferences(preferences)
        assert "Informal" in text
        assert "TI" in text
        assert "relatório mensal" in text

    def test_omits_unset_fields(self):
        preferences = UserPreferences(user_id=USER_ID, updated_at=datetime.now(timezone.utc))
        assert render_preferences(preferences) == ""


class TestThreadCache:
    def test_get_returns_none_on_cache_miss(self):
        cache = ThreadCache(ttl_seconds=60)
        assert cache.get(THREAD_ID) is None

    def test_get_returns_a_cached_entry(self):
        cache = ThreadCache(ttl_seconds=60)
        entry = _entry()
        cache.put(entry)

        assert cache.get(THREAD_ID) is entry

    def test_get_evicts_an_expired_entry(self):
        cache = ThreadCache(ttl_seconds=60)
        cache.put(_entry(last_access=datetime.now(timezone.utc) - timedelta(seconds=120)))

        assert cache.get(THREAD_ID) is None

    def test_get_touches_last_access(self):
        cache = ThreadCache(ttl_seconds=60)
        entry = _entry(last_access=datetime.now(timezone.utc) - timedelta(seconds=30))
        cache.put(entry)
        before = entry.last_access

        cache.get(THREAD_ID)

        assert entry.last_access > before

    def test_sweep_removes_and_returns_only_expired_entries(self):
        cache = ThreadCache(ttl_seconds=60)
        fresh = _entry(thread_id=THREAD_ID)
        expired = _entry(thread_id=uuid4(), last_access=datetime.now(timezone.utc) - timedelta(seconds=120))
        cache.put(fresh)
        cache.put(expired)

        swept = cache.sweep()

        assert swept == [expired]
        assert cache.get(THREAD_ID) is fresh
        assert cache._entries.get(expired.thread_id) is None

    def test_sweep_returns_an_entry_only_once(self):
        cache = ThreadCache(ttl_seconds=60)
        cache.put(_entry(last_access=datetime.now(timezone.utc) - timedelta(seconds=120)))

        assert len(cache.sweep()) == 1
        assert cache.sweep() == []
