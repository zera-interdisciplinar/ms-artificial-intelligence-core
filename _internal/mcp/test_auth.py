import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from _internal.mcp.auth import resolve_caller, user_id_from_authorization

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
UNIT_ID = UUID("33333333-3333-3333-3333-333333333333")


def _bearer(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"Bearer header.{body}.sig"


def test_reads_the_user_id_from_the_bearer():
    authorization = _bearer({"sub": str(USER_ID)})
    assert user_id_from_authorization(authorization) == USER_ID


def test_rejects_a_token_without_bearer_prefix():
    with pytest.raises(ValueError, match="missing bearer token"):
        user_id_from_authorization("token")


def test_rejects_a_token_without_payload():
    with pytest.raises(ValueError, match="invalid bearer token"):
        user_id_from_authorization("Bearer onlyonepart")


def test_rejects_a_token_with_broken_payload():
    with pytest.raises(ValueError, match="invalid bearer token"):
        user_id_from_authorization("Bearer header.%%% .sig")


def test_rejects_a_token_without_user_id():
    with pytest.raises(ValueError, match="bearer token has no user id"):
        user_id_from_authorization(_bearer({"email": "a@zera.dev"}))


def test_resolve_caller_returns_user_and_unit():
    admin = MagicMock()
    admin.get_unit_id = AsyncMock(return_value=UNIT_ID)
    user_id, unit_id = asyncio.run(resolve_caller(admin, _bearer({"sub": str(USER_ID)})))
    assert user_id == USER_ID
    assert unit_id == UNIT_ID


def test_resolve_caller_rejects_unknown_unit():
    admin = MagicMock()
    admin.get_unit_id = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="could not resolve unit"):
        asyncio.run(resolve_caller(admin, _bearer({"sub": str(USER_ID)})))
