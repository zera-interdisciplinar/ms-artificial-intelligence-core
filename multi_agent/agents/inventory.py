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

        return {
            "called_agents": [AgentName.INVENTORY_AGENT],
            "inventory_answer": classification["answer"],
        }

    return inventory_func
