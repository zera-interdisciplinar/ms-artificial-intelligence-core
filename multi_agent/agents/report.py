from ..entity import State, AgentName
from .message_utils import parse_json_message
from logger.logger import logger

# module-level logger instance
_logger = logger()


def make_report_func(report_agent):
    """
    Wraps report_agent so its JSON output is parsed and projected into report_html.
    """

    def report_func(state: State) -> dict:
        response = report_agent.invoke({"messages": state["messages"]})
        _logger.Info("Report agent invoked")

        _logger.Debug(f"Report raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Report classification={classification}")

        return {
            "called_agents": [AgentName.REPORT_AGENT],
            "report_html": classification["report_html"],
        }

    return report_func
