from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from .message_utils import parse_json_message, with_preferences
from logger.logger import Logger

# module-level logger instance
_logger = Logger()


def make_report_func(report_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps report_agent so its JSON output is parsed and projected into report_html.
    """

    async def report_func(state: State) -> dict[str, Any]:
        request = with_preferences(state["current_request"], state.get("user_preferences"))
        response = await report_agent.ainvoke({"messages": request})
        _logger.Info("Report agent invoked")

        _logger.Debug(f"Report raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Report classification={classification}")

        return {
            "called_agents": [AgentName.REPORT_AGENT],
            "report_html": classification["report_html"],
        }

    return report_func
