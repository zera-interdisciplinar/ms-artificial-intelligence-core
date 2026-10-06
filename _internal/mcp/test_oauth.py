import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from _internal.mcp.oauth import ZeraOAuthProvider

USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _jwt(user_id: UUID) -> str:
    raw = json.dumps({"sub": str(user_id)}).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"header.{body}.sig"


def _provider(login_result):
    admin = MagicMock()
    admin.login = AsyncMock(return_value=login_result)
    provider = ZeraOAuthProvider(admin, "http://localhost:8000", MagicMock())
    client = OAuthClientInformationFull(
        client_id="claude",
        redirect_uris=[AnyUrl("http://localhost/callback")],
    )
    provider._clients["claude"] = client
    return provider, client


def test_submit_login_sends_claude_back_with_the_admin_access_token():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}
    )
    params = AuthorizationParams(
        state="st",
        scopes=[],
        code_challenge="challenge",
        redirect_uri=AnyUrl("http://localhost/callback"),
        redirect_uri_provided_explicitly=True,
    )

    login_url = asyncio.run(provider.authorize(client, params))
    txn = login_url.split("txn=")[1]
    redirect = asyncio.run(provider.submit_login(txn, "a@zera.dev", "secret"))

    assert redirect is not None
    assert redirect.startswith("http://localhost/callback")
    code = redirect.split("code=")[1].split("&")[0]
    token = asyncio.run(provider.exchange_authorization_code(client, provider._codes[code]))

    assert token.access_token == access
    assert token.refresh_token != "admin-refresh"
    assert asyncio.run(provider.load_access_token(access)).subject == str(USER_ID)


def test_submit_login_keeps_the_form_open_when_credentials_fail():
    provider, client = _provider(None)
    params = AuthorizationParams(
        state=None,
        scopes=[],
        code_challenge="challenge",
        redirect_uri=AnyUrl("http://localhost/callback"),
        redirect_uri_provided_explicitly=True,
    )
    login_url = asyncio.run(provider.authorize(client, params))
    txn = login_url.split("txn=")[1]

    assert asyncio.run(provider.submit_login(txn, "a@zera.dev", "nope")) is None
    assert txn in provider._pending
