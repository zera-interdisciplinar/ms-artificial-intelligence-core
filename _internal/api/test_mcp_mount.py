import base64
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from _internal.api.router import RouterAPI
from config.environments import Environments
from logger.logger import Logger
from multi_agent.exception import AgentOutputException
from repository.exception import RepositoryReadException


def _bearer() -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": str(uuid4())}).encode()).decode().rstrip("=")
    return f"Bearer header.{payload}.signature"


def _router(monkeypatch, self_mcp_url: str | None, service=None) -> RouterAPI:
    if self_mcp_url is None:
        monkeypatch.delenv("SELF_MCP_URL", raising=False)
    else:
        monkeypatch.setenv("SELF_MCP_URL", self_mcp_url)
    router = RouterAPI(Environments(), Logger())
    router.BuildAPI(service or MagicMock(), MagicMock(), MagicMock())
    return router


@pytest.mark.parametrize("error,status", [
    (AgentOutputException("not json"), 502),
    (RepositoryReadException("mongo down"), 503),
])
def test_core_failures_become_explicit_http_errors(monkeypatch, error, status):
    service = MagicMock()
    service.list_conversations.side_effect = error
    router = _router(monkeypatch, None, service)
    with TestClient(router._app) as client:
        response = client.get("/api/v1/multi-agent/conversations", headers={"Authorization": _bearer()})
    assert response.status_code == status


def test_health_still_answers_when_mcp_is_mounted(monkeypatch):
    router = _router(monkeypatch, "http://127.0.0.1:8000")
    with TestClient(router._app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_path_is_not_404(monkeypatch):
    router = _router(monkeypatch, "http://127.0.0.1:8000")
    with TestClient(router._app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code != 404


def test_claude_resource_metadata_is_at_the_rfc9728_path(monkeypatch):
    router = _router(monkeypatch, "https://www.zeratech.online/qa/ai-core")
    with TestClient(router._app) as client:
        response = client.get(
            "/.well-known/oauth-protected-resource/qa/ai-core/mcp"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == "https://www.zeratech.online/qa/ai-core/mcp"


def test_claude_authorization_server_metadata_keeps_the_gateway_prefix(monkeypatch):
    router = _router(monkeypatch, "https://www.zeratech.online/qa/ai-core")
    with TestClient(router._app) as client:
        response = client.get(
            "/.well-known/oauth-authorization-server/qa/ai-core"
        )
    assert response.status_code == 200
    assert response.json()["issuer"] == "https://www.zeratech.online/qa/ai-core"
