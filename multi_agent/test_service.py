import asyncio
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from langchain.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph

from .exception import MultiAgentServiceNotSetupException, UnitMismatchException
from .entity import (
    AgentName,
    AgentResponse,
    BLOCKED_USER_MESSAGE,
    DisposalReport,
    Message,
    RedirectTo,
    Role,
    State,
    UserPreferences,
)
from .prompt.report_agent import REPORT_AGENT_SYSTEM_PROMPT_FINAL
from .service import MultiAgentService, message_to_base_message, render_preferences

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
THREAD_ID = UUID("22222222-2222-2222-2222-222222222222")
UNIT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_UNIT_ID = UUID("44444444-4444-4444-4444-444444444444")
BEARER = "Bearer test-token"

END_STATE = {
    "final_response": "resposta",
    "blocked": False,
    "blocked_reason": None,
    "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
    "report_html": None,
}


@pytest.fixture
def unit_resolver() -> Any:
    """admin-core double that puts USER_ID in UNIT_ID, the happy path for every test
    that is not about the unit check itself."""

    client = MagicMock()
    client.get_unit_id = AsyncMock(return_value=UNIT_ID)
    return client


@pytest.fixture
def service(unit_resolver: Any) -> MultiAgentService:
    repository = MagicMock()
    repository.retrieve_messages.return_value = []
    repository.get_preferences.return_value = None
    return MultiAgentService(
        repository=cast(Any, repository),
        session_history_limit=50,
        logger=cast(Any, MagicMock()),
        pdf_renderer=cast(Any, MagicMock()),
        storage_service=cast(Any, MagicMock()),
        unit_resolver=cast(Any, unit_resolver),
        llm=cast(Any, MagicMock()),
        llm_fast=cast(Any, MagicMock()),
        checkpointer=cast(Any, MagicMock()),
        faq_retriever=cast(Any, MagicMock()),
        predict_tool=cast(Any, MagicMock()),
        valid_categories=["notebook"],
        valid_climate_zones=["TROPICAL"],
        inventory_tools=[],
    )


def _stub_graph(service: MultiAgentService, end_state: dict, checkpoint: dict | None = None) -> MagicMock:
    """Fake compiled graph; `checkpoint` is what the shared Redis checkpointer already holds."""

    async def ainvoke(state, config):
        # guardrail_in keeps the user message id, so the end state carries it back
        return {"messages": state["messages"], **end_state}

    compiled = MagicMock()
    compiled.ainvoke = AsyncMock(side_effect=ainvoke)
    compiled.aget_state = AsyncMock(return_value=MagicMock(values=checkpoint or {}))
    compiled.aupdate_state = AsyncMock()
    service.compiled_graph = compiled
    return compiled


def _process(service: MultiAgentService, unit_id: UUID | None = UNIT_ID) -> AgentResponse:
    return asyncio.run(service.process_message("olá", USER_ID, THREAD_ID, unit_id, BEARER))


class TestUnitValidation:
    """The request only proposes a unit; ms-administrative-core decides. Nothing
    here may fall back to an unscoped read."""

    def test_rejects_a_unit_that_is_not_the_users(self, service, unit_resolver):
        unit_resolver.get_unit_id = AsyncMock(return_value=OTHER_UNIT_ID)
        compiled = _stub_graph(service, {})

        with pytest.raises(UnitMismatchException):
            _process(service)

        compiled.ainvoke.assert_not_called()

    def test_rejects_when_the_admin_core_cannot_resolve_the_user(self, service, unit_resolver):
        unit_resolver.get_unit_id = AsyncMock(return_value=None)
        compiled = _stub_graph(service, {})

        with pytest.raises(UnitMismatchException):
            _process(service, unit_id=None)

        compiled.ainvoke.assert_not_called()

    def test_puts_the_validated_unit_in_the_initial_state(self, service):
        compiled = _stub_graph(service, END_STATE)

        _process(service)

        assert compiled.ainvoke.call_args.args[0]["unit_id"] == str(UNIT_ID)

    def test_uses_the_users_unit_when_none_is_claimed(self, service, unit_resolver):
        compiled = _stub_graph(service, END_STATE)

        _process(service, unit_id=None)

        unit_resolver.get_unit_id.assert_awaited_once_with(USER_ID, BEARER)
        assert compiled.ainvoke.call_args.args[0]["unit_id"] == str(UNIT_ID)


