from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from ..exception import AgentOutputException
from .message_utils import parse_json_message, request_with_history
from logger.logger import Logger

# module-level logger instance
_logger = Logger()

# where the orchestrator may send a request, and which agent may wait for inventory_agent's
# detail; must match the edges in graph.py (test_graph checks it), so a value outside them
# never reaches LangGraph
ROUTES: frozenset[AgentName] = frozenset({
    AgentName.FAQ_AGENT, AgentName.REPORT_AGENT, AgentName.PREDICT_MODEL, AgentName.INVENTORY_AGENT, AgentName.END,
})
PENDING_ROUTES: frozenset[AgentName] = frozenset({AgentName.PREDICT_MODEL})

def make_orchestrator_func(orchestrator_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps orchestrator_agent so its JSON output is parsed and projected into intent/next_agent.
    """

    async def orchestrator_func(state: State) -> dict[str, Any]:
        # state["messages"][-1] is this turn's own (already anonymized) request,
        # added by guardrail_in; history is everything before it.
        current_request = state["current_request"]
        assert current_request is not None, "guardrail_in sets current_request before the orchestrator runs"
        # retry after judge_agent rejected the previous answer: the reason travels with
        # the request (to routing and to the specialist), not through message history.
        retry_note = ""
        if state.get("judge_attempts") and state.get("discrepancy"):
            retry_note = (
                "\n\n[A resposta anterior foi reprovada pelo judge_agent pelo seguinte motivo: "
                f"{state['discrepancy']}. Corrija esse ponto na nova tentativa.]"
            )
        request = request_with_history(
            current_request + retry_note, state["messages"], state.get("user_preferences")
        )

        response = await orchestrator_agent.ainvoke({"messages": request})
        _logger.Info("Orchestrator agent invoked")

        _logger.Debug(f"Orchestrator raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content, "intent", "next_agent")
        _logger.Debug(f"Orchestrator classification={classification}")

        next_agent, pending_agent = _validated_routing(classification)

        result: dict[str, Any] = {
            "called_agents": [AgentName.ORCHESTRATOR],
            "intent": classification["intent"],
            "next_agent": next_agent,
            # self-contained request, with conversational references (if any) already
            # resolved by the orchestrator; downstream agents never see message history.
            "current_request": (classification.get("resolved_request") or current_request) + retry_note,
            # inventory_agent hands over to pending_agent once it has fetched the missing detail
            "pending_agent": pending_agent,
            "pending_request": classification.get("pending_request"),
        }

        if next_agent == AgentName.END:
            # unclassified intent still leaves through guardrail_out, like every other
            # answer, so the suggestion goes through the same PII/safety check.
            result["formatted_response"] = classification["suggestion"]

        return result

    return orchestrator_func


def _validated_routing(classification: dict[str, Any]) -> tuple[AgentName, AgentName | None]:
    """The LLM picks the route; anything the graph has no edge for is a bad agent output (502)."""

    raw_pending = classification.get("pending_agent")
    try:
        next_agent = AgentName(classification["next_agent"])
        pending_agent = AgentName(raw_pending) if raw_pending else None
    except ValueError as e:
        raise AgentOutputException(f"orchestrator chose an unknown agent: {classification}") from e

    if next_agent not in ROUTES or (pending_agent is not None and pending_agent not in PENDING_ROUTES):
        raise AgentOutputException(f"orchestrator chose a route the graph does not have: {classification}")
    if next_agent == AgentName.END and not classification.get("suggestion"):
        raise AgentOutputException(f"orchestrator ended the flow without a suggestion: {classification}")
    return next_agent, pending_agent


def orchestrator_fate_decision(state: State) -> str:
    """
    Function to determine the fate of the orchestrator state.
    """
    next_agent = state['next_agent'] if state['next_agent'] is not None else AgentName.END
    _logger.Debug(f"Orchestrator fate decision: next_agent={next_agent}")
    return next_agent