"""
MCP server implementation.
This part here is responsible for the MCP server implementation.

It have two main flows:

- login flow: the user will be redirected to the login page of the platform to authenticate and grant access to the MCP server. The authentication will be done using the admin core client. The client will keep the access token in their logic.
- process message flow: the user will send a message to the MCP server and the server will process the message and return the response. The message will be processed by the multi agent service.
"""

from uuid import UUID, uuid4

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from _internal.admin_core.client import AdminCoreClient
from _internal.mcp.acl import acl_process_message
from _internal.mcp.auth import resolve_caller
from _internal.mcp.oauth import ZeraOAuthProvider, mount_login
from config.environments import Environments
from logger.logger import Logger
from multi_agent.multi_agent import IMultiAgentService

ASK_ZERA_DESCRIPTION = """Ask the Zera multi-agent assistant (guardrails + orchestrator + specialists).
Use only when the user goal matches a Zera specialist:
(1) FAQ about the Zera platform,
(2) factual inventory already stored (item, batch, battery, warranty, hazardous checklist),
(3) predicted time-to-failure for equipment,
(4) disposal report text (not PDF).
Do not call for general chat, coding, or topics outside those four.
The host already holds the Bearer token. Pass content and, to continue a thread, thread_id.
"""


def authorization_from_context(ctx: Context) -> str:
    """The Bearer the connector sends on the HTTP request. Not a tool argument."""

    request = ctx.request_context.request
    if request is None:
        raise ValueError("missing bearer token")

    authorization = request.headers.get("authorization", "")
    if not authorization:
        raise ValueError("missing bearer token")

    return authorization


async def ask_zera_impl(
    service: IMultiAgentService,
    admin_core: AdminCoreClient,
    logger: Logger,
    authorization: str,
    content: str,
    thread_id: str | None,
) -> dict:
    """
    Process message flow. Resolve who is calling, then hand the text to the ACL.
    A missing thread id starts a new conversation.
    """

    # resolve the caller and its unit id from the authorization token
    # a bad token or an unknown unit is a client rejection, same as the API's 403 log
    try:
        user_id, unit_id = await resolve_caller(admin_core, authorization)
    except ValueError as e:
        logger.Warning(f"Rejected ask_zera caller: {e}")
        raise

    # if no thread is provided, a new one is created
    parsed_thread_id = UUID(thread_id) if thread_id else uuid4()
    
    response = await acl_process_message(
        service, content, parsed_thread_id, user_id, unit_id, authorization
    )
    body = response.model_dump(mode="json")
    body["thread_id"] = str(parsed_thread_id)
    return body


def build_mcp(
    service: IMultiAgentService,
    admin_core: AdminCoreClient,
    logger: Logger,
    envs: Environments,
) -> FastMCP:
    """
    One tool. The host decides when to call it. Specialists stay inside the graph.
    When SELF_MCP_URL is set, Claude can log in and store the Bearer.
    """

    auth = None
    provider = None
    if envs.SELF_MCP_URL:
        issuer = AnyHttpUrl(envs.SELF_MCP_URL)
        provider = ZeraOAuthProvider(admin_core, envs.SELF_MCP_URL, logger)
        auth = AuthSettings(
            issuer_url=issuer,
            resource_server_url=issuer,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )

    mcp = FastMCP(
        "zera",
        instructions=ASK_ZERA_DESCRIPTION,
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
        auth=auth,
        auth_server_provider=provider,
        # Behind the gateway the Host header is not localhost. The edge does TLS.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    if provider is not None:
        mount_login(mcp, provider)

    @mcp.tool(name="ask_zera", description=ASK_ZERA_DESCRIPTION)
    async def ask_zera(content: str, ctx: Context, thread_id: str | None = None) -> dict:
        try:
            authorization = authorization_from_context(ctx)
        except ValueError as e:
            logger.Warning(f"Rejected ask_zera caller: {e}")
            raise
        return await ask_zera_impl(service, admin_core, logger, authorization, content, thread_id)

    return mcp