class TestProcessMessage:
    def test_raises_when_the_service_has_not_been_setup(self, service):
        with pytest.raises(MultiAgentServiceNotSetupException):
            _process(service)

    def test_returns_agent_response_built_from_the_graph_end_state(self, service):
        _stub_graph(service, END_STATE)

        assert _process(service) == AgentResponse(
            content="resposta",
            blocked=False,
            blocked_reason=None,
            agent_trace=[AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR],
        )

    def test_replaces_guardrail_codes_with_a_user_facing_message_when_blocked(self, service):
        _stub_graph(service, {
            **END_STATE,
            "final_response": None,
            "blocked": True,
            "blocked_reason": "inappropriate_content",
            "called_agents": [AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR, AgentName.GUARDRAIL_OUT],
        })

        response = _process(service)

        assert response.content == BLOCKED_USER_MESSAGE
        assert response.blocked is True
        assert response.blocked_reason == "inappropriate_content"

    def test_forwards_redirect_to_from_the_end_state(self, service):
        redirect = RedirectTo(screen="Scan", message="Escanear código de barras")
        _stub_graph(service, {**END_STATE, "redirect_to": redirect})

        assert _process(service).redirect_to == redirect

    def test_invokes_the_graph_with_user_and_thread_ids_configured(self, service):
        compiled = _stub_graph(service, END_STATE)

        _process(service)

        assert compiled.ainvoke.call_args.kwargs["config"]["configurable"] == {
            "user_id": USER_ID,
            "thread_id": THREAD_ID,
        }

    def test_does_not_hydrate_when_the_checkpoint_already_has_the_thread(self, service):
        compiled = _stub_graph(service, END_STATE, checkpoint={"messages": [HumanMessage(content="oi")]})

        _process(service)

        service.repository.retrieve_messages.assert_not_called()
        # only the assistant's reply is fed back; nothing is seeded twice
        compiled.aupdate_state.assert_awaited_once()

    def test_hydrates_an_empty_checkpoint_from_the_repository_history(self, service):
        service.repository.retrieve_messages.return_value = [
            Message(
                user_id=USER_ID, thread_id=THREAD_ID, role=Role.USER,
                content="oi", agent=None, created_at=datetime.now(timezone.utc),
            ),
        ]
        service._update_preferences = AsyncMock()
        compiled = _stub_graph(service, END_STATE)

        _process(service)

        service.repository.retrieve_messages.assert_called_once_with(USER_ID, THREAD_ID, limit=50)
        # first call seeds the checkpoint; second feeds the assistant's reply back
        assert compiled.aupdate_state.await_count == 2
        assert compiled.aupdate_state.await_args_list[0].args[1]["messages"][0].content == "oi"

    def test_refreshes_preferences_when_an_expired_conversation_is_resumed(self, service):
        history = [Message(
            user_id=USER_ID, thread_id=THREAD_ID, role=Role.USER,
            content="oi", agent=None, created_at=datetime.now(timezone.utc),
        )]
        service.repository.retrieve_messages.return_value = history
        service._update_preferences = AsyncMock()
        _stub_graph(service, END_STATE)

        async def run():
            await service.process_message("olá", USER_ID, THREAD_ID, UNIT_ID, BEARER)
            await asyncio.sleep(0)  # let the fire-and-forget task run

        asyncio.run(run())

        service._update_preferences.assert_awaited_once_with(USER_ID, history, None)

    def test_saves_question_and_answer_together_once_the_turn_succeeds(self, service):
        _stub_graph(service, END_STATE)

        _process(service)

        saved = [call.args[0] for call in service.repository.save_message.call_args_list]
        assert [(m.role, m.content) for m in saved] == [(Role.USER, "olá"), (Role.ASSISTANT, "resposta")]
        assert saved[0].created_at <= saved[1].created_at

    def test_a_failed_turn_saves_nothing_and_leaves_no_question_in_the_checkpoint(self, service):
        compiled = _stub_graph(service, END_STATE)
        compiled.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))

        with pytest.raises(RuntimeError):
            _process(service)

        service.repository.save_message.assert_not_called()
        update = compiled.aupdate_state.await_args
        assert update is not None
        assert isinstance(update.args[1]["messages"][0], RemoveMessage)
        assert update.kwargs["as_node"] == AgentName.GUARDRAIL_OUT

    def test_rollback_works_on_a_real_checkpointed_graph(self, service):
        def guardrail_in(state):
            return {"called_agents": [AgentName.GUARDRAIL_IN]}

        def guardrail_out(state):
            raise RuntimeError("guardrail_out down")

        graph = StateGraph(State)
        graph.add_node(AgentName.GUARDRAIL_IN, guardrail_in)
        graph.add_node(AgentName.GUARDRAIL_OUT, guardrail_out)
        graph.set_entry_point(AgentName.GUARDRAIL_IN)
        graph.add_edge(AgentName.GUARDRAIL_IN, AgentName.GUARDRAIL_OUT)
        service.compiled_graph = graph.compile(checkpointer=InMemorySaver())

        with pytest.raises(RuntimeError):
            _process(service)

        state = asyncio.run(service.compiled_graph.aget_state(service._config(USER_ID, THREAD_ID)))
        assert state.values["messages"] == []
        assert state.next == ()

    def test_does_not_save_or_feed_back_a_message_blocked_at_guardrail_in(self, service):
        compiled = _stub_graph(service, {**END_STATE, "blocked": True, "called_agents": [AgentName.GUARDRAIL_IN]})

        _process(service)

        service.repository.save_message.assert_not_called()
        compiled.aupdate_state.assert_not_called()

    def test_does_not_upload_a_report_generated_in_chat(self, service):
        _stub_graph(service, {**END_STATE, "report_html": "<html><body>relatório</body></html>"})

        response = _process(service)

        service.pdf_renderer.render.assert_not_called()
        service.storage_service.upload.assert_not_called()
        assert response.report_url is None


