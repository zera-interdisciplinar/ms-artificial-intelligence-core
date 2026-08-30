"""
E2E tests for our application using FastAPI's TestClient. These tests are meant to be run in a CI/CD pipeline and will hit real external services (Gemini, Groq, MongoDB, Supabase, and the predict_model MCP)
They are designed to verify that the entire system works together as expected, rather than testing individual components in isolation.
Edit these tests are out of context, except if the task is explicity saying to edit them or something that causes a change in out api behavior. They are not meant to be run locally, as they require access to real external services and secrets.


Tests usecases:
- /health: Check if the API is up and running.
- /multi-agent/process-message: Test the FAQ agent's ability to retrieve context from a PDF
- /multi-agent/process-message: Test the predict agent's ability to generate predictions based on input
- /multi-agent/process-message: Test the report agent's ability to generate reports based on input
- /multi-agent/process-message: Tests the ablity of a off-topic user message to be handled (blocked by guardrail_in)
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from multi_agent.entity import Message, AgentResponse

pytestmark = pytest.mark.integration

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


@pytest.fixture()
def client() -> TestClient:
    """
    Fixture that provides a TestClient instance for testing the FastAPI application.
    """
    from _internal.api.router import RouterAPI
    from config.environments import Environments
    from logger.logger import Logger
    from multi_agent.service import MultiAgentService
    from _internal.mongo.setup import Repository
    from repository.multi_agent import MultiAgentRepository
    from _internal.storage.pdf import PdfRenderer
    from _internal.storage.service import SupabaseStorageService

    envs = Environments()
    
    # ovverride the MONGO_DB_NAME to ensure that the tests run against a test database and not the production database
    envs.MONGO_DB_NAME = "ms-artificial-intelligence-core-tests"
    envs.MONGO_URI="mongodb://localhost:27017"
    
    logger = Logger()
    router_api = RouterAPI(envs, logger)
    
    general_repository = Repository(envs)
    multi_agent_repository = MultiAgentRepository()
    pdf_renderer = PdfRenderer()
    storage_service = SupabaseStorageService(envs)
    
    # clear the collection if exists
    multi_agent_repository.setup(general_repository)
    multi_agent_repository.messageCollection.delete_many({})
    multi_agent_repository.threadCollection.delete_many({})
    
    multi_agent_service = MultiAgentService(
        repository=multi_agent_repository,
        envs=envs,
        logger=logger,
        pdf_renderer=pdf_renderer,
        storage_service=storage_service
    )
    
    multi_agent_service.setup()
    
    router_api.BuildAPI(multi_agent_service)
    
    return TestClient(router_api._app)


def test_health_endpoint(client: TestClient) -> None:
    """
    Test the /health endpoint to ensure the API is up and running.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
def test_faq_agent(client: TestClient) -> None:
    """
    Test the FAQ agent's ability to retrieve context from a PDF and generate an answer.
    """
    user_message = "What is the project zera?"

    body: Message = Message(
        user_id=_new_UUID(),
        thread_id=_new_UUID(),
        role="user",
        content=user_message,
        created_at=datetime.now(timezone.utc),
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the FAQ agent was called
    assert called_faq_flow(response)
    assert response.content is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_predict_flow(response)
    assert not called_report_flow(response)
    assert not response.blocked

def test_predict_agent(client: TestClient) -> None:
    """
    Test the predict agent's ability to generate predictions based on input.
    """
    user_message = (
        "Qual a estimativa de tempo até falha de um notebook Dell Latitude 5420, "
        "fabricado em 2022, adquirido em 2023-01-15, em zona climática tropical, "
        "uso intenso (nível 8)?"
    )

    body: Message = Message(
        user_id=_new_UUID(),
        thread_id=_new_UUID(),
        role="user",
        content=user_message,
        created_at=datetime.now(timezone.utc),
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the predict agent was called
    assert called_predict_flow(response)
    assert response.content is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_faq_flow(response)
    assert not called_report_flow(response)
    assert not response.blocked

def test_report_agent(client: TestClient) -> None:
    """
    Test the report agent's ability to generate reports based on input.
    """
    user_message = "Gere um relatório com o histórico de previsões de falha dos meus equipamentos."

    body: Message = Message(
        user_id=_new_UUID(),
        thread_id=_new_UUID(),
        role="user",
        content=user_message,
        created_at=datetime.now(timezone.utc),
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that the response has successfully processed the message and that the report agent was called
    assert called_report_flow(response)
    assert response.content is not None
    assert response.report_url is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_faq_flow(response)
    assert not called_predict_flow(response)
    assert not response.blocked

def test_off_topic_agent(client: TestClient) -> None:
    """
    Tests the ability of a off-topic user message to be handled.
    """
    user_message = "Qual a receita de um bolo de chocolate?"

    body: Message = Message(
        user_id=_new_UUID(),
        thread_id=_new_UUID(),
        role="user",
        content=user_message,
        created_at=datetime.now(timezone.utc),
    )

    http_response: Response = client.post(
        "/api/v1/multi-agent/process-message",
        json=body.model_dump(mode="json"),
    )

    assert http_response.status_code == 200
    response: AgentResponse = AgentResponse(**http_response.json())

    # assert that an off-topic message is blocked and does not reach any specialist agent
    assert response.blocked
    assert response.blocked_reason is not None

    assert not called_faq_flow(response)
    assert not called_predict_flow(response)
    assert not called_report_flow(response)


