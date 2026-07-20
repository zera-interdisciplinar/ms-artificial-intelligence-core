import json

from ..entity import State
from logger.logger import logger

# module-level logger instance
_logger = logger()


def make_formatter_func(formatter_agent):
    """
    Wraps formatter_agent so its JSON output is parsed and projected into formatted_response.
    """

    def formatter_func(state: State) -> dict:
        response = formatter_agent.invoke({"messages": state["messages"]})
        _logger.Info("Formatter agent invoked")

        _logger.Debug(f"Formatter raw response={response['messages'][-1].content}")
        formated_response = json.loads(response["messages"][-1].content)
        _logger.Debug(f"Formatter formatted_response={formated_response}")

        return {
            "formatted_response": formated_response["formatted_response"],
        }

    return formatter_func
