import asyncio
import contextlib
import json
from datetime import datetime, timezone
from typing import Any, Optional, cast
from uuid import UUID, uuid4

from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from logger.logger import Logger

from .entity import (
    AgentName,
    AgentResponse,
    BLOCKED_USER_MESSAGE,
    ConversationPage,
    DisposalReport,
    Message,
    Role,
    State,
    UserPreferences,
)
from .exception import MultiAgentServiceNotSetupException, UnitMismatchException
from .graph import build_graph
from .multi_agent import IMultiAgentRepository, IMultiAgentService, IPdfRenderer, IStorageService, IUnitResolver
from .unit_scope import bind_unit_id

# completed prompts
from .prompt.guardrail_in import GUARDRAIL_IN_SYSTEM_PROMPT_FINAL
from .prompt.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT_FINAL
from .prompt.predict_model import build_predict_model_system_prompt
from .prompt.inventory_agent import INVENTORY_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.report_agent import REPORT_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.faq_agent import FAQ_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.formatter_agent import FORMATTER_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.judge_agent import JUDGE_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.guardrail_out import GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL
from .prompt.preferences_agent import PREFERENCES_AGENT_SYSTEM_PROMPT_FINAL

# agents
from .agents.guardrail import Guardrail
from .agents.orchestrator import make_orchestrator_func
from .agents.predict_model import make_predict_model_func
from .agents.inventory import make_inventory_func
from .agents.faq import make_faq_func
from .agents.report import make_report_func
from .agents.formatter import make_formatter_func
from .agents.judge import make_judge_func
from .agents.message_utils import parse_json_message


def message_to_base_message(message: Message) -> BaseMessage:
    """Converts a persisted Message into the BaseMessage LangGraph expects."""

    if message.role == Role.USER:
        return HumanMessage(content=message.content)
    if message.role == Role.ASSISTANT:
        return AIMessage(content=message.content)
    return SystemMessage(content=message.content)


def render_preferences(preferences: UserPreferences) -> str:
    """Renders UserPreferences into the plain-text block injected into State.user_preferences."""

    parts = []
    if preferences.writing_style:
        parts.append(f"Estilo de escrita: {preferences.writing_style}")
    if preferences.company_context:
        parts.append(f"Contexto na empresa: {preferences.company_context}")
    if preferences.frequent_requests:
        parts.append(f"Pedidos frequentes: {', '.join(preferences.frequent_requests)}")
    return " | ".join(parts)


