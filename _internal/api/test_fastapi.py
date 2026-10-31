"""
E2E tests for our application using FastAPI's TestClient. These tests are meant to be run in a CI/CD pipeline and will hit real external services (Gemini, Groq, MongoDB, Supabase, the predict_model MCP, and the ms-inventory MCP)
They are designed to verify that the entire system works together as expected, rather than testing individual components in isolation.
Edit these tests are out of context, except if the task is explicity saying to edit them or something that causes a change in out api behavior. They are not meant to be run locally, as they require access to real external services and secrets.


Tests usecases:
- /health: Check if the API is up and running.
- /multi-agent/process-message: Test the FAQ agent's ability to retrieve context from a PDF
- /multi-agent/process-message: Test the predict agent's ability to generate predictions based on input
- /multi-agent/process-message: Test the report agent's ability to generate reports based on input
- /reports: Test that a disposal report is stored and its URL can be read back
- /multi-agent/process-message: Test the inventory agent's ability to answer a factual inventory query
- /multi-agent/process-message: An off-topic message is answered by the orchestrator with blocked false, and no specialist runs
- /multi-agent/process-message: A unit_id that is not the user's is refused with 403, never answered from another unit's data
- /multi-agent/conversations: lists a user's threads, newest first, paged, with a 40-character preview
- /multi-agent/conversations/{thread_id}: returns every message exchanged in that thread
"""

import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()
from fastapi.testclient import TestClient
from httpx import Response
from multi_agent.entity import AgentResponse, Message, Role
from _internal.api.dto import DisposalReportRequest, ProcessMessageRequest

pytestmark = pytest.mark.integration

INTEGRATION_UNIT_ID = os.getenv("INTEGRATION_UNIT_ID", "")

_ADMIN_CORE_URL = os.getenv("ADMIN_CORE_URL", "").strip()
_ADMIN_CORE_API_KEY = os.getenv("ADMIN_CORE_API_KEY", "").strip()
_ADMIN_CORE_SERVICE_EMAIL = os.getenv("ADMIN_CORE_SERVICE_EMAIL", "").strip()
_ADMIN_CORE_SERVICE_PASSWORD = os.getenv("ADMIN_CORE_SERVICE_PASSWORD", "").strip()


@pytest.fixture(scope="module")
def auth_headers() -> dict:
    """Logs in against ms-administrative-core and returns the Authorization header
    to forward on every /process-message call."""

    response = httpx.post(
        f"{_ADMIN_CORE_URL}/api/v1/auth/login",
        json={"email": _ADMIN_CORE_SERVICE_EMAIL, "password": _ADMIN_CORE_SERVICE_PASSWORD},
        headers={"apikey": _ADMIN_CORE_API_KEY},
        timeout=10.0,
    )
    assert response.status_code == 200, (
        f"ms-administrative-core login answered {response.status_code}: {response.text}"
    )
    access_token = response.json()["accessToken"]
    return {"Authorization": f"Bearer {access_token}"}


def _new_UUID() -> str:
    """
    Generate a new UUID string.
    """
    return str(uuid4())

def called_faq_flow(response: AgentResponse) -> bool:
    """
    Check if the FAQ agent was called in the multi-agent flow based on the response.
    """
    return "faq" in response.agent_trace

def called_predict_flow(response: AgentResponse) -> bool:
    """
    Check if the predict agent was called in the multi-agent flow based on the response.
    """
    return "predict_model" in response.agent_trace

def called_report_flow(response: AgentResponse) -> bool:
    """
    Check if the report agent was called in the multi-agent flow based on the response.
    """
    return "report" in response.agent_trace

