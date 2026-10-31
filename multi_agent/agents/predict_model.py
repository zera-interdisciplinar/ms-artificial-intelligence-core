from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, PredictionItem, GraphNodeFunc
from .message_utils import parse_json_message, request_with_history
from logger.logger import Logger

# module-level logger instance
_logger = Logger()


def _remaining_months(value: Any) -> Any:
    """The tool returns a fractional month count. The state field is an int: drop the fraction toward zero (8.4 -> 8). Non-numeric values pass through so PredictionItem still fails loud."""

    if isinstance(value, bool) or not isinstance(value, (float, str)):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(float(value))
    except ValueError:
        return value


def make_predict_model_func(predict_model_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps predict_model_agent so its JSON output is parsed and projected into
    predictions. The agent itself extracts, validates/clamps and calls
    predict_time_to_failure_batch (see multi_agent/prompt/predict_model.py) —
    this wrapper only parses the final structured response, it does not touch
    the MCP tool.
    """

    async def predict_model_func(state: State) -> dict[str, Any]:
        request = request_with_history(
            state["current_request"], state.get("messages"), state.get("user_preferences")
        )
        response = await predict_model_agent.ainvoke({"messages": request})
        _logger.Info("Predict model agent invoked")

        _logger.Debug(f"Predict model raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content, "predictions")
        _logger.Debug(f"Predict model classification={classification}")

        predictions: list[PredictionItem] = [
            PredictionItem(**{**item, "estimated_remaining_months": _remaining_months(item.get("estimated_remaining_months"))})
            for item in classification["predictions"]
        ]

        return {
            "called_agents": [AgentName.PREDICT_MODEL],
            "predictions": predictions,
        }

    return predict_model_func
