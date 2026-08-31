from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from multi_agent.entity import AgentName, Message, Role, UserPreferences

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def user_id() -> UUID:
    return USER_ID


@pytest.fixture
def thread_id() -> UUID:
    return THREAD_ID


@pytest.fixture
def message() -> Message:
    return Message(
        user_id=USER_ID,
        thread_id=THREAD_ID,
        role=Role.USER,
        content="Quais perfis de usuário existem no sistema Zera?",
        agent=AgentName.FAQ_AGENT,
        created_at=datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def preferences() -> UserPreferences:
    return UserPreferences(
        user_id=USER_ID,
        writing_style="Informal, direto.",
        company_context="Time de operações de TI.",
        frequent_requests=["gerar relatório mensal de descarte"],
        updated_at=datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mongo_repository():
    """A Repository double whose db behaves like a mapping of collection name to Collection."""
    repository = MagicMock()
    collections = {
        "messages": MagicMock(name="messageCollection"),
        "user_preferences": MagicMock(name="preferencesCollection"),
    }
    repository.db.__getitem__.side_effect = collections.__getitem__
    return repository
