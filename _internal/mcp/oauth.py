"""
OAuth authorization server for the MCP connector.

Claude does not have the worker's JWT. It discovers this server from the 401,
opens /login, and stores the access token the admin-core already issues.
The refresh token from admin-core stays here. ask_zera still reads the Bearer.
"""

import html
import secrets
import time
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
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from _internal.admin_core.client import AdminCoreClient
from _internal.mcp.auth import user_id_from_authorization
from logger.logger import Logger

_CODE_TTL_SECONDS = 60
# ponytail: in-memory clients and tokens die on restart. Claude logs in again.
# A shared store is the upgrade when more than one pod serves the connector.


class ZeraAuthorizationCode(AuthorizationCode):
    admin_access_token: str
    admin_refresh_token: str
    expires_in: int


class ZeraRefreshToken(RefreshToken):
    admin_refresh_token: str


class ZeraOAuthProvider(
    OAuthAuthorizationServerProvider[ZeraAuthorizationCode, ZeraRefreshToken, AccessToken]
):
    def __init__(self, admin_core: AdminCoreClient, issuer_url: str, logger: Logger) -> None:
        self.admin_core = admin_core
        self.issuer_url = issuer_url.rstrip("/")
        self.logger = logger
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, tuple[str, AuthorizationParams]] = {}
        self._codes: dict[str, ZeraAuthorizationCode] = {}
        self._access: dict[str, AccessToken] = {}
        self._refresh: dict[str, ZeraRefreshToken] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = str(uuid4())
        self._clients[client_info.client_id] = client_info
        self.logger.Info(f"Registered MCP OAuth client {client_info.client_id}")

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        txn = secrets.token_urlsafe(32)
        self._pending[txn] = (client.client_id or "", params)
        return f"{self.issuer_url}/login?{urlencode({'txn': txn})}"

    async def submit_login(self, txn: str, email: str, password: str) -> str | None:
        """Returns the redirect back to Claude, or None when the txn or the credentials fail."""

        pending = self._pending.get(txn)
        if pending is None:
            return None
        client_id, params = pending

        tokens = await self.admin_core.login(email, password)
        if tokens is None:
            self.logger.Warning("MCP login rejected by ms-administrative-core")
            return None

        del self._pending[txn]
        code = secrets.token_urlsafe(32)
        access_token = tokens["accessToken"]
        self._codes[code] = ZeraAuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + _CODE_TTL_SECONDS,
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject=str(user_id_from_authorization(f"Bearer {access_token}")),
            admin_access_token=access_token,
            admin_refresh_token=tokens["refreshToken"],
            expires_in=int(tokens["expiresIn"]),
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> ZeraAuthorizationCode | None:
        stored = self._codes.get(authorization_code)
        if stored is None or stored.client_id != client.client_id:
            return None
        return stored

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: ZeraAuthorizationCode
    ) -> OAuthToken:
        self._codes.pop(authorization_code.code, None)
        return self._issue(
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
        return self._refresh.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: ZeraRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        tokens = await self.admin_core.refresh(refresh_token.admin_refresh_token)
        if tokens is None:
            raise TokenError("invalid_grant", "refresh rejected")
        self._refresh.pop(refresh_token.token, None)
        self._access.pop(refresh_token.token, None)
        return self._issue(
            client_id=client.client_id or "",
            scopes=scopes,
            subject=refresh_token.subject,
            access_token=tokens["accessToken"],
            admin_refresh=tokens.get("refreshToken") or refresh_token.admin_refresh_token,
            expires_in=int(tokens["expiresIn"]),
            resource=None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self._access.get(token)

    async def revoke_token(self, token: AccessToken | ZeraRefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access.pop(token.token, None)
        else:
            self._refresh.pop(token.token, None)

    def _issue(
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
        self._access[access_token] = AccessToken(
            token=access_token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + expires_in,
            resource=resource,
            subject=subject,
        )
        self._refresh[handle] = ZeraRefreshToken(
            token=handle,
            client_id=client_id,
            scopes=scopes,
            subject=subject,
            admin_refresh_token=admin_refresh,
        )
        return OAuthToken(
            access_token=access_token,
            expires_in=expires_in,
            scope=" ".join(scopes) or None,
            refresh_token=handle,
        )


def _login_page(txn: str, error: str | None) -> HTMLResponse:
    message = f"<p>{html.escape(error)}</p>" if error else ""
    body = f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Entrar na Zera</title></head>
<body>
<h1>Entrar na Zera</h1>
{message}
<form method="post" action="/login">
<input type="hidden" name="txn" value="{html.escape(txn)}">
<label>E-mail <input name="email" type="email" required></label>
<label>Senha <input name="password" type="password" required></label>
<button type="submit">Entrar</button>
</form>
</body>
</html>"""
    return HTMLResponse(body)


def mount_login(mcp, provider: ZeraOAuthProvider) -> None:
    """Public routes. FastMCP does not require a Bearer on custom_route."""

    @mcp.custom_route("/login", methods=["GET"])
    async def login_form(request: Request) -> Response:
        txn = request.query_params.get("txn", "")
        if txn not in provider._pending:
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
            if txn not in provider._pending:
                return HTMLResponse("Login expirado.", status_code=400)
            return _login_page(txn, "Credenciais inválidas.")
        return RedirectResponse(redirect, status_code=302)
