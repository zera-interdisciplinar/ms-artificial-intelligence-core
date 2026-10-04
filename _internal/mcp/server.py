"""MCP tools: login (admin-core proxy) and ask_zera (process_message)."""

from uuid import UUID, uuid4

from mcp.server.fastmcp import FastMCP

from _internal.admin_core.client import AdminCoreClient
from _internal.mcp.session import McpSessionStore
from multi_agent.entity import AgentResponse
from multi_agent.multi_agent import IMultiAgentService

ASK_ZERA_DESCRIPTION = """Ask the Zera multi-agent assistant (guardrails + orchestrator + specialists).
Use only when the user goal matches a Zera specialist:
(1) FAQ about the Zera platform,
(2) factual inventory already stored (item, batch, battery, warranty, hazardous checklist),
(3) predicted time-to-failure for equipment,
(4) disposal report text (not PDF).
Do not call for general chat, coding, or topics outside those four.
Call login first. Pass content, thread_id, and the session_handle login returned.
"""

LOGIN_DESCRIPTION = """Log in with the worker's Zera email and password (ms-administrative-core).
Call once per session. Do not echo the password afterwards. Does not return the access token.
Returns session_handle for ask_zera.
"""


async def login_impl(
    admin_core: AdminCoreClient,
    store: McpSessionStore,
    email: str,
    password: str,
) -> dict:
    result = await admin_core.login(email, password)
    if result is None:
        return {"ok": False, "error": "invalid credentials"}
    authorization = f"Bearer {result.access_token}"
    unit_id = await admin_core.get_unit_id(result.user_id, authorization)
    if unit_id is None:
        return {"ok": False, "error": "could not resolve unit"}
    session_handle = str(uuid4())
    store.put(session_handle, authorization, result.user_id, unit_id)
    return {
        "ok": True,
        "user_id": str(result.user_id),
        "unit_id": str(unit_id),
        "session_handle": session_handle,
    }


async def ask_zera_impl(
    service: IMultiAgentService,
    store: McpSessionStore,
    session_handle: str,
    content: str,
    thread_id: str,
) -> dict:
    session = store.get(session_handle)
    if session is None:
        raise ValueError("not logged in; call login first")
    response: AgentResponse = await service.process_message(
        content, session.user_id, UUID(thread_id), session.unit_id, session.authorization
    )
    return response.model_dump(mode="json")


def build_mcp(
    service: IMultiAgentService,
    admin_core: AdminCoreClient,
    ttl_seconds: int,
) -> FastMCP:
    mcp = FastMCP(
        "zera",
        instructions=ASK_ZERA_DESCRIPTION,
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )
    store = McpSessionStore(ttl_seconds)

    @mcp.tool(name="login", description=LOGIN_DESCRIPTION)
    async def login(email: str, password: str) -> dict:
        return await login_impl(admin_core, store, email, password)

    @mcp.tool(name="ask_zera", description=ASK_ZERA_DESCRIPTION)
    async def ask_zera(content: str, thread_id: str, session_handle: str) -> dict:
        return await ask_zera_impl(service, store, session_handle, content, thread_id)

    return mcp
