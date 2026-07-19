import json

from entity import State


def make_faq_func(faq_agent):
    """
    Wraps faq_agent so its JSON output is parsed and projected into answer/sources.
    """

    def faq_func(state: State) -> dict:
        response = faq_agent.invoke({"messages": state["messages"]})

        formated_response = json.loads(response["messages"][-1].content)

        return {
            "answer": formated_response["answer"],
            "sources": formated_response["sources"],
        }

    return faq_func
