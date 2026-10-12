from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from ..unit_scope import set_unit_id
from .message_utils import parse_json_message, request_with_history
from .report_template import render_quote_report
from logger.logger import Logger

# module-level logger instance
_logger = Logger()


def make_report_func(report_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps report_agent so its JSON output is parsed and projected into report_html.
    """

    async def report_func(state: State) -> dict[str, Any]:
        set_unit_id(state.get("unit_id"))
        request = request_with_history(
            state["current_request"], state.get("messages"), state.get("user_preferences")
        )
        response = await report_agent.ainvoke({"messages": request})
        _logger.Info("Report agent invoked")

        _logger.Debug(f"Report raw response={response['messages'][-1].content}")
        data = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Report data={data}")

        return {
            "called_agents": [AgentName.REPORT_AGENT],
            "report_html": render_quote_report(data if isinstance(data, dict) else {}),
        }

    return report_func
