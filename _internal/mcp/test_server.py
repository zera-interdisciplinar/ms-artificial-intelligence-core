import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from multi_agent.entity import AgentResponse

from _internal.mcp.server import ask_zera_impl

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
UNIT_ID = UUID("33333333-3333-3333-3333-333333333333")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")


def _bearer(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"Bearer header.{body}.sig"


def test_ask_zera_resolves_the_unit_and_returns_the_thread():
    service = MagicMock()
    service.process_message = AsyncMock(return_value=AgentResponse(content="resposta"))
    admin_core = MagicMock()
    admin_core.get_unit_id = AsyncMock(return_value=UNIT_ID)

    body = asyncio.run(
        ask_zera_impl(
            service,
            admin_core,
            MagicMock(),
            _bearer({"sub": str(USER_ID)}),
            "quanto tempo até falhar?",
            str(THREAD_ID),
        )
    )

    assert body["content"] == "resposta"
    assert body["thread_id"] == str(THREAD_ID)
    service.process_message.assert_awaited_once()
    assert service.process_message.await_args.args[1] == USER_ID
    assert service.process_message.await_args.args[3] == UNIT_ID


def test_ask_zera_logs_and_reraises_when_the_caller_is_rejected():
    logger = MagicMock()

    with pytest.raises(ValueError, match="missing bearer token"):
        asyncio.run(
            ask_zera_impl(MagicMock(), MagicMock(), logger, "token", "oi", None)
        )

    logger.Warning.assert_called_once()
    assert "missing bearer token" in logger.Warning.call_args.args[0]
