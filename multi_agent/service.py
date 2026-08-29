import asyncio
from typing import cast

from langchain.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from multi_agent.multi_agent import IMultiAgentRepository, IMultiAgentService

from .entity import Message, AgentResponse, State, Role
from uuid import UUID, uuid4
from datetime import datetime, timezone

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from config.environments import Environments
from logger.logger import Logger

# storage
from _internal.storage.storage import IStorageService
from _internal.storage.pdf import PdfRenderer
from _internal.storage.exceptions import StorageServiceException

# completed prompts
from .prompt.guardrail_in import GUARDRAIL_IN_SYSTEM_PROMPT_FINAL
from .prompt.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT_FINAL
from .prompt.predict_model import build_predict_model_system_prompt
from .prompt.report_agent import REPORT_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.faq_agent import FAQ_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.formatter_agent import FORMATTER_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.judge_agent import JUDGE_AGENT_SYSTEM_PROMPT_FINAL
from .prompt.guardrail_out import GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL

# checkpointer
from langgraph.checkpoint.memory import MemorySaver

#langchain/langgraph imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent

# state
from .entity import State

# agents imports
from .entity import AgentName

from .agents.guardrail import Guardrail
from .agents.orchestrator import make_orchestrator_func, orchestrator_fate_decision
from .agents.predict_model import make_predict_model_func
from .agents.faq import FAQ
from .agents.report import make_report_func
from .agents.formatter import make_formatter_func
from .agents.judge import make_judge_func, judge_fate_decision

from langchain_groq import ChatGroq

# exceptions
from .exception import MultiAgentServiceNotSetupException

from typing import Optional

