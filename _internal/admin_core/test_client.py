import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest

from .client import AdminCoreClient

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
UNIT_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def envs() -> Any:
    envs = MagicMock()
    envs.ADMIN_CORE_URL = "https://gateway.zera.internal/administrative"
    envs.ADMIN_CORE_API_KEY = "fake-key"
    return envs


@pytest.fixture
def client(envs: Any) -> AdminCoreClient:
    return AdminCoreClient(envs, MagicMock())


def _http_client(response: Any) -> MagicMock:
    async_client = MagicMock()
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=False)
    async_client.get = AsyncMock(return_value=response)
    return async_client


def _response(status_code: int, json_body: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    return response


class TestGetUnitId:
    def test_returns_the_unit_the_admin_core_reports(self, client):
        http = _http_client(_response(200, {"userId": str(USER_ID), "unitId": str(UNIT_ID)}))

        with patch("httpx.AsyncClient", return_value=http):
            assert asyncio.run(client.get_unit_id(USER_ID, "Bearer test-token")) == UNIT_ID

        http.get.assert_awaited_once_with(
            f"https://gateway.zera.internal/administrative/api/v1/users/{USER_ID}",
            headers={"apikey": "fake-key", "Authorization": "Bearer test-token"},
        )

    def test_caches_the_answer_instead_of_calling_on_every_turn(self, client):
        http = _http_client(_response(200, {"unitId": str(UNIT_ID)}))

        with patch("httpx.AsyncClient", return_value=http):
            asyncio.run(client.get_unit_id(USER_ID, "Bearer test-token"))
            asyncio.run(client.get_unit_id(USER_ID, "Bearer test-token"))

        assert http.get.await_count == 1

    def test_returns_none_when_the_user_is_unknown(self, client):
        http = _http_client(_response(404))

        with patch("httpx.AsyncClient", return_value=http):
            assert asyncio.run(client.get_unit_id(USER_ID, "Bearer test-token")) is None

    def test_returns_none_when_the_user_has_no_unit(self, client):
        http = _http_client(_response(200, {"userId": str(USER_ID), "unitId": None}))

        with patch("httpx.AsyncClient", return_value=http):
            assert asyncio.run(client.get_unit_id(USER_ID, "Bearer test-token")) is None

    def test_returns_none_when_the_admin_core_is_unreachable(self, client):
        http = _http_client(_response(200))
        http.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with patch("httpx.AsyncClient", return_value=http):
            assert asyncio.run(client.get_unit_id(USER_ID, "Bearer test-token")) is None