class MultiAgentService(IMultiAgentService):
    """
    Application core: builds the agents over the injected adapters (models, tools,
    checkpointer, repository) and runs the graph. Concrete providers are chosen in
    the composition root (app/api/composition.py), never here.
    """

    compiled_graph: Optional[CompiledStateGraph] = None

    def __init__(
        self,
        repository: IMultiAgentRepository,
        session_history_limit: int,
        logger: Logger,
        pdf_renderer: IPdfRenderer,
        storage_service: IStorageService,
        unit_resolver: IUnitResolver,
        llm: BaseChatModel,
        llm_fast: BaseChatModel,
        checkpointer: BaseCheckpointSaver,
        faq_retriever: BaseTool,
        predict_tool: BaseTool,
        valid_categories: list[str],
        valid_climate_zones: list[str],
        inventory_tools: list[BaseTool],
    ) -> None:
        self.repository = repository
        self.session_history_limit = session_history_limit
        self.logger = logger
        self.pdf_renderer = pdf_renderer
        self.storage_service = storage_service
        self.unit_resolver = unit_resolver
        self.llm = llm
        self.llm_fast = llm_fast
        self.checkpointer = checkpointer
        self.faq_retriever = faq_retriever
        self.predict_tool = predict_tool
        self.valid_categories = valid_categories
        self.valid_climate_zones = valid_climate_zones
        self.inventory_tools = bind_unit_id(inventory_tools)
        self._background: set[asyncio.Task] = set()

    def setup(self) -> None:
        """Builds every agent and compiles the graph once; thread_id partitions state between threads."""
        self.logger.Info("Setting up the multi-agent service")

        def agent(model: BaseChatModel, prompt: str, tools: list[BaseTool] | None = None) -> CompiledStateGraph:
            return create_agent(model=model, system_prompt=prompt, tools=tools)

        self.guardrail = Guardrail(
            agent(self.llm_fast, GUARDRAIL_IN_SYSTEM_PROMPT_FINAL),
            agent(self.llm_fast, GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL),
            self.logger,
        )
        self.preferences_agent = agent(self.llm_fast, PREFERENCES_AGENT_SYSTEM_PROMPT_FINAL)
        self.report_node = make_report_func(
            agent(self.llm_fast, REPORT_AGENT_SYSTEM_PROMPT_FINAL, self.inventory_tools)
        )

        nodes = {
            AgentName.GUARDRAIL_IN: self.guardrail.guardrail_in_func,
            AgentName.ORCHESTRATOR: make_orchestrator_func(agent(self.llm_fast, ORCHESTRATOR_SYSTEM_PROMPT_FINAL)),
            AgentName.PREDICT_MODEL: make_predict_model_func(agent(
                self.llm_fast,
                build_predict_model_system_prompt(self.valid_categories, self.valid_climate_zones),
                [self.predict_tool],
            )),
            AgentName.REPORT_AGENT: self.report_node,
            AgentName.INVENTORY_AGENT: make_inventory_func(
                agent(self.llm, INVENTORY_AGENT_SYSTEM_PROMPT_FINAL, self.inventory_tools)
            ),
            AgentName.FAQ_AGENT: make_faq_func(agent(self.llm, FAQ_AGENT_SYSTEM_PROMPT_FINAL, [self.faq_retriever])),
            AgentName.FORMATTER_AGENT: make_formatter_func(agent(self.llm_fast, FORMATTER_AGENT_SYSTEM_PROMPT_FINAL)),
            AgentName.JUDGE_AGENT: make_judge_func(agent(self.llm_fast, JUDGE_AGENT_SYSTEM_PROMPT_FINAL)),
            AgentName.GUARDRAIL_OUT: self.guardrail.guardrail_out_func,
        }

        graph = build_graph(nodes, self.guardrail.guardrail_in_fate_decision)
        self.compiled_graph = graph.compile(checkpointer=self.checkpointer)

    @staticmethod
    def _config(user_id: UUID, thread_id: UUID) -> Any:
        return {"configurable": {"user_id": user_id, "thread_id": thread_id}}

    async def _hydrate_thread(self, user_id: UUID, thread_id: UUID, config: Any) -> None:
        """
        Seeds an empty checkpoint (first turn, or the Redis TTL expired) with Mongo
        data: recent messages and the user's long-term preferences. Only runs when
        the checkpoint is empty, so replicas sharing Redis never seed it twice.
        """
        assert self.compiled_graph is not None

        self.logger.Info(f"Hydrating thread for user_id: {user_id}, thread_id: {thread_id}")

        history = await asyncio.to_thread(
            self.repository.retrieve_messages, user_id, thread_id, limit=self.session_history_limit
        )
        preferences = await asyncio.to_thread(self.repository.get_preferences, user_id)

        if history or preferences:
            await self.compiled_graph.aupdate_state(config, cast(State, {
                "messages": [message_to_base_message(m) for m in history],
                "user_preferences": render_preferences(preferences) if preferences else None,
            }))

        if history:
            # only update the preferences if there is a new history (in this flow, there is no message in the cache)
            task = asyncio.create_task(self._update_preferences(user_id, history, preferences))
            self._background.add(task)
            task.add_done_callback(self._background.discard)

    async def _update_preferences(
        self, user_id: UUID, history: list[Message], current: UserPreferences | None
    ) -> None:
        """
        Fire-and-forget: summarizes a conversation into long-term preferences (writing
        style, company context, frequent requests). Never on the response critical
        path, and never allowed to raise.
        """
        try:
            payload = {
                "current_preferences": current.model_dump(mode="json", exclude={"user_id", "updated_at"}) if current else None,
                "conversation": "\n".join(f"{m.role.value}: {m.content}" for m in history),
            }
            response = await self.preferences_agent.ainvoke(
                {"messages": [HumanMessage(content=json.dumps(payload))]}
            )
            extracted = parse_json_message(response["messages"][-1].content)

            await asyncio.to_thread(self.repository.upsert_preferences, UserPreferences(
                user_id=user_id,
                writing_style=extracted.get("writing_style"),
                company_context=extracted.get("company_context"),
                frequent_requests=extracted.get("frequent_requests") or [],
                updated_at=datetime.now(timezone.utc),
            ))
            self.logger.Info(f"Updated preferences for user_id: {user_id}")
        except Exception as e:
            self.logger.Error(f"Failed to update preferences for user_id: {user_id}", e)

    async def _resolve_unit(self, user_id: UUID, claimed: UUID | None, authorization: str) -> UUID:
        """ms-administrative-core says which unit the user belongs to. A claimed unit
        that differs, or an unresolvable user, is refused — never widened into a global read."""

        actual = await self.unit_resolver.get_unit_id(user_id, authorization)
        if actual is None or (claimed is not None and actual != claimed):
            self.logger.Warning(f"Rejected unit_id {claimed} for user_id: {user_id} (admin-core says {actual})")
            raise UnitMismatchException(f"unit_id does not belong to user {user_id}")
        return actual

    async def process_message(
        self, message: str, user_id: UUID, thread_id: UUID, unit_id: UUID | None, authorization: str
    ) -> AgentResponse:
        if self.compiled_graph is None:
            self.logger.Error("The multi-agent service is not set up. Please call the setup() method before processing messages.", MultiAgentServiceNotSetupException)
            raise MultiAgentServiceNotSetupException("The multi-agent service is not set up. Please call the setup() method before processing messages.")

        # resolve the unit_id for the user
        # when fetching the unit_id, the system also validates the authorization header
        unit_id = await self._resolve_unit(user_id, unit_id, authorization)

        config = self._config(user_id, thread_id)
        if not (await self.compiled_graph.aget_state(config)).values:
            await self._hydrate_thread(user_id, thread_id, config)

        # guardrail_in replaces it in place with the masked text (same id), or removes it if blocked
        user_message_id = str(uuid4())
        user_message = HumanMessage(content=message, id=user_message_id)
        received_at = datetime.now(timezone.utc)

        # delta state: only the fields with a reducer (reset by an empty/zero value) plus the
        # fields that a node may skip this turn and that would otherwise leak the previous
        # turn's value through the checkpoint.
        initial_state = cast(
            State,
            {
                "messages": [user_message],
                "called_agents": [],
                "current_request": None,
                "unit_id": str(unit_id),
                "next_agent": None,
                "intent": None,
                "pending_agent": None,
                "pending_request": None,
                "blocked": False,
                "blocked_reason": None,
                "pii_map": {},
                "answer": None,
                "sources": [],
                "redirect_to": None,
                "report_html": None,
                "predictions": [],
                "inventory_answer": None,
                "formatted_response": None,
                "approved": None,
                "discrepancy": None,
                "judge_attempts": 0,
                "final_response": None,
            },
        )

        self.logger.Info(f"Processing message for user_id: {user_id}, thread_id: {thread_id}")

        try:
            end_state = await self.compiled_graph.ainvoke(initial_state, config=config)
        except Exception:
            # a failed turn must not leave a question without an answer for the next turn;
            # as guardrail_out, so the half-finished run is closed instead of resumed
            with contextlib.suppress(Exception):
                await self.compiled_graph.aupdate_state(
                    config, {"messages": [RemoveMessage(id=user_message_id)]}, as_node=AgentName.GUARDRAIL_OUT
                )
            raise

        # the flow only leaves guardrail_in when blocked=False there; if blocked=True and
        # the orchestrator was never reached, the flow stopped at guardrail_in, so nothing
        # is saved. blocked=True set later on (orchestrator's unclassified intent,
        # guardrail_out) still produces a turn worth saving.
        stopped_at_guardrail_in = end_state["blocked"] and AgentName.ORCHESTRATOR not in end_state["called_agents"]
        content = BLOCKED_USER_MESSAGE if end_state["blocked"] else (end_state["final_response"] or "")

        if not stopped_at_guardrail_in:
            masked = next(m for m in end_state["messages"] if m.id == user_message_id)

            # question and answer are saved together, only once the whole turn succeeded
            await asyncio.to_thread(self.repository.save_message, Message(
                user_id=user_id,
                thread_id=thread_id,
                role=Role.USER,
                content=str(masked.content),
                agent=AgentName.GUARDRAIL_IN,
                created_at=received_at,
            ))
            await asyncio.to_thread(self.repository.save_message, Message(
                user_id=user_id,
                thread_id=thread_id,
                role=Role.ASSISTANT,
                content=content,
                agent=AgentName.GUARDRAIL_OUT,
                created_at=datetime.now(timezone.utc),
            ))

            # feeds the assistant's reply back into the checkpoint so the orchestrator
            # can resolve conversational references on the next turn.
            await self.compiled_graph.aupdate_state(config, {"messages": [AIMessage(content=content)]})

        self.logger.Info(f"Finished processing message for user_id: {user_id}, thread_id: {thread_id}")

        return AgentResponse(
            content = content,
            blocked = end_state["blocked"],
            blocked_reason = end_state["blocked_reason"],
            agent_trace = end_state["called_agents"],
            redirect_to = end_state.get("redirect_to"),
        )

    async def create_disposal_report(self, user_id: UUID, disposal_id: str, authorization: str) -> str:
        """
        Generate and store the PDF for one disposal, or return the URL already stored.
        Uses the same report agent as the chat; only this path uploads the PDF.
        unit_id is resolved here and injected into get_disposal_report, the same way the chat does.
        """
        unit_id = await self._resolve_unit(user_id, None, authorization)

        existing = await asyncio.to_thread(self.repository.get_disposal_report, disposal_id)
        if existing is not None:
            if not self._owns(existing, user_id, unit_id):
                raise UnitMismatchException(f"disposal {disposal_id} does not belong to the unit of user {user_id}")
            return existing.report_url

        result = await self.report_node(cast(State, {
            "current_request": f"Gere o relatório do descarte {disposal_id}.",
            "messages": [],
            "user_preferences": None,
            "unit_id": str(unit_id),
        }))
        pdf_bytes = await asyncio.to_thread(self.pdf_renderer.render, result["report_html"])
        report_url = await asyncio.to_thread(
            self.storage_service.upload,
            content=pdf_bytes,
            filename=f"disposal-{disposal_id}.pdf",
            content_type="application/pdf",
        )
        await asyncio.to_thread(self.repository.save_disposal_report, DisposalReport(
            disposal_id=disposal_id,
            user_id=user_id,
            unit_id=unit_id,
            report_url=report_url,
            created_at=datetime.now(timezone.utc),
        ))
        return report_url

    async def get_disposal_report(self, user_id: UUID, disposal_id: str, authorization: str) -> str | None:
        """The stored PDF URL for this disposal, or None if it was never generated or is another unit's."""
        unit_id = await self._resolve_unit(user_id, None, authorization)
        existing = await asyncio.to_thread(self.repository.get_disposal_report, disposal_id)
        return existing.report_url if existing is not None and self._owns(existing, user_id, unit_id) else None

    @staticmethod
    def _owns(report: DisposalReport, user_id: UUID, unit_id: UUID) -> bool:
        # reports stored before unit_id was recorded are only handed back to whoever generated them
        return report.unit_id == unit_id if report.unit_id is not None else report.user_id == user_id

    def list_conversations(self, user_id: UUID, page: int, page_size: int) -> ConversationPage:
        return self.repository.list_conversations(user_id, page, page_size)

    def get_conversation(self, user_id: UUID, thread_id: UUID) -> list[Message]:
        return self.repository.retrieve_messages(user_id, thread_id, limit=None)
