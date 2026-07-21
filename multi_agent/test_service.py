from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from langgraph.checkpoint.memory import InMemorySaver

from .exception import MultiAgentServiceNotSetupException
from multi_agent.entity import AgentName, AgentResponse
from multi_agent.service import MultiAgentService

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def envs() -> Any:
    envs = MagicMock()
    envs.GEMINI_API_KEY = "fake-key"
    return envs


@pytest.fixture
def service(envs: Any) -> MultiAgentService:
    return MultiAgentService(
        repository=cast(Any, MagicMock()), envs=envs, logger=cast(Any, MagicMock())
    )


class TestProcessMessage:
    def test_raises_when_the_service_has_not_been_setup(self, service):
        with pytest.raises(MultiAgentServiceNotSetupException):
            service.process_message("olá", USER_ID, THREAD_ID)

    def test_returns_agent_response_built_from_the_graph_end_state(self, service):
        compiled_graph = MagicMock()
        compiled_graph.invoke.return_value = {
            "final_response": "três perfis",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
        }
        service._MultiAgentService__compiled_graph = compiled_graph

        response = service.process_message("quais perfis existem?", USER_ID, THREAD_ID)

        assert response == AgentResponse(
            content="três perfis",
            blocked=False,
            blocked_reason=None,
            agent_trace=[AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
        )

    def test_invokes_the_graph_with_user_and_thread_ids_configured(self, service):
        compiled_graph = MagicMock()
        compiled_graph.invoke.return_value = {
            "final_response": "resposta",
            "blocked": True,
            "blocked_reason": "conteúdo sensível",
            "called_agents": [],
        }
        service._MultiAgentService__compiled_graph = compiled_graph

        service.process_message("olá", USER_ID, THREAD_ID)

        _, kwargs = compiled_graph.invoke.call_args
        assert kwargs["config"]["configurable"] == {
            "user_id": USER_ID,
            "thread_id": THREAD_ID,
        }


class TestSetup:
    @patch("multi_agent.service.FAQ")
    @patch("multi_agent.service.StateGraph")
    @patch("multi_agent.service.MemorySaver")
    @patch("multi_agent.service.create_agent")
    @patch("multi_agent.service.ChatGoogleGenerativeAI")
    def test_builds_the_guardrail_and_compiles_the_graph(
        self, mock_llm, mock_create_agent, mock_memory_saver, mock_state_graph, mock_faq, service
    ):
        mock_create_agent.side_effect = lambda **kwargs: MagicMock()
        mock_memory_saver.return_value = InMemorySaver()
        mock_graph = mock_state_graph.return_value
        mock_graph.compile.return_value = MagicMock()

        service.setup()

        assert mock_llm.called
        assert mock_create_agent.call_count == 8
        assert service.guardrail is not None
        assert service.graph is mock_graph
        assert service._MultiAgentService__compiled_graph is mock_graph.compile.return_value
        mock_graph.compile.assert_called_once()
