import asyncio
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from .exception import MultiAgentServiceNotSetupException, UnitMismatchException
from .entity import AgentName, AgentResponse, Message, Role
from .service import MultiAgentService
from .thread_cache import ThreadCacheEntry
USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")
UNIT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_UNIT_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def envs() -> Any:
    envs = MagicMock()
    envs.GEMINI_API_KEY = "fake-key"
    envs.SESSION_TTL_SECONDS = 3600
    envs.SESSION_HISTORY_LIMIT = 50
    return envs


@pytest.fixture
def admin_core() -> Any:
    """admin-core double that puts USER_ID in UNIT_ID, the happy path for every test
    that is not about the unit check itself."""

    client = MagicMock()
    client.get_unit_id = AsyncMock(return_value=UNIT_ID)
    return client


@pytest.fixture
def service(envs: Any, admin_core: Any) -> MultiAgentService:
    repository = MagicMock()
    repository.retrieve_messages.return_value = []
    repository.get_preferences.return_value = None
    return MultiAgentService(
        repository=cast(Any, repository),
        envs=envs,
        logger=cast(Any, MagicMock()),
        pdf_renderer=cast(Any, MagicMock()),
        storage_service=cast(Any, MagicMock()),
        admin_core=cast(Any, admin_core),
    )


def _stub_graph(service: MultiAgentService, end_state: dict) -> MagicMock:
    """Wires a fake compiled graph as `service.compiled_graph`, the single graph
    shared by every thread (no per-thread compile)."""

    compiled = MagicMock()
    compiled.ainvoke = AsyncMock(return_value=end_state)
    service.compiled_graph = compiled
    service.checkpointer = MagicMock()
    return compiled


class TestUnitValidation:
    """The request only proposes a unit; ms-administrative-core decides. Nothing
    here may fall back to an unscoped read."""

    def test_rejects_a_unit_that_is_not_the_users(self, service, admin_core):
        admin_core.get_unit_id = AsyncMock(return_value=OTHER_UNIT_ID)
        compiled = _stub_graph(service, {})

        with pytest.raises(UnitMismatchException):
            asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        compiled.ainvoke.assert_not_called()

    def test_rejects_when_the_admin_core_cannot_resolve_the_user(self, service, admin_core):
        admin_core.get_unit_id = AsyncMock(return_value=None)
        compiled = _stub_graph(service, {})

        with pytest.raises(UnitMismatchException):
            asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        compiled.ainvoke.assert_not_called()

    def test_puts_the_validated_unit_in_the_initial_state(self, service):
        compiled = _stub_graph(service, {
            "final_response": "ok",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.ORCHESTRATOR],
            "report_html": None,
        })

        asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        initial_state = compiled.ainvoke.call_args.args[0]
        assert initial_state["unit_id"] == str(UNIT_ID)


