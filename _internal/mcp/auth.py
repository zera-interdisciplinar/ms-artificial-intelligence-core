"""
Who is calling the MCP server.
The host already did the login and kept the Bearer. Here we only read that token
and ask ms-administrative-core which unit the user belongs to.
"""

import base64
import json
from uuid import UUID

from _internal.admin_core.client import AdminCoreClient


def user_id_from_authorization(authorization: str) -> UUID:
    """
    Read the user id from the Bearer the host stored.
    The signature is not checked here. ms-administrative-core checks the token
    when we resolve the unit. The model never receives this value back.
    """

    if not authorization.lower().startswith("bearer "):
        raise ValueError("missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("invalid bearer token")

    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError("invalid bearer token") from e

    raw_user_id = payload.get("sub") or payload.get("userId") or payload.get("user_id")
    if not raw_user_id:
        raise ValueError("bearer token has no user id")

    return UUID(str(raw_user_id))


async def resolve_caller(admin_core: AdminCoreClient, authorization: str) -> tuple[UUID, UUID]:
    """
    Login result, already done by the host: token in, user and unit out.
    The unit comes from ms-administrative-core, not from a tool argument.
    """

    user_id = user_id_from_authorization(authorization)
    unit_id = await admin_core.get_unit_id(user_id, authorization)
    if unit_id is None:
        raise ValueError("could not resolve unit")

    return user_id, unit_id
