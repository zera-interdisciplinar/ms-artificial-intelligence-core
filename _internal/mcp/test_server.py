import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from multi_agent.entity import AgentResponse
from multi_agent.exception import UnitMismatchException

from _internal.mcp.server import (
    _mount_issuer_metadata,
    ask_zera_impl,
    authorization_from_context,
    build_mcp,
)

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")


def _bearer(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"Bearer header.{body}.sig"


def _service(**kwargs) -> MagicMock:
    service = MagicMock()
    service.process_message = AsyncMock(**({"return_value": AgentResponse(content="resposta")} | kwargs))
    return service


def test_ask_zera_passes_the_user_and_lets_the_core_resolve_the_unit():
    service = _service()

    body = asyncio.run(
        ask_zera_impl(service, MagicMock(), _bearer({"sub": str(USER_ID)}), "quanto tempo até falhar?", str(THREAD_ID))
    )

    assert body["content"] == "resposta"
    assert body["thread_id"] == str(THREAD_ID)
    args = service.process_message.await_args.args
    assert args[1] == USER_ID
    assert args[3] is None


def test_ask_zera_logs_and_reraises_when_the_caller_is_rejected():
    logger = MagicMock()

    with pytest.raises(ValueError, match="missing bearer token"):
        asyncio.run(ask_zera_impl(MagicMock(), logger, "token", "oi", None))

    logger.Warning.assert_called_once()
    assert "missing bearer token" in logger.Warning.call_args.args[0]


def test_ask_zera_rejects_a_user_without_unit():
    service = _service(side_effect=UnitMismatchException("no unit"))
    logger = MagicMock()

    with pytest.raises(ValueError, match="could not resolve unit"):
        asyncio.run(ask_zera_impl(service, logger, _bearer({"sub": str(USER_ID)}), "oi", None))

    logger.Warning.assert_called_once()


def test_ask_zera_creates_a_thread_when_none_is_given():
    service = _service()

    body = asyncio.run(ask_zera_impl(service, MagicMock(), _bearer({"sub": str(USER_ID)}), "faq", None))

    assert UUID(body["thread_id"])
    service.process_message.assert_awaited_once()


def test_authorization_from_context_reads_the_header():
    ctx = MagicMock()
    ctx.request_context.request.headers.get.return_value = "Bearer t"
    assert authorization_from_context(ctx) == "Bearer t"


def test_authorization_from_context_rejects_missing_request_or_header():
    missing_request = MagicMock()
    missing_request.request_context.request = None
    with pytest.raises(ValueError, match="missing bearer token"):
        authorization_from_context(missing_request)

    empty = MagicMock()
    empty.request_context.request.headers.get.return_value = ""
    with pytest.raises(ValueError, match="missing bearer token"):
        authorization_from_context(empty)


def _envs(url: str = "") -> MagicMock:
    envs = MagicMock()
    envs.SELF_MCP_URL = url
    return envs


def test_build_mcp_registers_ask_zera_without_oauth_when_url_is_empty():
    mcp = build_mcp(MagicMock(), MagicMock(), MagicMock(), _envs())
    names = [tool.name for tool in asyncio.run(mcp.list_tools())]
    assert "ask_zera" in names


def test_build_mcp_with_oauth_requires_a_shared_store():
    with pytest.raises(AssertionError, match="shared store"):
        build_mcp(MagicMock(), MagicMock(), MagicMock(), _envs("https://example.com/ai-core"))


def test_ask_zera_tool_logs_and_reraises_without_bearer():
    logger = MagicMock()
    mcp = build_mcp(MagicMock(), MagicMock(), logger, _envs())
    ask = mcp._tool_manager.get_tool("ask_zera").fn
    ctx = MagicMock()
    ctx.request_context.request = None
    with pytest.raises(ValueError, match="missing bearer token"):
        asyncio.run(ask(content="oi", ctx=ctx))
    logger.Warning.assert_called()


def test_ask_zera_tool_forwards_to_the_impl():
    service = _service(return_value=AgentResponse(content="ok"))
    mcp = build_mcp(service, MagicMock(), MagicMock(), _envs())
    ask = mcp._tool_manager.get_tool("ask_zera").fn
    ctx = MagicMock()
    ctx.request_context.request.headers.get.return_value = _bearer({"sub": str(USER_ID)})
    body = asyncio.run(ask(content="faq", ctx=ctx, thread_id=str(THREAD_ID)))
    assert body["content"] == "ok"


def test_mount_issuer_metadata_skips_root_issuer():
    mcp = MagicMock()
    _mount_issuer_metadata(mcp, "https://example.com")
    mcp.custom_route.assert_not_called()