class TestProcessMessage:
    def test_raises_when_the_service_has_not_been_setup(self, service):
        with pytest.raises(MultiAgentServiceNotSetupException):
            asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

    def test_returns_agent_response_built_from_the_graph_end_state(self, service):
        _stub_graph(service, {
            "final_response": "três perfis",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
            "report_html": None,
        })

        response = asyncio.run(service.process_message("quais perfis existem?", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        assert response == AgentResponse(
            content="três perfis",
            blocked=False,
            blocked_reason=None,
            agent_trace=[AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
        )

    def test_invokes_the_graph_with_user_and_thread_ids_configured(self, service):
        compiled = _stub_graph(service, {
            "final_response": "resposta",
            "blocked": True,
            "blocked_reason": "conteúdo sensível",
            "called_agents": [],
            "report_html": None,
        })

        asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        _, kwargs = compiled.ainvoke.call_args
        assert kwargs["config"]["configurable"] == {
            "user_id": USER_ID,
            "thread_id": THREAD_ID,
        }

    def test_reuses_the_cached_thread_on_the_second_call(self, service):
        compiled = _stub_graph(service, {
            "final_response": "resposta",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [],
            "report_html": None,
        })

        asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))
        asyncio.run(service.process_message("de novo", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        # hydration (history/preferences lookup) only happened once; the second call hit the cache.
        service.repository.retrieve_messages.assert_called_once()
        assert compiled.ainvoke.call_count == 2

    def test_hydrates_a_new_thread_from_the_repository_history(self, service):
        service.repository.retrieve_messages.return_value = [
            Message(
                user_id=USER_ID, thread_id=THREAD_ID, role=Role.USER,
                content="oi", agent=None, created_at=datetime.now(timezone.utc),
            ),
        ]
        compiled = _stub_graph(service, {
            "final_response": "resposta",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [],
            "report_html": None,
        })

        asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        service.repository.retrieve_messages.assert_called_once_with(
            USER_ID, THREAD_ID, limit=service.envs.SESSION_HISTORY_LIMIT
        )
        # first call seeds the checkpoint on hydration; second feeds the assistant's
        # reply back after the turn completes.
        assert compiled.update_state.call_count == 2
        hydration_args, hydration_kwargs = compiled.update_state.call_args_list[0]
        assert hydration_args[1]["messages"][0].content == "oi"

    def test_does_not_upload_a_report_generated_in_chat(self, service):
        _stub_graph(service, {
            "final_response": "aqui está o relatório",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.REPORT_AGENT],
            "report_html": "<html><body>relatório</body></html>",
        })

        response = asyncio.run(service.process_message("gere o relatório", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        service.pdf_renderer.render.assert_not_called()
        service.storage_service.upload.assert_not_called()
        assert response.report_url is None

    def test_does_not_render_or_upload_when_report_agent_was_not_called(self, service):
        _stub_graph(service, {
            "final_response": "três perfis",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
            "report_html": None,
        })

        response = asyncio.run(service.process_message("quais perfis existem?", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))

        service.pdf_renderer.render.assert_not_called()
        service.storage_service.upload.assert_not_called()
        assert response.report_url is None

    def test_fires_and_forgets_preferences_update_when_a_thread_cache_entry_expires(self, service):
        _stub_graph(service, {
            "final_response": "resposta",
            "blocked": False,
            "blocked_reason": None,
            "called_agents": [],
            "report_html": None,
        })
        expired = ThreadCacheEntry(
            user_id=USER_ID, thread_id=UUID("33333333-3333-3333-3333-333333333333"),
        )
        service.thread_cache.sweep = MagicMock(return_value=[expired])
        service._update_preferences = AsyncMock()

        asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, "Bearer test-token"))
        asyncio.run(asyncio.sleep(0))  # let the fire-and-forget task run

        service._update_preferences.assert_called_once_with(expired)


class TestDisposalReport:
    def test_generates_uploads_and_stores_a_new_disposal_report(self, service):
        service.repository.get_disposal_report.return_value = None
        service.report_node = AsyncMock(return_value={"report_html": "<html>descarte</html>"})
        service.pdf_renderer.render.return_value = b"%PDF-1.7"
        service.storage_service.upload.return_value = "https://storage/disposal-42.pdf"

        url = asyncio.run(service.create_disposal_report(USER_ID, "42"))

        service.report_node.assert_awaited_once()
        assert "42" in service.report_node.await_args.args[0]["current_request"]
        service.pdf_renderer.render.assert_called_once_with("<html>descarte</html>")
        _, upload_kwargs = service.storage_service.upload.call_args
        assert upload_kwargs["filename"] == "disposal-42.pdf"
        assert upload_kwargs["content"] == b"%PDF-1.7"
        saved = service.repository.save_disposal_report.call_args.args[0]
        assert saved.disposal_id == "42"
        assert saved.user_id == USER_ID
        assert saved.report_url == "https://storage/disposal-42.pdf"
        assert url == "https://storage/disposal-42.pdf"

    def test_returns_the_stored_url_without_generating_again(self, service):
        existing = MagicMock(report_url="https://storage/already.pdf")
        service.repository.get_disposal_report.return_value = existing
        service.report_node = AsyncMock()

        url = asyncio.run(service.create_disposal_report(USER_ID, "42"))

        assert url == "https://storage/already.pdf"
        service.report_node.assert_not_awaited()
        service.storage_service.upload.assert_not_called()
        service.repository.save_disposal_report.assert_not_called()

    def test_reads_the_stored_url(self, service):
        service.repository.get_disposal_report.return_value = MagicMock(report_url="https://storage/already.pdf")

        assert service.get_disposal_report("42") == "https://storage/already.pdf"

    def test_reads_none_when_the_disposal_has_no_report(self, service):
        service.repository.get_disposal_report.return_value = None

        assert service.get_disposal_report("42") is None


class TestSetup:
    @patch("multi_agent.service.MultiServerMCPClient")
    @patch("multi_agent.service.FAQ")
    @patch("multi_agent.service.StateGraph")
    @patch("multi_agent.service.AsyncRedisSaver")
    @patch("multi_agent.service.create_agent")
    @patch("multi_agent.service.ChatGroq")
    @patch("multi_agent.service.ChatGoogleGenerativeAI")
    def test_builds_the_guardrail_and_compiles_the_graph_once(
        self, mock_llm, mock_groq_llm, mock_create_agent, mock_redis_saver, mock_state_graph, mock_faq, mock_mcp_client, service
    ):
        mock_create_agent.side_effect = lambda **kwargs: MagicMock()
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
        assert mock_create_agent.call_count == 10  # 9 graph agents + preferences_agent
        mock_mcp_client.assert_any_call(
            {
                "predict_model": {
                    "url": service.envs.PREDICT_MODEL_MCP_URL,
                    "transport": "streamable_http",
                    "headers": {"apikey": service.envs.PREDICT_MODEL_API_KEY},
                }
            }
        )
        mock_mcp_client.assert_any_call(
            {
                "ms_inventory": {
                    "url": service.envs.MS_INVENTORY_MCP_URL,
                    "transport": "streamable_http",
                    "headers": {"apikey": service.envs.MS_INVENTORY_API_KEY},
                }
            }
        )
        assert service.guardrail is not None
        assert service.preferences_agent is not None
        assert service.graph is mock_graph
        assert service.compiled_graph is mock_graph.compile.return_value
        mock_redis_saver.assert_called_once_with(redis_url=service.envs.REDIS_URL)
        mock_redis_saver.return_value.setup.assert_called_once_with()
        assert service.checkpointer is mock_redis_saver.return_value
        mock_graph.compile.assert_called_once_with(checkpointer=service.checkpointer)


class TestFetchPredictModelTools:
    @patch("multi_agent.service.MultiServerMCPClient")
    def test_fetches_tools_from_the_predict_model_mcp_server(self, mock_mcp_client, service):
        tools = [MagicMock(name="predict_time_to_failure")]
        mock_mcp_client.return_value.get_tools = AsyncMock(return_value=tools)
        service.envs.PREDICT_MODEL_MCP_URL = "https://gateway.zera.internal/predictor"
        service.envs.PREDICT_MODEL_API_KEY = "predict-key"

        result = asyncio.run(service._fetch_predict_model_tools())

        mock_mcp_client.assert_called_once_with(
            {
                "predict_model": {
                    "url": "https://gateway.zera.internal/predictor",
                    "transport": "streamable_http",
                    "headers": {"apikey": "predict-key"},
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
