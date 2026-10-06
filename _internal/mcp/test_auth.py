import base64
import json
from uuid import UUID

import pytest

from _internal.mcp.auth import user_id_from_authorization

USER_ID = UUID("11111111-1111-1111-1111-111111111111")


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
