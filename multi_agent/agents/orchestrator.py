from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from .message_utils import parse_json_message, render_history, with_preferences
from logger.logger import Logger

# module-level logger instance
_logger = Logger()

# how many recent Human/AI turns to give the orchestrator so it can resolve
# conversational references ("esse aí", "quanto custaria isso") into a
# self-contained request for the downstream (history-less) specialist agents.
HISTORY_MESSAGES_LIMIT = 6

def make_orchestrator_func(orchestrator_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps orchestrator_agent so its JSON output is parsed and projected into intent/next_agent.
    """

    async def orchestrator_func(state: State) -> dict[str, Any]:
        # state["messages"][-1] is this turn's own (already anonymized) request,
        # added by guardrail_in; history is everything before it.
        history = render_history(state["messages"][:-1], limit=HISTORY_MESSAGES_LIMIT)
        current_request = state["current_request"]
        request = with_preferences(current_request, state.get("user_preferences"))
        if history:
            request = f"[Histórico recente da conversa:\n{history}]\n\n{request}"

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
            # self-contained request, with conversational references (if any) already
            # resolved by the orchestrator; downstream agents never see message history.
            "current_request": classification.get("resolved_request") or current_request,
        }

        if next_agent == AgentName.END:
            # unclassified intent still leaves through guardrail_out, like every other
            # answer, so the suggestion goes through the same PII/safety check.
            result["formatted_response"] = classification["suggestion"]

        return result

    return orchestrator_func


def orchestrator_fate_decision(state: State) -> str:
    """
    Function to determine the fate of the orchestrator state.
    """
    next_agent = state['next_agent'] if state['next_agent'] is not None else AgentName.END
    _logger.Debug(f"Orchestrator fate decision: next_agent={next_agent}")
    return next_agent