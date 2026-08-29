import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from langgraph.checkpoint.memory import InMemorySaver

from .exception import MultiAgentServiceNotSetupException
from multi_agent.entity import AgentName, AgentResponse
from multi_agent.service import MultiAgentService
from _internal.storage.exceptions import PDFRenderException, StorageUploadException

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
        repository=cast(Any, MagicMock()),
        envs=envs,
        logger=cast(Any, MagicMock()),
        pdf_renderer=cast(Any, MagicMock()),
        storage_service=cast(Any, MagicMock()),
    )


class TestProcessMessage:
    def test_raises_when_the_service_has_not_been_setup(self, service):
        with pytest.raises(MultiAgentServiceNotSetupException):
            asyncio.run(service.process_message("olá", USER_ID, THREAD_ID))

    def test_returns_agent_response_built_from_the_graph_end_state(self, service):
        compiled_graph = MagicMock()
        compiled_graph.ainvoke = AsyncMock(return_value={
            "final_response": "três perfis",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
            "report_html": None,
        })
        service._MultiAgentService__compiled_graph = compiled_graph

        response = asyncio.run(service.process_message("quais perfis existem?", USER_ID, THREAD_ID))

        assert response == AgentResponse(
            content="três perfis",
            blocked=False,
            blocked_reason=None,
            agent_trace=[AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
        )

    def test_invokes_the_graph_with_user_and_thread_ids_configured(self, service):
        compiled_graph = MagicMock()
        compiled_graph.ainvoke = AsyncMock(return_value={
            "final_response": "resposta",
            "blocked": True,
            "blocked_reason": "conteúdo sensível",
            "called_agents": [],
            "report_html": None,
        })
        service._MultiAgentService__compiled_graph = compiled_graph

        asyncio.run(service.process_message("olá", USER_ID, THREAD_ID))

        _, kwargs = compiled_graph.ainvoke.call_args
        assert kwargs["config"]["configurable"] == {
            "user_id": USER_ID,
            "thread_id": THREAD_ID,
        }

    def test_renders_and_uploads_the_report_when_report_agent_was_called(self, service):
        compiled_graph = MagicMock()
        compiled_graph.ainvoke = AsyncMock(return_value={
            "final_response": "aqui está o relatório",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.REPORT_AGENT],
            "report_html": "<html><body>relatório</body></html>",
        })
        service._MultiAgentService__compiled_graph = compiled_graph
        service.pdf_renderer.render.return_value = b"%PDF-1.7"
        service.storage_service.upload.return_value = "https://xxxxx.supabase.co/storage/v1/object/public/zera-reports/report.pdf"

        response = asyncio.run(service.process_message("gere o relatório", USER_ID, THREAD_ID))

        service.pdf_renderer.render.assert_called_once_with("<html><body>relatório</body></html>")
        _, upload_kwargs = service.storage_service.upload.call_args
        assert upload_kwargs["content"] == b"%PDF-1.7"
        assert upload_kwargs["filename"].endswith(".pdf")
        assert upload_kwargs["content_type"] == "application/pdf"
        assert response.report_url == "https://xxxxx.supabase.co/storage/v1/object/public/zera-reports/report.pdf"

    def test_does_not_render_or_upload_when_report_agent_was_not_called(self, service):
        compiled_graph = MagicMock()
        compiled_graph.ainvoke = AsyncMock(return_value={
            "final_response": "três perfis",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
            "report_html": None,
        })
        service._MultiAgentService__compiled_graph = compiled_graph

        response = asyncio.run(service.process_message("quais perfis existem?", USER_ID, THREAD_ID))

        service.pdf_renderer.render.assert_not_called()
        service.storage_service.upload.assert_not_called()
        assert response.report_url is None

    def test_keeps_the_chat_response_when_pdf_rendering_fails(self, service):
        compiled_graph = MagicMock()
        compiled_graph.ainvoke = AsyncMock(return_value={
            "final_response": "aqui está o relatório",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.REPORT_AGENT],
            "report_html": "<html><body>relatório</body></html>",
        })
        service._MultiAgentService__compiled_graph = compiled_graph
        service.pdf_renderer.render.side_effect = PDFRenderException("invalid markup")

        response = asyncio.run(service.process_message("gere o relatório", USER_ID, THREAD_ID))

        service.storage_service.upload.assert_not_called()
        assert response.content == "aqui está o relatório"
        assert response.report_url is None

    def test_keeps_the_chat_response_when_upload_fails(self, service):
        compiled_graph = MagicMock()
        compiled_graph.ainvoke = AsyncMock(return_value={
            "final_response": "aqui está o relatório",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.REPORT_AGENT],
            "report_html": "<html><body>relatório</body></html>",
        })
        service._MultiAgentService__compiled_graph = compiled_graph
        service.pdf_renderer.render.return_value = b"%PDF-1.7"
        service.storage_service.upload.side_effect = StorageUploadException("404 Not Found")

        response = asyncio.run(service.process_message("gere o relatório", USER_ID, THREAD_ID))

        assert response.content == "aqui está o relatório"
        assert response.report_url is None


