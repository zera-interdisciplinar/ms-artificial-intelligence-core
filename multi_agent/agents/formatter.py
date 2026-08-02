import json

from ..entity import State, AgentName
from .message_utils import parse_json_message
from langchain.messages import HumanMessage
from logger.logger import logger

# module-level logger instance
_logger = logger()


def make_formatter_func(formatter_agent):
    """
    Wraps formatter_agent so its JSON output is parsed and projected into formatted_response.
    """

    def formatter_func(state: State) -> dict:
        source_state = {
            key: state.get(key)
            for key in (
                "answer",
                "sources",
                "report_header",
                "report_body",
                "report_footer",
                "predictions",
            )
            if state.get(key) not in (None, [], "")
        }
        _logger.Debug(f"Formatter input state={source_state}")

        response = formatter_agent.invoke(
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
