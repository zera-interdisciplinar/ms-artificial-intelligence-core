import json

from entity import State


def make_formatter_func(formatter_agent):
    """
    Wraps formatter_agent so its JSON output is parsed and projected into formatted_response.
    """

    def formatter_func(state: State) -> dict:
        response = formatter_agent.invoke({"messages": state["messages"]})

        formated_response = json.loads(response["messages"][-1].content)

        return {
            "formatted_response": formated_response["formatted_response"],
        }

    return formatter_func
