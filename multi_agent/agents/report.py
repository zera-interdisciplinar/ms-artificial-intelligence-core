import json

from entity import State


def make_report_func(report_agent):
    """
    Wraps report_agent so its JSON output is parsed and projected into report_header/report_body/report_footer.
    """

    def report_func(state: State) -> dict:
        response = report_agent.invoke({"messages": state["messages"]})

        classification = json.loads(response["messages"][-1].content)

        return {
            "report_header": classification["report_header"],
            "report_body": classification["report_body"],
            "report_footer": classification["report_footer"],
        }

    return report_func
