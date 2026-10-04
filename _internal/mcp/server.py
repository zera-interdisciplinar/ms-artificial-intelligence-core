"""MCP tools: login (admin-core proxy) and ask_zera (process_message)."""

from uuid import UUID, uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

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
        # ponytail: FastMCP defaults host=127.0.0.1 and then only allows localhost
        # Host headers. Behind Kong the Host is the LB IP/DNS. Kong is the edge;
        # when we have a real hostname, set allowed_hosts instead of disabling.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    store = McpSessionStore(ttl_seconds)

    @mcp.tool(name="login", description=LOGIN_DESCRIPTION)
    async def login(email: str, password: str) -> dict:
        return await login_impl(admin_core, store, email, password)

    @mcp.tool(name="ask_zera", description=ASK_ZERA_DESCRIPTION)
    async def ask_zera(content: str, thread_id: str, session_handle: str) -> dict:
        return await ask_zera_impl(service, store, session_handle, content, thread_id)

    return mcp


def wrap_chatgpt_mcp(app):
    """ChatGPT's connector GETs /mcp without Accept: text/event-stream (406).

    Probe GETs get 200 JSON. Other methods get Accept patched so Streamable HTTP
    does not 406 when the host omits the header.
    """

    async def inner(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        method = scope.get("method", b"")
        if isinstance(method, bytes):
            method = method.decode()
        headers = list(scope.get("headers") or [])
        accept = b""
        for key, value in headers:
            if key == b"accept":
                accept = value.lower()
                break
        if method == "GET" and b"text/event-stream" not in accept:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"ok":true}'})
            return
        needed = []
        if b"application/json" not in accept:
            needed.append(b"application/json")
        if b"text/event-stream" not in accept:
            needed.append(b"text/event-stream")
        if needed:
            patched = accept + (b", " if accept else b"") + b", ".join(needed)
            new_headers = []
            found = False
            for key, value in headers:
                if key == b"accept":
                    new_headers.append((key, patched))
                    found = True
                else:
                    new_headers.append((key, value))
            if not found:
                new_headers.append((b"accept", patched))
            scope = {**scope, "headers": new_headers}
        await app(scope, receive, send)

    return inner
