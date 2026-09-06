"""
E2E tests for our application using FastAPI's TestClient. These tests are meant to be run in a CI/CD pipeline and will hit real external services (Gemini, Groq, MongoDB, Supabase, the predict_model MCP, and the ms-inventory MCP)
They are designed to verify that the entire system works together as expected, rather than testing individual components in isolation.
Edit these tests are out of context, except if the task is explicity saying to edit them or something that causes a change in out api behavior. They are not meant to be run locally, as they require access to real external services and secrets.


Tests usecases:
- /health: Check if the API is up and running.
- /multi-agent/process-message: Test the FAQ agent's ability to retrieve context from a PDF
- /multi-agent/process-message: Test the predict agent's ability to generate predictions based on input
- /multi-agent/process-message: Test the report agent's ability to generate reports based on input
- /multi-agent/process-message: Test the inventory agent's ability to answer a factual inventory query
- /multi-agent/process-message: Tests the ablity of a off-topic user message to be handled (blocked by guardrail_in)
- /multi-agent/process-message: A unit_id that is not the user's is refused with 403, never answered from another unit's data
"""

import os
from uuid import uuid4

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()
from fastapi.testclient import TestClient
from httpx import Response
from multi_agent.entity import AgentResponse
from _internal.api.dto import ProcessMessageRequest

pytestmark = pytest.mark.integration

INTEGRATION_USER_ID = os.getenv("INTEGRATION_USER_ID", "")
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
    from _internal.admin_core.client import AdminCoreClient

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
    multi_agent_repository.preferencesCollection.delete_many({})
    
    multi_agent_service = MultiAgentService(
        repository=multi_agent_repository,
        envs=envs,
        logger=logger,
        pdf_renderer=pdf_renderer,
        storage_service=storage_service,
        admin_core=AdminCoreClient(envs, logger),
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
    
def test_faq_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Test the FAQ agent's ability to retrieve context from a PDF and generate an answer.
    """
    user_message = "What is the project zera?"

    body: ProcessMessageRequest = ProcessMessageRequest(
        user_id=INTEGRATION_USER_ID,
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
        user_id=INTEGRATION_USER_ID,
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
    user_message = "Gere um relatório com o histórico de previsões de falha dos meus equipamentos."

    body: ProcessMessageRequest = ProcessMessageRequest(
        user_id=INTEGRATION_USER_ID,
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
    assert response.report_url is not None

    # assert that the response did not called any other agents or that the response is not blocked
    assert not called_faq_flow(response)
    assert not called_predict_flow(response)
    assert not called_inventory_flow(response)
    assert not response.blocked

def test_inventory_agent(client: TestClient, auth_headers: dict) -> None:
    """
    Test the inventory agent's ability to answer a factual inventory query.
    """
    user_message = "Qual o status atual do notebook de patrimônio NB-4521?"

    body: ProcessMessageRequest = ProcessMessageRequest(
        user_id=INTEGRATION_USER_ID,
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
        user_id=INTEGRATION_USER_ID,
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

    # assert that an off-topic message is blocked and does not reach any specialist agent
    assert response.blocked
    assert response.blocked_reason is not None

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
        user_id=INTEGRATION_USER_ID,
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
