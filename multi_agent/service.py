from typing import cast

from langchain.messages import HumanMessage

from multi_agent.multi_agent import IMultiAgentRepository, IMultiAgentService

from .entity import Message, AgentResponse, State, Role
from uuid import UUID
from datetime import datetime, timezone

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from config.environments import Environments
from logger.logger import logger

# completed prompts
from .prompt.guardrail_in import GUARDRAIL_IN_SYSTEM_PROMPT_FINAL
from .prompt.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT_FINAL
from .prompt.predict_model import PREDICT_MODEL_SYSTEM_PROMPT_FINAL
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

    def __init__(self, repository: IMultiAgentRepository, envs: Environments, logger: logger):
        self.repository = repository
        self.envs = envs
        self.logger = logger

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
        )

        # uses groq as fallback if gemini is not available
        llm_groq = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            api_key=SecretStr(self.envs.GROQ_API_KEY) if self.envs.GROQ_API_KEY else None,
        )
        
        # we just use cast here to hide the type error, but in run time this should not be a problem
        llm = cast(BaseChatModel, llm_gemini.with_fallbacks([llm_groq]))
        
        llm_fast = ChatGoogleGenerativeAI(
            model = "gemini-3.1-flash-lite",
            temperature = 0.2,
            top_p = 0.9,
            api_key = api_key,
        )

        # initializes the system agents
        guardrail_in_agent = create_agent(
            model=llm_fast,
            system_prompt=GUARDRAIL_IN_SYSTEM_PROMPT_FINAL,
        )

        orchestrator_agent = create_agent(
            model=llm_fast,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT_FINAL,
        )

        predict_model_agent = create_agent(
            model=llm,
            system_prompt=PREDICT_MODEL_SYSTEM_PROMPT_FINAL,
        )

        report_agent = create_agent(
            model=llm,
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

    def process_message(self, message: str, user_id: UUID, thread_id: UUID) -> AgentResponse:
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
                "report_header": None,
                "report_body": None,
                "report_footer": None,

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
        
        end_state = self.__compiled_graph.invoke(
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
            
        self.logger.Info(f"Finished processing message for user_id: {user_id}, thread_id: {thread_id}")

        return AgentResponse(
            content = end_state["final_response"] or end_state["blocked_reason"] or "",
            blocked = end_state["blocked"],
            blocked_reason = end_state["blocked_reason"],
            agent_trace = end_state["called_agents"],
        )

