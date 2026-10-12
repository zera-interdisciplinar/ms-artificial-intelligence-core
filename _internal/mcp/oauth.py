"""
OAuth authorization server for the MCP connector.

Claude does not have the worker's JWT. It discovers this server from the 401,
opens /login, and stores the access token the admin-core already issues.
The refresh token from admin-core stays here. ask_zera still reads the Bearer.
"""

import html
import secrets
from pathlib import Path
import time
from typing import TypeVar
from urllib.parse import urlencode
from uuid import uuid4

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl, BaseModel
from redis.asyncio import Redis
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from _internal.admin_core.client import AdminCoreClient
from _internal.mcp.auth import user_id_from_authorization
from logger.logger import Logger

_CODE_TTL_SECONDS = 60
_PENDING_TTL_SECONDS = 10 * 60
_REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60
_KEY_PREFIX = "mcp:oauth"
_M = TypeVar("_M", bound=BaseModel)


class ZeraAuthorizationCode(AuthorizationCode):
    admin_access_token: str
    admin_refresh_token: str
    expires_in: int


class ZeraRefreshToken(RefreshToken):
    admin_refresh_token: str


class _PendingLogin(BaseModel):
    client_id: str
    params: AuthorizationParams


class ZeraOAuthProvider(
    OAuthAuthorizationServerProvider[ZeraAuthorizationCode, ZeraRefreshToken, AccessToken]
):
    """
    Clients, logins in progress, codes and tokens live in Redis (shared by every
    replica, survives deploys) with a TTL per kind, so nothing grows unbounded.
    """

    def __init__(self, admin_core: AdminCoreClient, issuer_url: str, logger: Logger, store: Redis) -> None:
        self.admin_core = admin_core
        self.issuer_url = issuer_url.rstrip("/")
        self.logger = logger
        self.store = store

    async def _put(self, kind: str, key: str, value: BaseModel, ttl: int | None = None) -> None:
        await self.store.set(f"{_KEY_PREFIX}:{kind}:{key}", value.model_dump_json(), ex=ttl)

    async def _get(self, kind: str, key: str, model: type[_M]) -> _M | None:
        raw = await self.store.get(f"{_KEY_PREFIX}:{kind}:{key}")
        return model.model_validate_json(raw) if raw else None

    async def _drop(self, kind: str, key: str) -> None:
        await self.store.delete(f"{_KEY_PREFIX}:{kind}:{key}")

    async def has_pending(self, txn: str) -> bool:
        return await self._get("pending", txn, _PendingLogin) is not None

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return await self._get("client", client_id, OAuthClientInformationFull)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = str(uuid4())
        await self._put("client", client_info.client_id, client_info)
        self.logger.Info(f"Registered MCP OAuth client {client_info.client_id}")

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        txn = secrets.token_urlsafe(32)
        await self._put("pending", txn, _PendingLogin(client_id=client.client_id or "", params=params), _PENDING_TTL_SECONDS)
        return f"{self.issuer_url}/login?{urlencode({'txn': txn})}"

    async def submit_login(self, txn: str, email: str, password: str) -> str | None:
        """Returns the redirect back to Claude, or None when the txn or the credentials fail."""

        pending = await self._get("pending", txn, _PendingLogin)
        if pending is None:
            return None
        params = pending.params

        tokens = await self.admin_core.login(email, password)
        if tokens is None:
            self.logger.Warning("MCP login rejected by ms-administrative-core")
            return None

        await self._drop("pending", txn)
        code = secrets.token_urlsafe(32)
        access_token = tokens["accessToken"]
        await self._put("code", code, ZeraAuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + _CODE_TTL_SECONDS,
            client_id=pending.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject=str(user_id_from_authorization(f"Bearer {access_token}")),
            admin_access_token=access_token,
            admin_refresh_token=tokens["refreshToken"],
            expires_in=int(tokens["expiresIn"]),
        ), _CODE_TTL_SECONDS)
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> ZeraAuthorizationCode | None:
        stored = await self._get("code", authorization_code, ZeraAuthorizationCode)
        if stored is None or stored.client_id != client.client_id:
            return None
        return stored

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: ZeraAuthorizationCode
    ) -> OAuthToken:
        await self._drop("code", authorization_code.code)
        return await self._issue(
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            subject=authorization_code.subject,
            access_token=authorization_code.admin_access_token,
            admin_refresh=authorization_code.admin_refresh_token,
            expires_in=authorization_code.expires_in,
            resource=authorization_code.resource,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> ZeraRefreshToken | None:
        return await self._get("refresh", refresh_token, ZeraRefreshToken)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: ZeraRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        tokens = await self.admin_core.refresh(refresh_token.admin_refresh_token)
        if tokens is None:
            raise TokenError("invalid_grant", "refresh rejected")
        await self._drop("refresh", refresh_token.token)
        return await self._issue(
            client_id=client.client_id or "",
            scopes=scopes,
            subject=refresh_token.subject,
            access_token=tokens["accessToken"],
            admin_refresh=tokens.get("refreshToken") or refresh_token.admin_refresh_token,
            expires_in=int(tokens["expiresIn"]),
            resource=None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await self._get("access", token, AccessToken)

    async def revoke_token(self, token: AccessToken | ZeraRefreshToken) -> None:
        await self._drop("access" if isinstance(token, AccessToken) else "refresh", token.token)

    async def _issue(
        self,
        client_id: str,
        scopes: list[str],
        subject: str | None,
        access_token: str,
        admin_refresh: str,
        expires_in: int,
        resource: str | None,
    ) -> OAuthToken:
        handle = secrets.token_urlsafe(32)
        await self._put("access", access_token, AccessToken(
            token=access_token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + expires_in,
            resource=resource,
            subject=subject,
        ), expires_in)
        await self._put("refresh", handle, ZeraRefreshToken(
            token=handle,
            client_id=client_id,
            scopes=scopes,
            subject=subject,
            admin_refresh_token=admin_refresh,
        ), _REFRESH_TTL_SECONDS)
        return OAuthToken(
            access_token=access_token,
            expires_in=expires_in,
            scope=" ".join(scopes) or None,
            refresh_token=handle,
        )


_LOGIN_HTML = Path(__file__).with_name("login.html").read_text(encoding="utf-8")


def _login_page(txn: str, error: str | None) -> HTMLResponse:
    message = f'<p class="error">{html.escape(error)}</p>' if error else ""
    body = _LOGIN_HTML.replace("__TXN__", html.escape(txn)).replace("__ERROR__", message)
    return HTMLResponse(body)


def mount_login(mcp, provider: ZeraOAuthProvider) -> None:
    """Public routes. FastMCP does not require a Bearer on custom_route."""

    @mcp.custom_route("/login", methods=["GET"])
    async def login_form(request: Request) -> Response:
        txn = request.query_params.get("txn", "")
        if not await provider.has_pending(txn):
            # if the txn is not in the pending list, the login has expired
            return HTMLResponse("Login expirado.", status_code=400)
        return _login_page(txn, None)

    @mcp.custom_route("/login", methods=["POST"])
    async def login_submit(request: Request) -> Response:
        form = await request.form()
        txn = str(form.get("txn") or "")
        email = str(form.get("email") or "")
        password = str(form.get("password") or "")
        redirect = await provider.submit_login(txn, email, password)
        if redirect is None:
            if not await provider.has_pending(txn):
                return HTMLResponse("Login expirado.", status_code=400)
            return _login_page(txn, "Credenciais inválidas.")
        return RedirectResponse(redirect, status_code=302)
