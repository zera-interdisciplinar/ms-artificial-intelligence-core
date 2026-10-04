from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from _internal.api.router import RouterAPI
from config.environments import Environments
from logger.logger import Logger


def test_mcp_path_is_not_404():
    envs = Environments()
    router = RouterAPI(envs, Logger())
    service = MagicMock()
    service.admin_core = MagicMock()
    router.BuildAPI(service)
    with TestClient(router._app) as client:
        response = client.post(
                "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code != 404
