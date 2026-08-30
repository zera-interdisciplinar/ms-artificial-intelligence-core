from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from .message_utils import parse_json_message, with_preferences
from logger.logger import Logger

# module-level logger instance
_logger = Logger()

def make_orchestrator_func(orchestrator_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps orchestrator_agent so its JSON output is parsed and projected into intent/next_agent.
    """

    async def orchestrator_func(state: State) -> dict[str, Any]:
        request = with_preferences(state["current_request"], state.get("user_preferences"))
        response = await orchestrator_agent.ainvoke({"messages": request})
        _logger.Info("Orchestrator agent invoked")

        _logger.Debug(f"Orchestrator raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Orchestrator classification={classification}")

        next_agent = classification["next_agent"]

        result: dict[str, Any] = {
            "called_agents": [AgentName.ORCHESTRATOR],
            "intent": classification["intent"],
            "next_agent": next_agent,
        }

        if next_agent == AgentName.END:
            result["final_response"] = classification["suggestion"]
            result["blocked"] = True
            result["blocked_reason"] = "unclassified_intent"

        return result

    return orchestrator_func


def orchestrator_fate_decision(state: State) -> str:
    """
    Function to determine the fate of the orchestrator state.
    """
    next_agent = state['next_agent'] if state['next_agent'] is not None else AgentName.END
    _logger.Debug(f"Orchestrator fate decision: next_agent={next_agent}")
    return next_agent