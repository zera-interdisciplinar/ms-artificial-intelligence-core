import base64
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from multi_agent.entity import AgentResponse, ConversationPage, ConversationPreview, Message, Role
from multi_agent.exception import UnitMismatchException

from _internal.api.multi_agent_handlers import multi_agent_handlers, report_handlers

USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _bearer(user_id: UUID) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": str(user_id)}).encode()).decode().rstrip("=")
    return f"Bearer header.{payload}.signature"


_AUTH_HEADER = {"Authorization": _bearer(USER_ID)}


def _client(service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(multi_agent_handlers(service))
    app.include_router(report_handlers(service))
    return TestClient(app)


def _body() -> dict:
    return {
        "thread_id": str(uuid4()),
        "unit_id": str(uuid4()),
        "content": "quais itens têm bateria de lítio?",
    }


class TestCallerIdentity:
    """The user always comes from the Bearer Kong validated, never from body or query."""

    def test_ignores_a_user_id_sent_in_the_body(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))

        response = _client(service).post(
            "/multi-agent/process-message", json={**_body(), "user_id": str(uuid4())}, headers=_AUTH_HEADER
        )

        assert response.status_code == 200
        assert service.process_message.await_args.args[1] == USER_ID

    def test_ignores_a_user_id_sent_in_the_query(self):
        service = MagicMock()
        service.list_conversations.return_value = ConversationPage(items=[], page=1, page_size=20, total=0)

        response = _client(service).get(
            "/multi-agent/conversations", params={"user_id": str(uuid4())}, headers=_AUTH_HEADER
        )

        assert response.status_code == 200
        service.list_conversations.assert_called_once_with(USER_ID, 1, 20)

    @pytest.mark.parametrize("authorization", ["Basic abc", "Bearer not-a-jwt"])
    def test_answers_401_when_the_bearer_has_no_user(self, authorization):
        service = MagicMock()

        response = _client(service).get("/multi-agent/conversations", headers={"Authorization": authorization})

        assert response.status_code == 401
        service.list_conversations.assert_not_called()

    def test_answers_422_when_the_authorization_header_is_missing(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))

        response = _client(service).post("/multi-agent/process-message", json=_body())

        assert response.status_code == 422
        service.process_message.assert_not_awaited()


class TestProcessMessageEndpoint:
    def test_forwards_the_unit_id_to_the_service(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))
        body = _body()

        response = _client(service).post("/multi-agent/process-message", json=body, headers=_AUTH_HEADER)

        assert response.status_code == 200
        service.process_message.assert_awaited_once()
        assert str(service.process_message.await_args.args[3]) == body["unit_id"]
        assert service.process_message.await_args.args[4] == _AUTH_HEADER["Authorization"]

    def test_answers_403_when_the_unit_is_not_the_users(self):
        service = MagicMock()
        service.process_message = AsyncMock(side_effect=UnitMismatchException("nope"))

        response = _client(service).post("/multi-agent/process-message", json=_body(), headers=_AUTH_HEADER)

        assert response.status_code == 403

    def test_answers_422_when_the_unit_id_is_missing(self):
        service = MagicMock()
        service.process_message = AsyncMock(return_value=AgentResponse(content="ok"))
        body = _body()
        del body["unit_id"]

        response = _client(service).post("/multi-agent/process-message", json=body, headers=_AUTH_HEADER)

        assert response.status_code == 422
        service.process_message.assert_not_awaited()


class TestConversationEndpoints:
    def test_lists_conversations_newest_first(self):
        service = MagicMock()
        thread_id = uuid4()
        last_at = datetime(2026, 7, 16, 13, 0, tzinfo=timezone.utc)
        service.list_conversations.return_value = ConversationPage(
            items=[ConversationPreview(thread_id=thread_id, last_message_at=last_at, preview="olá")],
            page=1,
            page_size=20,
            total=1,
        )

        response = _client(service).get("/multi-agent/conversations", headers=_AUTH_HEADER)

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

    def test_returns_every_message_in_the_thread(self):
        service = MagicMock()
        thread_id = uuid4()
        created_at = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        service.get_conversation.return_value = [
            Message(user_id=USER_ID, thread_id=thread_id, role=Role.USER, content="oi", created_at=created_at),
            Message(user_id=USER_ID, thread_id=thread_id, role=Role.ASSISTANT, content="olá", created_at=created_at),
        ]

        response = _client(service).get(f"/multi-agent/conversations/{thread_id}", headers=_AUTH_HEADER)

        assert response.status_code == 200
        assert [item["role"] for item in response.json()] == ["user", "assistant"]
        service.get_conversation.assert_called_once_with(USER_ID, thread_id)

    def test_forwards_the_requested_page(self):
        service = MagicMock()
        service.list_conversations.return_value = ConversationPage(items=[], page=2, page_size=5, total=0)

        response = _client(service).get(
            "/multi-agent/conversations", params={"page": 2, "page_size": 5}, headers=_AUTH_HEADER
        )

        assert response.status_code == 200
        service.list_conversations.assert_called_once_with(USER_ID, 2, 5)


class TestDisposalReportEndpoints:
    def test_creates_the_report_and_returns_its_url(self):
        service = MagicMock()
        service.create_disposal_report = AsyncMock(return_value="https://storage/disposal-42.pdf")

        response = _client(service).post("/reports", json={"disposal_id": "42"}, headers=_AUTH_HEADER)

        assert response.status_code == 200
        assert response.json() == {"report_url": "https://storage/disposal-42.pdf"}
        service.create_disposal_report.assert_awaited_once_with(USER_ID, "42", _AUTH_HEADER["Authorization"])

    def test_answers_403_when_the_disposal_is_not_the_users_unit(self):
        service = MagicMock()
        service.create_disposal_report = AsyncMock(side_effect=UnitMismatchException("other unit"))

        response = _client(service).post("/reports", json={"disposal_id": "42"}, headers=_AUTH_HEADER)

        assert response.status_code == 403

    def test_returns_the_stored_url(self):
        service = MagicMock()
        service.get_disposal_report = AsyncMock(return_value="https://storage/disposal-42.pdf")

        response = _client(service).get("/reports/42", headers=_AUTH_HEADER)

        assert response.status_code == 200
        assert response.json()["report_url"] == "https://storage/disposal-42.pdf"
        service.get_disposal_report.assert_awaited_once_with(USER_ID, "42", _AUTH_HEADER["Authorization"])

    def test_answers_404_when_the_disposal_has_no_report_for_this_unit(self):
        service = MagicMock()
        service.get_disposal_report = AsyncMock(return_value=None)

        response = _client(service).get("/reports/42", headers=_AUTH_HEADER)

        assert response.status_code == 404

    def test_answers_403_when_the_user_unit_cannot_be_resolved(self):
        service = MagicMock()
        service.get_disposal_report = AsyncMock(side_effect=UnitMismatchException("no unit"))

        response = _client(service).get("/reports/42", headers=_AUTH_HEADER)

        assert response.status_code == 403
