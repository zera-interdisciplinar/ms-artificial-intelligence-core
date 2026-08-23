from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, PredictionItem, GraphNodeFunc
from .message_utils import parse_json_message
from logger.logger import Logger

# module-level logger instance
_logger = Logger()


def make_predict_model_func(predict_model_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps predict_model_agent so its JSON output is parsed and projected into predictions.
    """

    def predict_model_func(state: State) -> dict[str, Any]:
        response = predict_model_agent.invoke({"messages": state["current_request"]})
        _logger.Info("Predict model agent invoked")

        _logger.Debug(f"Predict model raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Predict model classification={classification}")

        predictions: list[PredictionItem] = [PredictionItem(**item) for item in classification["predictions"]]

        return {
            "called_agents": [AgentName.PREDICT_MODEL],
            "predictions": predictions,
        }

    return predict_model_func
