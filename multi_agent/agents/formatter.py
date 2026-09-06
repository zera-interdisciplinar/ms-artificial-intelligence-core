import json
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from .message_utils import parse_json_message
from langchain.messages import HumanMessage
from logger.logger import Logger

# module-level logger instance
_logger = Logger()


def make_formatter_func(formatter_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps formatter_agent so its JSON output is parsed and projected into formatted_response.
    """

    async def formatter_func(state: State) -> dict[str, Any]:
        source_state: dict[str, Any] = {
            key: state.get(key)
            for key in (
                "answer",
                "sources",
                "report_html",
                "predictions",
                "inventory_answer",
            )
            if state.get(key) not in (None, [], "")
        }
        predictions = state.get("predictions")
        if predictions:
            source_state["predictions"] = [p.model_dump() for p in predictions]
        if state.get("user_preferences"):
            source_state["user_preferences"] = state["user_preferences"]
        _logger.Debug(f"Formatter input state={source_state}")

        response = await formatter_agent.ainvoke(
            {"messages": [HumanMessage(content=json.dumps(source_state))]}
        )
        _logger.Info("Formatter agent invoked")

        _logger.Debug(f"Formatter raw response={response['messages'][-1].content}")
        formated_response = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Formatter formatted_response={formated_response}")

        return {
            "called_agents": [AgentName.FORMATTER_AGENT],
            "formatted_response": formated_response["formatted_response"],
        }

    return formatter_func
