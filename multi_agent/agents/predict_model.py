from ..entity import State, AgentName
from .message_utils import parse_json_message
from logger.logger import logger

# module-level logger instance
_logger = logger()


def make_predict_model_func(predict_model_agent):
    """
    Wraps predict_model_agent so its JSON output is parsed and projected into predictions.
    """

    def predict_model_func(state: State) -> dict:
        response = predict_model_agent.invoke({"messages": state["messages"]})
        _logger.Info("Predict model agent invoked")

        _logger.Debug(f"Predict model raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Predict model classification={classification}")

        return {
            "called_agents": [AgentName.PREDICT_MODEL],
            "predictions": classification["predictions"],
        }

    return predict_model_func
