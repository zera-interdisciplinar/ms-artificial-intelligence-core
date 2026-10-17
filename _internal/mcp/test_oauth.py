import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from mcp.server.auth.provider import AuthorizationParams, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from _internal.mcp.oauth import ZeraOAuthProvider, mount_login

USER_ID = UUID("11111111-1111-1111-1111-111111111111")


class _FakeRedis:
    """The three commands the provider uses, with the TTL each key was written with."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int | None] = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttl[key] = ex

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)


def _jwt(user_id: UUID) -> str:
    raw = json.dumps({"sub": str(user_id)}).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"header.{body}.sig"


def _provider(login_result, refresh_result=None, store=None):
    admin = MagicMock()
    admin.login = AsyncMock(return_value=login_result)
    admin.refresh = AsyncMock(return_value=refresh_result)
    provider = ZeraOAuthProvider(admin, "http://localhost:8000", MagicMock(), store or _FakeRedis())
    client = OAuthClientInformationFull(
        client_id="claude",
        redirect_uris=[AnyUrl("http://localhost/callback")],
    )
    asyncio.run(provider.register_client(client))
    return provider, client


def _login(provider, client):
    login_url = asyncio.run(provider.authorize(client, _params()))
    txn = login_url.split("txn=")[1]
    redirect = asyncio.run(provider.submit_login(txn, "a@zera.dev", "secret"))
    code = redirect.split("code=")[1].split("&")[0]
    stored = asyncio.run(provider.load_authorization_code(client, code))
    return asyncio.run(provider.exchange_authorization_code(client, stored))


def _params():
    return AuthorizationParams(
        state="st",
        scopes=["ask"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("http://localhost/callback"),
        redirect_uri_provided_explicitly=True,
    )


class _Routes:
    def __init__(self):
        self.handlers = {}

    def custom_route(self, path, methods):
        def deco(fn):
            for method in methods:
                self.handlers[(path, method)] = fn
            return fn

        return deco


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
    token = asyncio.run(provider.exchange_authorization_code(client, asyncio.run(provider.load_authorization_code(client, code))))

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
    assert asyncio.run(provider.has_pending(txn))


def test_submit_login_returns_none_for_unknown_txn():
    provider, _ = _provider(None)
    assert asyncio.run(provider.submit_login("missing", "a@zera.dev", "secret")) is None


def test_register_and_get_client():
    provider, _ = _provider(None)
    client = OAuthClientInformationFull(
        client_id="",
        redirect_uris=[AnyUrl("http://localhost/callback")],
    )
    asyncio.run(provider.register_client(client))
    assert client.client_id
    assert asyncio.run(provider.get_client(client.client_id)) == client


def test_load_authorization_code_rejects_unknown_or_wrong_client():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}
    )
    login_url = asyncio.run(provider.authorize(client, _params()))
    txn = login_url.split("txn=")[1]
    redirect = asyncio.run(provider.submit_login(txn, "a@zera.dev", "secret"))
    code = redirect.split("code=")[1].split("&")[0]
    other = OAuthClientInformationFull(
        client_id="other",
        redirect_uris=[AnyUrl("http://localhost/callback")],
    )
    assert asyncio.run(provider.load_authorization_code(other, code)) is None
    assert asyncio.run(provider.load_authorization_code(client, "nope")) is None
    stored = asyncio.run(provider.load_authorization_code(client, code))
    assert stored is not None
    assert stored.code == code


def test_exchange_refresh_token_issues_a_new_admin_access():
    access = _jwt(USER_ID)
    new_access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600},
        {"accessToken": new_access, "refreshToken": "admin-refresh-2", "expiresIn": 1200},
    )
    login_url = asyncio.run(provider.authorize(client, _params()))
    txn = login_url.split("txn=")[1]
    redirect = asyncio.run(provider.submit_login(txn, "a@zera.dev", "secret"))
    code = redirect.split("code=")[1].split("&")[0]
    token = asyncio.run(provider.exchange_authorization_code(client, asyncio.run(provider.load_authorization_code(client, code))))
    stored = asyncio.run(provider.load_refresh_token(client, token.refresh_token))
    refreshed = asyncio.run(provider.exchange_refresh_token(client, stored, ["ask"]))
    assert refreshed.access_token == new_access
    assert asyncio.run(provider.load_refresh_token(client, token.refresh_token)) is None


def test_exchange_refresh_token_raises_when_admin_rejects():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600},
        None,
    )
    login_url = asyncio.run(provider.authorize(client, _params()))
    txn = login_url.split("txn=")[1]
    redirect = asyncio.run(provider.submit_login(txn, "a@zera.dev", "secret"))
    code = redirect.split("code=")[1].split("&")[0]
    token = asyncio.run(provider.exchange_authorization_code(client, asyncio.run(provider.load_authorization_code(client, code))))
    stored = asyncio.run(provider.load_refresh_token(client, token.refresh_token))
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_refresh_token(client, stored, ["ask"]))
    assert asyncio.run(provider.load_refresh_token(client, token.refresh_token)) is None


def test_load_access_token_returns_none_after_expiry():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}
    )
    _login(provider, client)
    stored = asyncio.run(provider.load_access_token(access))
    asyncio.run(provider._put("access", access, stored.model_copy(update={"expires_at": int(time.time()) - 1}), 1))

    assert asyncio.run(provider.load_access_token(access)) is None


def test_refresh_grant_dies_with_the_platform_login():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}
    )
    token = _login(provider, client)
    stored = asyncio.run(provider.load_refresh_token(client, token.refresh_token))
    assert stored.expires_at <= int(time.time()) + 3600
    assert stored.resource == _params().resource
    asyncio.run(provider._put("refresh", token.refresh_token, stored.model_copy(update={"expires_at": int(time.time()) - 1}), 1))

    assert asyncio.run(provider.load_refresh_token(client, token.refresh_token)) is None


def test_refresh_without_expiry_is_dead():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}
    )
    token = _login(provider, client)
    stored = asyncio.run(provider.load_refresh_token(client, token.refresh_token))
    asyncio.run(provider._put("refresh", token.refresh_token, stored.model_copy(update={"expires_at": None}), 1))
    assert asyncio.run(provider.load_refresh_token(client, token.refresh_token)) is None


def test_revoke_drops_access_and_refresh():
    access = _jwt(USER_ID)
    provider, client = _provider({"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600})
    token = _login(provider, client)

    asyncio.run(provider.revoke_token(asyncio.run(provider.load_access_token(access))))
    asyncio.run(provider.revoke_token(asyncio.run(provider.load_refresh_token(client, token.refresh_token))))

    assert asyncio.run(provider.load_access_token(access)) is None
    assert asyncio.run(provider.load_refresh_token(client, token.refresh_token)) is None


def test_login_survives_a_restart_and_every_key_expires():
    access = _jwt(USER_ID)
    store = _FakeRedis()
    provider, client = _provider({"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}, store=store)
    token = _login(provider, client)

    restarted = ZeraOAuthProvider(MagicMock(), "http://localhost:8000", MagicMock(), store)
    assert asyncio.run(restarted.get_client("claude")) == client
    assert asyncio.run(restarted.load_access_token(access)).subject == str(USER_ID)
    assert asyncio.run(restarted.load_refresh_token(client, token.refresh_token)) is not None
    assert store.ttl["mcp:oauth:access:" + access] == 3600
    assert all(ttl for key, ttl in store.ttl.items() if not key.startswith("mcp:oauth:client:"))


def test_login_page_and_submit_routes():
    access = _jwt(USER_ID)
    provider, client = _provider(
        {"accessToken": access, "refreshToken": "admin-refresh", "expiresIn": 3600}
    )
    routes = _Routes()
    mount_login(routes, provider)
    login_url = asyncio.run(provider.authorize(client, _params()))
    txn = login_url.split("txn=")[1]

    expired = asyncio.run(
        routes.handlers[("/login", "GET")](
            Request({"type": "http", "method": "GET", "path": "/login", "query_string": b"txn=gone", "headers": []})
        )
    )
    assert expired.status_code == 400

    form = asyncio.run(
        routes.handlers[("/login", "GET")](
            Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/login",
                    "query_string": f"txn={txn}".encode(),
                    "headers": [],
                }
            )
        )
    )
    assert isinstance(form, HTMLResponse)
    assert txn in form.body.decode()
    assert "Entrar na Zera" in form.body.decode()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/login",
        "query_string": b"",
        "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
    }

    async def receive_ok():
        return {
            "type": "http.request",
            "body": f"txn={txn}&email=a%40zera.dev&password=secret".encode(),
            "more_body": False,
        }

    redirect = asyncio.run(routes.handlers[("/login", "POST")](Request(scope, receive_ok)))
    assert isinstance(redirect, RedirectResponse)
    assert redirect.status_code == 302


def test_login_submit_bad_credentials_and_expired_txn():
    provider, client = _provider(None)
    routes = _Routes()
    mount_login(routes, provider)
    login_url = asyncio.run(provider.authorize(client, _params()))
    txn = login_url.split("txn=")[1]

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/login",
        "query_string": b"",
        "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
    }

    async def receive_bad():
        return {
            "type": "http.request",
            "body": f"txn={txn}&email=a%40zera.dev&password=nope".encode(),
            "more_body": False,
        }

    page = asyncio.run(routes.handlers[("/login", "POST")](Request(scope, receive_bad)))
    assert isinstance(page, HTMLResponse)
    assert "Credenciais inválidas" in page.body.decode()

    async def receive_gone():
        return {
            "type": "http.request",
            "body": b"txn=gone&email=a%40zera.dev&password=secret",
            "more_body": False,
        }

    expired = asyncio.run(routes.handlers[("/login", "POST")](Request(scope, receive_gone)))
    assert expired.status_code == 400
