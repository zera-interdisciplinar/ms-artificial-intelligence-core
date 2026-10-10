from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from multi_agent.entity import AgentResponse, ConversationPage, ConversationPreview, Message, Role
from multi_agent.exception import UnitMismatchException

from _internal.api.multi_agent_handlers import multi_agent_handlers, report_handlers


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


class TestConversationEndpoints:
    def test_lists_conversations_newest_first(self):
        service = MagicMock()
        user_id = uuid4()
        thread_id = uuid4()
        last_at = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
        service.repository.list_conversations.return_value = ConversationPage(
            items=[ConversationPreview(thread_id=thread_id, last_message_at=last_at, preview="olá")],
            page=1,
            page_size=20,
            total=1,
        )

        response = _client(service).get("/multi-agent/conversations", params={"user_id": str(user_id)})

        assert response.status_code == 200
        assert response.json() == {
            "items": [{
                "thread_id": str(thread_id),
                "last_message_at": "2026-07-16T13:00:00Z",
                "preview": "olá",
            }],
            "page": 1,
            "page_size": 20,
            "total": 1,
        }
        service.repository.list_conversations.assert_called_once_with(user_id, 1, 20)

    def test_returns_every_message_in_the_thread(self):
        service = MagicMock()
        user_id = uuid4()
        thread_id = uuid4()
        created_at = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        service.repository.retrieve_messages.return_value = [
            Message(user_id=user_id, thread_id=thread_id, role=Role.USER, content="oi", created_at=created_at),
            Message(user_id=user_id, thread_id=thread_id, role=Role.ASSISTANT, content="olá", created_at=created_at),
        ]

        response = _client(service).get(
            f"/multi-agent/conversations/{thread_id}", params={"user_id": str(user_id)}
        )

        assert response.status_code == 200
        assert [item["role"] for item in response.json()] == ["user", "assistant"]
        service.repository.retrieve_messages.assert_called_once_with(user_id, thread_id, limit=None)

    def test_forwards_the_requested_page(self):
        service = MagicMock()
        user_id = uuid4()
        service.repository.list_conversations.return_value = ConversationPage(
            items=[], page=2, page_size=5, total=0
        )

        response = _client(service).get(
            "/multi-agent/conversations",
            params={"user_id": str(user_id), "page": 2, "page_size": 5},
        )

        assert response.status_code == 200
        service.repository.list_conversations.assert_called_once_with(user_id, 2, 5)

    def test_answers_422_when_the_user_id_is_missing(self):
        service = MagicMock()

        response = _client(service).get("/multi-agent/conversations")

        assert response.status_code == 422
        service.repository.list_conversations.assert_not_called()


def _report_client(service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(report_handlers(service))
    return TestClient(app)


class TestDisposalReportEndpoints:
    def test_creates_the_report_and_returns_its_url(self):
        service = MagicMock()
        service.create_disposal_report = AsyncMock(return_value="https://storage/disposal-42.pdf")
        user_id = uuid4()

        response = _report_client(service).post(
            "/reports",
            json={"user_id": str(user_id), "disposal_id": "42"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.json() == {"report_url": "https://storage/disposal-42.pdf"}
        service.create_disposal_report.assert_awaited_once()
        assert service.create_disposal_report.await_args.args[1] == "42"
        assert service.create_disposal_report.await_args.args[2] == "Bearer test-token"

    def test_answers_403_when_the_user_unit_cannot_be_resolved(self):
        service = MagicMock()
        service.create_disposal_report = AsyncMock(side_effect=UnitMismatchException("no unit"))

        response = _report_client(service).post(
            "/reports",
            json={"user_id": str(uuid4()), "disposal_id": "42"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403

    def test_returns_the_stored_url(self):
        service = MagicMock()
        service.get_disposal_report.return_value = "https://storage/disposal-42.pdf"

        response = _report_client(service).get("/reports/42")

        assert response.status_code == 200
        assert response.json()["report_url"] == "https://storage/disposal-42.pdf"

    def test_answers_404_when_the_disposal_has_no_report(self):
        service = MagicMock()
        service.get_disposal_report.return_value = None

        response = _report_client(service).get("/reports/42")

        assert response.status_code == 404