class TestUpdatePreferences:
    def test_upserts_what_the_preferences_agent_extracted(self, service):
        service.preferences_agent = MagicMock()
        service.preferences_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(
            content='{"writing_style": "Informal", "company_context": null, "frequent_requests": ["relatório"]}'
        )]})

        asyncio.run(service._update_preferences(USER_ID, [], None))

        saved = service.repository.upsert_preferences.call_args.args[0]
        assert saved.writing_style == "Informal"
        assert saved.frequent_requests == ["relatório"]

    def test_never_raises(self, service):
        service.preferences_agent = MagicMock()
        service.preferences_agent.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))

        asyncio.run(service._update_preferences(USER_ID, [], None))

        service.logger.Error.assert_called_once()


class TestDisposalReport:
    def test_generates_uploads_and_stores_a_new_disposal_report(self, service):
        service.repository.get_disposal_report.return_value = None
        service.report_node = AsyncMock(return_value={"report_html": "<html>descarte</html>"})
        service.pdf_renderer.render.return_value = b"%PDF-1.7"
        service.storage_service.upload.return_value = "https://storage/disposal-42.pdf"

        url = asyncio.run(service.create_disposal_report(USER_ID, "42", BEARER))

        state = service.report_node.await_args.args[0]
        assert "42" in state["current_request"]
        assert state["unit_id"] == str(UNIT_ID)
        service.pdf_renderer.render.assert_called_once_with("<html>descarte</html>")
        _, upload_kwargs = service.storage_service.upload.call_args
        assert upload_kwargs["filename"] == "disposal-42.pdf"
        assert upload_kwargs["content"] == b"%PDF-1.7"
        saved = service.repository.save_disposal_report.call_args.args[0]
        assert (saved.disposal_id, saved.user_id, saved.unit_id, saved.report_url) == ("42", USER_ID, UNIT_ID, url)
        assert url == "https://storage/disposal-42.pdf"

    def test_returns_the_stored_url_without_generating_again(self, service):
        service.repository.get_disposal_report.return_value = _stored_report(unit_id=UNIT_ID)
        service.report_node = AsyncMock()

        url = asyncio.run(service.create_disposal_report(USER_ID, "42", BEARER))

        assert url == "https://storage/already.pdf"
        service.report_node.assert_not_awaited()
        service.storage_service.upload.assert_not_called()

    def test_refuses_another_units_stored_report(self, service):
        service.repository.get_disposal_report.return_value = _stored_report(unit_id=OTHER_UNIT_ID)
        service.report_node = AsyncMock()

        with pytest.raises(UnitMismatchException):
            asyncio.run(service.create_disposal_report(USER_ID, "42", BEARER))

        service.report_node.assert_not_awaited()

    def test_refuses_when_the_user_unit_cannot_be_resolved(self, service, unit_resolver):
        service.repository.get_disposal_report.return_value = None
        unit_resolver.get_unit_id = AsyncMock(return_value=None)
        service.report_node = AsyncMock()

        with pytest.raises(UnitMismatchException):
            asyncio.run(service.create_disposal_report(USER_ID, "42", BEARER))

        service.report_node.assert_not_called()

    def test_reads_only_the_units_own_report(self, service):
        service.repository.get_disposal_report.return_value = _stored_report(unit_id=UNIT_ID)
        assert asyncio.run(service.get_disposal_report(USER_ID, "42", BEARER)) == "https://storage/already.pdf"

        service.repository.get_disposal_report.return_value = _stored_report(unit_id=OTHER_UNIT_ID)
        assert asyncio.run(service.get_disposal_report(USER_ID, "42", BEARER)) is None

        service.repository.get_disposal_report.return_value = None
        assert asyncio.run(service.get_disposal_report(USER_ID, "42", BEARER)) is None

    def test_a_report_stored_without_unit_is_only_for_whoever_generated_it(self, service):
        service.repository.get_disposal_report.return_value = _stored_report(unit_id=None)
        assert asyncio.run(service.get_disposal_report(USER_ID, "42", BEARER)) == "https://storage/already.pdf"

        someone_else = UUID("55555555-5555-5555-5555-555555555555")
        assert asyncio.run(service.get_disposal_report(someone_else, "42", BEARER)) is None


