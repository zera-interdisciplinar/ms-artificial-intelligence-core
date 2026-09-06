from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from ..unit_scope import set_unit_id
from .message_utils import parse_json_message, with_preferences
from logger.logger import Logger

# module-level logger instance
_logger = Logger()


def make_inventory_func(inventory_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps inventory_agent so its JSON output is parsed and projected into
    inventory_answer. The agent itself decides which ms-inventory MCP tool(s)
    to call — this wrapper only
    parses the final structured response, it does not touch the MCP tools.

    It does not contains the adm core request, which is done in the multi-agent service before calling this function.
    """

    async def inventory_func(state: State) -> dict[str, Any]:
        set_unit_id(state.get("unit_id"))
        request = with_preferences(state["current_request"], state.get("user_preferences"))
        response = await inventory_agent.ainvoke({"messages": request})
        _logger.Info("Inventory agent invoked")

        _logger.Debug(f"Inventory raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Inventory classification={classification}")

        result: dict[str, Any] = {
            "called_agents": [AgentName.INVENTORY_AGENT],
            "inventory_answer": classification["answer"],
        }

        pending_agent = state.get("pending_agent")
        if pending_agent:
            #  in this case, orchestrator routed here first only to fetch item detail missing
            # from the original request; resume with the pending agent, now
            # armed with that detail, instead of going straight to formatter.
            result["next_agent"] = pending_agent
            result["current_request"] = (
                f"{state.get('pending_request')}\n\n"
                f"[Dados do inventário:\n{classification['answer']}]"
            )
            result["pending_agent"] = None
            result["pending_request"] = None
        else:
            # overwrites the stale next_agent left by the orchestrator (its own
            # routing target, "inventory_agent"), which isn't a valid edge here.
            result["next_agent"] = AgentName.FORMATTER_AGENT

        return result

    return inventory_func


def inventory_fate_decision(state: State) -> str:
    """Resumes with pending_agent (e.g. predict_model) when inventory_agent was
    called only to fetch detail missing from that agent's request; otherwise
    inventory_agent's answer is final and goes straight to formatter."""
    return state["next_agent"]
