import json

from ..entity import State
from logger.logger import logger

# module-level logger instance
_logger = logger()


def make_report_func(report_agent):
    """
    Wraps report_agent so its JSON output is parsed and projected into report_header/report_body/report_footer.
    """

    def report_func(state: State) -> dict:
        response = report_agent.invoke({"messages": state["messages"]})
        _logger.Info("Report agent invoked")

        _logger.Debug(f"Report raw response={response['messages'][-1].content}")
        classification = json.loads(response["messages"][-1].content)
        _logger.Debug(f"Report classification={classification}")

        return {
            "report_header": classification["report_header"],
            "report_body": classification["report_body"],
            "report_footer": classification["report_footer"],
        }

    return report_func
