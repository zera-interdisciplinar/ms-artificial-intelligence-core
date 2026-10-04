import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from _internal.admin_core.client import AdminCoreLogin
from _internal.mcp.server import ASK_ZERA_DESCRIPTION, ask_zera_impl, build_mcp, login_impl
from _internal.mcp.session import McpSessionStore
from multi_agent.entity import AgentResponse
from multi_agent.exception import UnitMismatchException


def test_ask_zera_description_names_the_four_specialists():
    text = ASK_ZERA_DESCRIPTION.lower()
    assert "faq" in text
    assert "inventory" in text
    assert "time-to-failure" in text
    assert "report" in text
    assert "do not call" in text


def test_build_mcp_has_login_and_ask_zera_only():
    mcp = build_mcp(MagicMock(), MagicMock(), ttl_seconds=60)
    names = set(mcp._tool_manager._tools.keys())
    assert names == {"login", "ask_zera"}


def test_login_stores_session_and_hides_token():
    admin = MagicMock()
    user_id = uuid4()
    unit_id = uuid4()
    admin.login = AsyncMock(return_value=AdminCoreLogin(access_token="secret-jwt", user_id=user_id))
    admin.get_unit_id = AsyncMock(return_value=unit_id)
    store = McpSessionStore(60)

    result = asyncio.run(login_impl(admin, store, "a@b.c", "pw"))

    assert result["ok"] is True
    assert result["user_id"] == str(user_id)
    assert result["unit_id"] == str(unit_id)
    assert "session_handle" in result
    assert "secret-jwt" not in str(result)
    session = store.get(result["session_handle"])
    assert session is not None
    assert session.authorization == "Bearer secret-jwt"


def test_ask_zera_uses_session_not_model_ids():
    service = MagicMock()
    service.process_message = AsyncMock(return_value=AgentResponse(content="ok", agent_trace=["faq"]))
    store = McpSessionStore(60)
    user_id, unit_id, thread_id = uuid4(), uuid4(), uuid4()
    store.put("handle", "Bearer tok", user_id, unit_id)

    result = asyncio.run(ask_zera_impl(service, store, "handle", "O que é o Zera?", str(thread_id)))

    assert result["content"] == "ok"
    service.process_message.assert_awaited_once_with(
        "O que é o Zera?", user_id, thread_id, unit_id, "Bearer tok"
    )


def test_ask_zera_without_login_raises():
    with pytest.raises(ValueError, match="not logged in"):
        asyncio.run(ask_zera_impl(MagicMock(), McpSessionStore(60), "missing", "hi", str(uuid4())))


def test_ask_zera_unit_mismatch_propagates():
    service = MagicMock()
    service.process_message = AsyncMock(side_effect=UnitMismatchException("nope"))
    store = McpSessionStore(60)
    store.put("s", "Bearer t", uuid4(), uuid4())
    with pytest.raises(UnitMismatchException):
        asyncio.run(ask_zera_impl(service, store, "s", "x", str(uuid4())))
