from typing import Protocol, runtime_checkable, cast

from langchain.messages import HumanMessage

from multi_agent.multi_agent import IMultiAgentRepository, IMultiAgentService

from .entity import Message, AgentResponse, State
from uuid import UUID

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from config.environments import Environments
from logger.logger import logger

# completed prompts
from prompt.guardrail_in import GUARDRAIL_IN_SYSTEM_PROMPT_FINAL
from prompt.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT_FINAL
from prompt.predict_model import PREDICT_MODEL_SYSTEM_PROMPT_FINAL
from prompt.report_agent import REPORT_AGENT_SYSTEM_PROMPT_FINAL
from prompt.faq_agent import FAQ_AGENT_SYSTEM_PROMPT_FINAL
from prompt.formatter_agent import FORMATTER_AGENT_SYSTEM_PROMPT_FINAL
from prompt.judge_agent import JUDGE_AGENT_SYSTEM_PROMPT_FINAL
from prompt.guardrail_out import GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL

# checkpointer
from langgraph.checkpoint.memory import MemorySaver

#langchain/langgraph imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent

# state
from .entity import State

# agents imports
from entity import AgentName

from agents.guardrail import Guardrail
from agents.orchestrator import orchestrator_fate_decision

# exceptions
from exception import MultiAgentServiceNotSetupException

from typing import Optional

class MultiAgentService(IMultiAgentService):
    """Concrete implementation of the multi-agent service."""

    graph: StateGraph[State]
    __compiled_graph: Optional[CompiledStateGraph[State]] = None
    guardrail: Guardrail

    def __init__(self, repository: IMultiAgentRepository, envs: Environments, logger: logger):
        self.repository = repository
        self.envs = envs
        self.logger = logger

    def setup(self, repository: IMultiAgentRepository) -> None:
        """
        Setup the MultiAgentService with the provided repository.
        """
        self.logger.Info("Setting up the multi-agent service")

        # initializes the model
        self.logger.Info("initializing the gemini llm")
        llm_gemini = ChatGoogleGenerativeAI(
            model = "gemini-2.5-flash",
            temperature = 0.2,
            top_p = 0.9,
            google_api_key = self.envs.GEMINI_API_KEY,
        )

        # initializes the system agents
        guardrail_in_agent = create_agent(
            model=llm_gemini,
            system_prompt=GUARDRAIL_IN_SYSTEM_PROMPT_FINAL,
        )

        orchestrator_agent = create_agent(
            model=llm_gemini,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT_FINAL,
        )

        predict_model_agent = create_agent(
            model=llm_gemini,
            system_prompt=PREDICT_MODEL_SYSTEM_PROMPT_FINAL,
        )

        report_agent = create_agent(
            model=llm_gemini,
            system_prompt=REPORT_AGENT_SYSTEM_PROMPT_FINAL,
        )

        faq_agent = create_agent(
            model=llm_gemini,
            system_prompt=FAQ_AGENT_SYSTEM_PROMPT_FINAL,
        )

        formatter_agent = create_agent(
            model=llm_gemini,
            system_prompt=FORMATTER_AGENT_SYSTEM_PROMPT_FINAL,
        )

        judge_agent = create_agent(
            model=llm_gemini,
            system_prompt=JUDGE_AGENT_SYSTEM_PROMPT_FINAL,
        )

        guardrail_out_agent = create_agent(
            model=llm_gemini,
            system_prompt=GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL,
        )

        self.guardrail = Guardrail(guardrail_in_agent, guardrail_out_agent)

        # initializes the state graph
        new_graph = StateGraph(State)

        new_graph.set_entry_point(AgentName.GUARDRAIL_IN)

        new_graph.add_node(AgentName.GUARDRAIL_IN, self.guardrail.guardrail_in_func)
        new_graph.add_node(AgentName.ORCHESTRATOR, orchestrator_agent)
        new_graph.add_node(AgentName.PREDICT_MODEL, predict_model_agent)
        new_graph.add_node(AgentName.REPORT_AGENT, report_agent)
        new_graph.add_node(AgentName.FAQ_AGENT, faq_agent)
        new_graph.add_node(AgentName.FORMATTER_AGENT, formatter_agent)
        new_graph.add_node(AgentName.JUDGE_AGENT, judge_agent)
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
            }
        )

        new_graph.add_edge(AgentName.PREDICT_MODEL, AgentName.FORMATTER_AGENT)
        new_graph.add_edge(AgentName.REPORT_AGENT, AgentName.FORMATTER_AGENT)
        new_graph.add_edge(AgentName.FAQ_AGENT, AgentName.FORMATTER_AGENT)

        new_graph.add_edge(AgentName.FORMATTER_AGENT, AgentName.JUDGE_AGENT)
        new_graph.add_edge(AgentName.JUDGE_AGENT, AgentName.GUARDRAIL_OUT)
        new_graph.add_edge(AgentName.GUARDRAIL_OUT, AgentName.END)

        self.graph = new_graph

        memory = MemorySaver()
        self.__compiled_graph = new_graph.compile(checkpointer=memory)

    def process_message(self, message: str, user_id: UUID, thread_id: UUID) -> AgentResponse:
        # certifies that the graph is already compiled
        if self.__compiled_graph is None:
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

                # guardrail_out
                "final_response": None,
            },
        )
        
        # executes the graph with the initial state and the user_id and thread_id as configurable parameters to get the last state of the graph.
        # invoke() also retreives the last state from the memory saver and merges it with the initial state, so we can get the last state of the graph.
        end_state = self.__compiled_graph.invoke(
            initial_state,
            config = {
                "configurable": {
                    "user_id": user_id,
                    "thread_id": thread_id
                }
            }
        )
        

        return AgentResponse(
            content = end_state["final_response"],
            blocked = end_state["blocked"],
            blocked_reason = end_state["blocked_reason"],
            agent_trace = end_state["called_agents"],
        )