class TestSetup:
    @patch("multi_agent.service.MultiServerMCPClient")
    @patch("multi_agent.service.FAQ")
    @patch("multi_agent.service.StateGraph")
    @patch("multi_agent.service.MemorySaver")
    @patch("multi_agent.service.create_agent")
    @patch("multi_agent.service.ChatGroq")
    @patch("multi_agent.service.ChatGoogleGenerativeAI")
    def test_builds_the_guardrail_and_compiles_the_graph(
        self, mock_llm, mock_groq_llm, mock_create_agent, mock_memory_saver, mock_state_graph, mock_faq, mock_mcp_client, service
    ):
        mock_create_agent.side_effect = lambda **kwargs: MagicMock()
        mock_memory_saver.return_value = InMemorySaver()
        mock_graph = mock_state_graph.return_value
        mock_graph.compile.return_value = MagicMock()

        predict_batch_tool = MagicMock(name="predict_time_to_failure_batch")
        predict_batch_tool.name = "predict_time_to_failure_batch"
        categories_tool = MagicMock(name="list_valid_categories")
        categories_tool.name = "list_valid_categories"
        categories_tool.ainvoke = AsyncMock(return_value=["notebook"])
        climate_zones_tool = MagicMock(name="list_valid_climate_zones")
        climate_zones_tool.name = "list_valid_climate_zones"
        climate_zones_tool.ainvoke = AsyncMock(return_value=["TROPICAL"])
        mock_mcp_client.return_value.get_tools = AsyncMock(
            return_value=[predict_batch_tool, categories_tool, climate_zones_tool]
        )

        service.setup()

        assert mock_llm.called
        assert mock_create_agent.call_count == 8
        mock_mcp_client.assert_called_once_with(
            {
                "predict_model": {
                    "url": service.envs.PREDICT_MODEL_MCP_URL,
                    "transport": "streamable_http",
                }
            }
        )
        assert service.guardrail is not None
        assert service.graph is mock_graph
        assert service._MultiAgentService__compiled_graph is mock_graph.compile.return_value
        mock_graph.compile.assert_called_once()


class TestFetchPredictModelTools:
    @patch("multi_agent.service.MultiServerMCPClient")
    def test_fetches_tools_from_the_predict_model_mcp_server(self, mock_mcp_client, service):
        tools = [MagicMock(name="predict_time_to_failure")]
        mock_mcp_client.return_value.get_tools = AsyncMock(return_value=tools)
        service.envs.PREDICT_MODEL_MCP_URL = "https://gateway.zera.internal/predictor"

        result = asyncio.run(service._fetch_predict_model_tools())

        mock_mcp_client.assert_called_once_with(
            {
                "predict_model": {
                    "url": "https://gateway.zera.internal/predictor",
                    "transport": "streamable_http",
                }
            }
        )
        assert result == tools


class TestFetchPredictModelContext:
    @patch("multi_agent.service.MultiServerMCPClient")
    def test_separates_the_batch_tool_from_the_vocabulary_tools(self, mock_mcp_client, service):
        predict_batch_tool = MagicMock(name="predict_time_to_failure_batch")
        predict_batch_tool.name = "predict_time_to_failure_batch"
        categories_tool = MagicMock(name="list_valid_categories")
        categories_tool.name = "list_valid_categories"
        categories_tool.ainvoke = AsyncMock(return_value=["notebook", "celular"])
        climate_zones_tool = MagicMock(name="list_valid_climate_zones")
        climate_zones_tool.name = "list_valid_climate_zones"
        climate_zones_tool.ainvoke = AsyncMock(return_value=["TROPICAL", "ARID"])
        mock_mcp_client.return_value.get_tools = AsyncMock(
            return_value=[predict_batch_tool, categories_tool, climate_zones_tool]
        )

        predict_time_to_failure_batch, categories, climate_zones = asyncio.run(
            service._fetch_predict_model_context()
        )

        assert predict_time_to_failure_batch is predict_batch_tool
        assert categories == ["notebook", "celular"]
        assert climate_zones == ["TROPICAL", "ARID"]
