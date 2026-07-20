import json

from ..entity import State
from logger.logger import logger

# module-level logger instance
_logger = logger()


def make_faq_func(faq_agent):
    """
    Wraps faq_agent so its JSON output is parsed and projected into answer/sources.
    """

    def faq_func(state: State) -> dict:
        response = faq_agent.invoke({"messages": state["messages"]})
        _logger.Info("FAQ agent invoked")

        _logger.Debug(f"FAQ raw response={response['messages'][-1].content}")
        formated_response = json.loads(response["messages"][-1].content)
        _logger.Debug(f"FAQ formatted response={formated_response}")

        return {
            "answer": formated_response["answer"],
            "sources": formated_response["sources"],
        }

    return faq_func
