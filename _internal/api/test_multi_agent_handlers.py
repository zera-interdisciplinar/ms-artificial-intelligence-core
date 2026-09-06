from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from multi_agent.entity import AgentResponse
from multi_agent.exception import UnitMismatchException

from _internal.api.multi_agent_handlers import multi_agent_handlers


def _client(service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(multi_agent_handlers(service))
    return TestClient(app)


def _body() -> dict:
    return {
        "user_id": str(uuid4()),
        "thread_id": str(uuid4()),
        "unit_id": str(uuid4()),
        "content": "quais itens têm bateria de lítio?",
    }


_AUTH_HEADER = {"Authorization": "Bearer test-token"}


class TestProcessMessageEndpoint:
    def test_forwards_the_unit_id_to_the_service(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))
        body = _body()

        response = _client(service).post(
            "/multi-agent/process-message", json=body, headers=_AUTH_HEADER
        )

        assert response.status_code == 200
        service.process_message.assert_awaited_once()
        assert str(service.process_message.await_args.args[3]) == body["unit_id"]
        assert service.process_message.await_args.args[4] == _AUTH_HEADER["Authorization"]

    def test_answers_403_when_the_unit_is_not_the_users(self):
        service = MagicMock()
        service.process_message = AsyncMock(side_effect=UnitMismatchException("nope"))

        response = _client(service).post(
            "/multi-agent/process-message", json=_body(), headers=_AUTH_HEADER
        )

        assert response.status_code == 403

    def test_answers_422_when_the_unit_id_is_missing(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))
        body = _body()
        del body["unit_id"]

        response = _client(service).post(
            "/multi-agent/process-message", json=body, headers=_AUTH_HEADER
        )

        assert response.status_code == 422
        service.process_message.assert_not_awaited()

    def test_answers_422_when_the_authorization_header_is_missing(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))

        response = _client(service).post("/multi-agent/process-message", json=_body())

        assert response.status_code == 422
        service.process_message.assert_not_awaited()