def _stored_report(unit_id: UUID | None) -> DisposalReport:
    return DisposalReport(
        disposal_id="42",
        user_id=USER_ID,
        unit_id=unit_id,
        report_url="https://storage/already.pdf",
        created_at=datetime.now(timezone.utc),
    )


class TestConversations:
    def test_delegates_to_the_repository(self, service):
        service.list_conversations(USER_ID, 2, 10)
        service.repository.list_conversations.assert_called_once_with(USER_ID, 2, 10)

        service.get_conversation(USER_ID, THREAD_ID)
        service.repository.retrieve_messages.assert_called_once_with(USER_ID, THREAD_ID, limit=None)


class TestSetup:
    @patch("multi_agent.service.create_agent")
    def test_builds_every_agent_over_the_injected_adapters_and_compiles_once(self, mock_create_agent, service):
        mock_create_agent.side_effect = lambda **kwargs: MagicMock()
        report_tool = MagicMock()
        report_tool.name = "get_disposal_report"
        service.inventory_tools = [report_tool]
        service.checkpointer = InMemorySaver()

        service.setup()

        assert mock_create_agent.call_count == 10  # 9 graph agents + preferences_agent
        assert service.compiled_graph is not None
        report_agent_call = next(
            call for call in mock_create_agent.call_args_list
            if call.kwargs.get("system_prompt") is REPORT_AGENT_SYSTEM_PROMPT_FINAL
        )
        assert report_agent_call.kwargs["tools"] == [report_tool]
        assert report_agent_call.kwargs["model"] is service.llm_fast


class TestMessageToBaseMessage:
    @pytest.mark.parametrize("role,expected", [
        (Role.USER, HumanMessage), (Role.ASSISTANT, AIMessage), (Role.SYSTEM, SystemMessage),
    ])
    def test_maps_each_role(self, role, expected):
        message = Message(user_id=USER_ID, thread_id=THREAD_ID, role=role, content="oi", created_at=datetime.now(timezone.utc))
        assert isinstance(message_to_base_message(message), expected)


class TestRenderPreferences:
    def test_renders_every_known_field(self):
        text = render_preferences(UserPreferences(
            user_id=USER_ID,
            writing_style="Informal",
            company_context="TI",
            frequent_requests=["relatório mensal"],
            updated_at=datetime.now(timezone.utc),
        ))
        assert "Informal" in text and "TI" in text and "relatório mensal" in text

    def test_omits_unset_fields(self):
        assert render_preferences(UserPreferences(user_id=USER_ID, updated_at=datetime.now(timezone.utc))) == ""
