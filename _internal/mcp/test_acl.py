import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from multi_agent.entity import AgentResponse

from _internal.mcp.acl import acl_process_message

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_acl_calls_process_message_letting_the_core_resolve_the_unit():
    service = MagicMock()
    service.process_message = AsyncMock(
        return_value=AgentResponse(content="ok", agent_trace=["faq"])
    )

    response = asyncio.run(
        acl_process_message(service, "quais perfis existem?", THREAD_ID, USER_ID, "Bearer t")
    )

    assert response.content == "ok"
    service.process_message.assert_awaited_once_with(
        "quais perfis existem?", USER_ID, THREAD_ID, None, "Bearer t"
    )