def called_inventory_flow(response: AgentResponse) -> bool:
    """
    Check if the inventory agent was called in the multi-agent flow based on the response.
    """
    return "inventory_agent" in response.agent_trace


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """
    Fixture that provides a TestClient instance for testing the FastAPI application.
    Opened with `with` so every request shares one event loop, like uvicorn: the async
    Redis pool keeps its connections bound to the loop that opened them.
    """
    from redis.asyncio import Redis

    from _internal.api.router import RouterAPI
    from app.api.composition import build_service
    from config.environments import Environments
    from logger.logger import Logger
    from _internal.mongo.setup import Repository
    from repository.multi_agent import MultiAgentRepository

    envs = Environments()
    
    # ovverride the MONGO_DB_NAME to ensure that the tests run against a test database and not the production database
    envs.MONGO_DB_NAME = "ms-artificial-intelligence-core-tests"
    envs.MONGO_URI="mongodb://localhost:27017"
    
    logger = Logger()
    router_api = RouterAPI(envs, logger)
    
    # clear the collection if exists
    multi_agent_repository = MultiAgentRepository()
    multi_agent_repository.setup(Repository(envs))
    multi_agent_repository.messageCollection.delete_many({})
    multi_agent_repository.preferencesCollection.delete_many({})
    
    redis = Redis.from_url(envs.REDIS_URL)
    multi_agent_service, admin_core = build_service(envs, logger, redis)
    
    router_api.BuildAPI(multi_agent_service, admin_core, redis)
    
    with TestClient(router_api._app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient) -> None:
    """
    Test the /health endpoint to ensure the API is up and running.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
def test_faq_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Test the FAQ agent's ability to retrieve context from a PDF and generate an answer.
    """
    user_message = "What is the project zera?"

    body: ProcessMessageRequest = ProcessMessageRequest(
        thread_id=_new_UUID(),
        unit_id=INTEGRATION_UNIT_ID,
        content=user_message,
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
        headers=auth_headers,
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the FAQ agent was called
    assert called_faq_flow(response)
    assert response.content is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_predict_flow(response)
    assert not called_report_flow(response)
    assert not called_inventory_flow(response)
    assert not response.blocked

def test_predict_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Test the predict agent's ability to generate predictions based on input.
    """
    user_message = (
        "Qual a estimativa de tempo até falha de um notebook Dell Latitude 5420, "
        "fabricado em 2022, adquirido em 2023-01-15, em zona climática tropical, "
        "uso intenso (nível 8)?"
    )

    body: ProcessMessageRequest = ProcessMessageRequest(
        thread_id=_new_UUID(),
        unit_id=INTEGRATION_UNIT_ID,
        content=user_message,
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
        headers=auth_headers,
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the predict agent was called
    assert called_predict_flow(response)
    assert response.content is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_faq_flow(response)
    assert not called_report_flow(response)
    assert not called_inventory_flow(response)
    assert not response.blocked

def test_report_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Test the report agent's ability to generate reports based on input.
    """
    # Facts stay in the message. The report agent must not need a stored lot or disposal.
    user_message = (
        "Gere a cotação de coleta com 12 notebooks descartáveis e 5 monitores aproveitáveis. "
        "Não há descarte cadastrado."
    )

    body: ProcessMessageRequest = ProcessMessageRequest(
        thread_id=_new_UUID(),
        unit_id=INTEGRATION_UNIT_ID,
        content=user_message,
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
        headers=auth_headers,
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the report agent was called
    assert called_report_flow(response)
    assert response.content is not None
    assert response.report_url is None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_faq_flow(response)
    assert not called_predict_flow(response)
    assert not called_inventory_flow(response)
    assert not response.blocked


def test_disposal_report_returns_a_stored_url(client: TestClient, auth_headers: dict) -> None:
    """
    A disposal report is generated outside the chat, stored, and readable by disposal id.
    """
    disposal_id = _new_UUID()
    body = DisposalReportRequest(disposal_id=disposal_id)

    created: Response = client.post(
        "/api/v1/reports", json=body.model_dump(mode="json"), headers=auth_headers
    )

    assert created.status_code == 200
    report_url = created.json()["report_url"]
    assert report_url.startswith("http")

    fetched: Response = client.get(f"/api/v1/reports/{disposal_id}", headers=auth_headers)

    assert fetched.status_code == 200
    assert fetched.json()["report_url"] == report_url

def test_inventory_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Test the inventory agent's ability to answer a factual inventory query.
    """
    user_message = "Qual o status atual do notebook de patrimônio NB-4521?"

    body: ProcessMessageRequest = ProcessMessageRequest(
        thread_id=_new_UUID(),
        unit_id=INTEGRATION_UNIT_ID,
        content=user_message,
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
        headers=auth_headers,
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the inventory agent was called
    assert called_inventory_flow(response)
    assert response.content is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_faq_flow(response)
    assert not called_predict_flow(response)
    assert not called_report_flow(response)
    assert not response.blocked

def test_off_topic_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Tests the ability of a off-topic user message to be handled.
    """
    user_message = "Qual a receita de um bolo de chocolate?"

    body: ProcessMessageRequest = ProcessMessageRequest(
        thread_id=_new_UUID(),
        unit_id=INTEGRATION_UNIT_ID,
        content=user_message,
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
        headers=auth_headers,
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # off-topic is not a guardrail block: the orchestrator answers and the suggestion
    # still goes through guardrail_out. No specialist runs.
    assert not response.blocked
    assert response.blocked_reason is None
    assert response.content
    assert "orchestrator" in response.agent_trace
    assert "guardrail_out" in response.agent_trace

    assert not called_faq_flow(response)
    assert not called_predict_flow(response)
    assert not called_report_flow(response)




def test_rejects_a_unit_that_does_not_belong_to_the_user(client: TestClient, auth_headers: dict) -> None:
    """
    The unit_id in the body is only a proposal: ms-administrative-core decides. A
    request naming someone else's unit must be refused, never answered with that
    unit's inventory.
    """
    body: ProcessMessageRequest = ProcessMessageRequest(
        thread_id=_new_UUID(),
        unit_id=_new_UUID(),
        content="Quantos itens existem no inventário?",
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
        headers=auth_headers,
    )

    assert http_response.status_code == 403


def test_lists_conversations_and_reads_every_message(client: TestClient, auth_headers: dict) -> None:
    """
    Threads saved in Mongo come back newest-first, one page at a time, with a
    40-character cut of the first message. The thread endpoint returns both sides.
    The user is the one in the Bearer.
    """
    from config.environments import Environments
    from _internal.mcp.auth import user_id_from_authorization
    from _internal.mongo.setup import Repository
    from repository.multi_agent import MultiAgentRepository

    envs = Environments()
    envs.MONGO_DB_NAME = "ms-artificial-intelligence-core-tests"
    envs.MONGO_URI = "mongodb://localhost:27017"
    repository = MultiAgentRepository()
    repository.setup(Repository(envs))

    user_id = user_id_from_authorization(auth_headers["Authorization"])
    older_thread = uuid4()
    newer_thread = uuid4()
    opening = "primeira mensagem desta conversa antiga que passa de quarenta caracteres"
    repository.save_message(Message(
        user_id=user_id, thread_id=older_thread, role=Role.USER, content=opening,
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
    ))
    repository.save_message(Message(
        user_id=user_id, thread_id=older_thread, role=Role.ASSISTANT, content="resposta do assistente",
        created_at=datetime(2026, 7, 1, 10, 1, tzinfo=timezone.utc),
    ))
    repository.save_message(Message(
        user_id=user_id, thread_id=newer_thread, role=Role.USER, content="conversa mais recente",
        created_at=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
    ))

    first_page = client.get(
        "/api/v1/multi-agent/conversations",
        params={"page": 1, "page_size": 1},
        headers=auth_headers,
    )
    assert first_page.status_code == 200
    body = first_page.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["items"][0]["thread_id"] == str(newer_thread)
    assert body["items"][0]["preview"] == "conversa mais recente"

    second_page = client.get(
        "/api/v1/multi-agent/conversations",
        params={"page": 2, "page_size": 1},
        headers=auth_headers,
    )
    assert second_page.status_code == 200
    older = second_page.json()["items"][0]
    assert older["thread_id"] == str(older_thread)
    assert older["preview"] == opening[:40]
    assert len(older["preview"]) == 40

    history = client.get(
        f"/api/v1/multi-agent/conversations/{older_thread}",
        headers=auth_headers,
    )
    assert history.status_code == 200
    assert [(item["role"], item["content"]) for item in history.json()] == [
        ("user", opening),
        ("assistant", "resposta do assistente"),
    ]