class MultiAgentService(IMultiAgentService):
    """Concrete implementation of the multi-agent service."""

    graph: StateGraph[State]
    __compiled_graph: Optional[CompiledStateGraph[State]] = None
    guardrail: Guardrail
    faq: FAQ

    repository: IMultiAgentRepository
    envs: Environments
    logger: Logger
    pdf_renderer: PdfRenderer
    storage_service: IStorageService

    def __init__(
        self,
        repository: IMultiAgentRepository,
        envs: Environments,
        logger: Logger,
        pdf_renderer: PdfRenderer,
        storage_service: IStorageService,
    ) -> None:
        self.repository = repository
        self.envs = envs
        self.logger = logger
        self.pdf_renderer = pdf_renderer
        self.storage_service = storage_service

    async def _fetch_predict_model_tools(self) -> list[BaseTool]:
        """
        Discovers the tools exposed by the sdk-ml-failure-predictor MCP server (predict_time_to_failure),
        reached through the Kong gateway. No auth headers are sent yet — see docs/integration-predict-time-to-failure.md.
        """
        assert self.envs.PREDICT_MODEL_MCP_URL is not None, "PREDICT_MODEL_MCP_URL must be set to reach the predict_model MCP server"

        client = MultiServerMCPClient(
            {
                "predict_model": {
                    "url": self.envs.PREDICT_MODEL_MCP_URL,
                    "transport": "streamable_http",
                }
            }
        )
        return await client.get_tools()

    async def _fetch_predict_model_context(self) -> tuple[BaseTool, list[str], list[str]]:
        """
        Besides predict_time_to_failure_batch, the predict_model MCP server also exposes
        list_valid_categories/list_valid_climate_zones, read directly from the
        trained model's vocabulary. We call them once here to build the
        predict_model system prompt at boot, instead of keeping a hand-copied
        list in the prompt that can silently drift from the trained model
        (see docs/integration-predict-time-to-failure.md).

        Returns the predict_time_to_failure_batch tool so it can be bound directly to
        predict_model_agent: the agent itself extracts, validates/clamps and calls it
        once with every eligible item (see multi_agent/prompt/predict_model.py).
        """
        tools = await self._fetch_predict_model_tools()
        tools_by_name: dict[str, BaseTool] = {tool.name: tool for tool in tools}

        categories: list[str] = await tools_by_name["list_valid_categories"].ainvoke({})
        climate_zones: list[str] = await tools_by_name["list_valid_climate_zones"].ainvoke({})

        predict_time_to_failure_batch = tools_by_name["predict_time_to_failure_batch"]

        return predict_time_to_failure_batch, categories, climate_zones

    def setup(self) -> None:
        """
        Setup the MultiAgentService with the provided repository.
        """
        self.logger.Info("Setting up the multi-agent service")

        # initializes the model
        self.logger.Info("initializing the gemini llm")
        api_key = SecretStr(self.envs.GEMINI_API_KEY) if self.envs.GEMINI_API_KEY else None
        llm_gemini = ChatGoogleGenerativeAI(
            model = "gemini-3.5-flash",
            temperature = 0.2,
            top_p = 0.9,
            api_key = api_key,
            reasoning_effort = "low",
        )

        # uses groq as fallback if gemini is not available
        llm_groq = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0.2,
            api_key=SecretStr(self.envs.GROQ_API_KEY) if self.envs.GROQ_API_KEY else None,
        )
        
        # we just use cast here to hide the type error, but in run time this should not be a problem
        llm = cast(BaseChatModel, llm_gemini.with_fallbacks([llm_groq]))
        
        llm_gemini_fast = ChatGoogleGenerativeAI(
            model = "gemini-3.5-flash-lite",
            temperature = 0.2,
            top_p = 0.9,
            api_key = api_key,
            reasoning_effort = "low",
        )
        llm_fast = cast(BaseChatModel, llm_gemini_fast.with_fallbacks([llm_groq]))

        # initializes the system agents
        guardrail_in_agent = create_agent(
            model=llm_fast,
            system_prompt=GUARDRAIL_IN_SYSTEM_PROMPT_FINAL,
        )

        orchestrator_agent = create_agent(
            model=llm_fast,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT_FINAL,
        )

        # discovers the predict_time_to_failure_batch tool and the valid category/climateZone
        # domains from the sdk-ml-failure-predictor MCP server (via Kong)
        self.logger.Info("Fetching predict_model MCP tools")
        predict_time_to_failure_batch, valid_categories, valid_climate_zones = asyncio.run(
            self._fetch_predict_model_context()
        )
        predict_model_agent = create_agent(
            model=llm_fast,
            system_prompt=build_predict_model_system_prompt(valid_categories, valid_climate_zones),
            tools=[predict_time_to_failure_batch],
        )

        report_agent = create_agent(
            model=llm_fast,
            system_prompt=REPORT_AGENT_SYSTEM_PROMPT_FINAL,
        )

        self.faq = FAQ(self.envs, self.logger)
        self.faq.setup()

        faq_agent = create_agent(
            model=llm,
            system_prompt=FAQ_AGENT_SYSTEM_PROMPT_FINAL,
            tools=[self.faq.make_retrieve_context_tool()],
        )
        self.faq.faq_agent = faq_agent

        formatter_agent = create_agent(
            model=llm_fast,
            system_prompt=FORMATTER_AGENT_SYSTEM_PROMPT_FINAL,
        )

        judge_agent = create_agent(
            model=llm_fast,
            system_prompt=JUDGE_AGENT_SYSTEM_PROMPT_FINAL,
        )

        guardrail_out_agent = create_agent(
            model=llm_fast,
            system_prompt=GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL,
        )

        self.guardrail = Guardrail(guardrail_in_agent, guardrail_out_agent, self.repository, self.logger)

        # initializes the state graph
        new_graph = StateGraph(State)

        new_graph.set_entry_point(AgentName.GUARDRAIL_IN)

        new_graph.add_node(AgentName.GUARDRAIL_IN, self.guardrail.guardrail_in_func)
        new_graph.add_node(AgentName.ORCHESTRATOR, make_orchestrator_func(orchestrator_agent))
        new_graph.add_node(AgentName.PREDICT_MODEL, make_predict_model_func(predict_model_agent))
        new_graph.add_node(AgentName.REPORT_AGENT, make_report_func(report_agent))
        new_graph.add_node(AgentName.FAQ_AGENT, self.faq.faq_func)
        new_graph.add_node(AgentName.FORMATTER_AGENT, make_formatter_func(formatter_agent))
        new_graph.add_node(AgentName.JUDGE_AGENT, make_judge_func(judge_agent))
        new_graph.add_node(AgentName.GUARDRAIL_OUT, self.guardrail.guardrail_out_func)

        new_graph.add_conditional_edges(
            AgentName.GUARDRAIL_IN,

            self.guardrail.guardrail_in_fate_decision,
            {
                AgentName.ORCHESTRATOR: AgentName.ORCHESTRATOR,
                AgentName.END: AgentName.END,
            }
        )

        new_graph.add_conditional_edges(
            AgentName.ORCHESTRATOR,

            orchestrator_fate_decision,
            {
                AgentName.PREDICT_MODEL: AgentName.PREDICT_MODEL,
                AgentName.REPORT_AGENT: AgentName.REPORT_AGENT,
                AgentName.FAQ_AGENT: AgentName.FAQ_AGENT,
                AgentName.END: AgentName.END,
            }
        )

        new_graph.add_edge(AgentName.PREDICT_MODEL, AgentName.FORMATTER_AGENT)
        new_graph.add_edge(AgentName.REPORT_AGENT, AgentName.FORMATTER_AGENT)
        new_graph.add_edge(AgentName.FAQ_AGENT, AgentName.FORMATTER_AGENT)

        new_graph.add_edge(AgentName.FORMATTER_AGENT, AgentName.JUDGE_AGENT)

        new_graph.add_conditional_edges(
            AgentName.JUDGE_AGENT,

            judge_fate_decision,
            {
                AgentName.ORCHESTRATOR: AgentName.ORCHESTRATOR,
                AgentName.GUARDRAIL_OUT: AgentName.GUARDRAIL_OUT,
            }
        )

        new_graph.add_edge(AgentName.GUARDRAIL_OUT, AgentName.END)

        self.graph = new_graph

        memory = MemorySaver()
        self.__compiled_graph = new_graph.compile(checkpointer=memory)

    async def process_message(self, message: str, user_id: UUID, thread_id: UUID) -> AgentResponse:
        # certifies that the graph is already compiled
        if self.__compiled_graph is None:
            self.logger.Error("The multi-agent service is not set up. Please call the setup() method before processing messages.", MultiAgentServiceNotSetupException)
            raise MultiAgentServiceNotSetupException("The multi-agent service is not set up. Please call the setup() method before processing messages.")
        
        # initial state merges the last state from memory saver with the new one.
        # the merge works in this way: if the value contains a reducer, it will be reduced with the new value, otherwise it will be replaced by the new value.
        # we clear most of the values from the last state because they are procedural informations from each execution of the graph.
        initial_state = cast(
            State,
            {
                "messages": [HumanMessage(content=message)],
                "called_agents": [],

                # routing
                "next_agent": None,
                "intent": None,

                # guardrails
                "blocked": False,
                "blocked_reason": None,
                "current_request": None,

                # faq_agent
                "answer": None,
                "sources": [],

                # report_agent
                "report_html": None,

                # predict_model
                "predictions": [],

                # formatter_agent
                "formatted_response": None,

                # judge_agent
                "approved": None,
                "discrepancy": None,
                "judge_attempts": 0,

                # guardrail_out
                "final_response": None,
            },
        )
        
        # executes the graph with the initial state and the user_id and thread_id as configurable parameters to get the last state of the graph.
        # invoke() also retreives the last state from the memory saver and merges it with the initial state, so we can get the last state of the graph.
        
        self.logger.Info(f"Processing message for user_id: {user_id}, thread_id: {thread_id}")
        
        end_state = await self.__compiled_graph.ainvoke(
            initial_state,
            config = {
                "configurable": {
                    "user_id": user_id,
                    "thread_id": thread_id
                }
            }
        )
        
        # the flow only leaves guardrail_in when blocked=False there; if blocked=True and
        # formatted_response was never set, the flow stopped at guardrail_in, so we don't
        # save a final message for it.
        stopped_at_guardrail_in = end_state["blocked"] and end_state.get("formatted_response") is None

        if not stopped_at_guardrail_in:
            
            self.logger.Info(f"Saving message for user_id: {user_id}, thread_id: {thread_id}, content: {end_state['final_response'] or end_state['blocked_reason'] or ''}")
            
            self.repository.save_message(
                Message(
                    user_id=user_id,
                    thread_id=thread_id,
                    role=Role.ASSISTANT,
                    content=end_state["final_response"] or end_state["blocked_reason"] or "",
                    agent=AgentName.GUARDRAIL_OUT,
                    created_at=datetime.now(timezone.utc),
                )
            )
            
        # the report agent may have generated a report, so we save it to the repository if it exists.
        # we see if the report is generated by checking if report_html is not None and if the report_agent is inside the called_agents list

        report_url: str | None = None

        if end_state["report_html"] is not None and AgentName.REPORT_AGENT in end_state["called_agents"]:
            self.logger.Info(f"Saving report for user_id: {user_id}, thread_id: {thread_id}")
            try:
                pdf_bytes = self.pdf_renderer.render(end_state["report_html"])
                report_url = self.storage_service.upload(
                    content=pdf_bytes,
                    filename=f"{uuid4()}.pdf",
                    content_type="application/pdf",
                )
            except StorageServiceException as e:
                self.logger.Error(f"Failed to save report for user_id: {user_id}, thread_id: {thread_id}", e)

            # TODO: we should save the report_url to the database, but we need to think more about how to do it and how to integrate with ms-inventory. For now, we just return the report_url to the caller, and they can decide what to do with it.



        self.logger.Info(f"Finished processing message for user_id: {user_id}, thread_id: {thread_id}")

        return AgentResponse(
            content = end_state["final_response"] or end_state["blocked_reason"] or "",
            blocked = end_state["blocked"],
            blocked_reason = end_state["blocked_reason"],
            agent_trace = end_state["called_agents"],
            report_url = report_url,
        )

