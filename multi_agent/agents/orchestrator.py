from ..entity import State, AgentName
from .message_utils import parse_json_message
from logger.logger import logger

# module-level logger instance
_logger = logger()

UNCLASSIFIED_INTENT_MESSAGE = (
    "Não consegui identificar sua solicitação. Poderia reformular sua pergunta "
    "com mais detalhes sobre o que você precisa?"
)


def make_orchestrator_func(orchestrator_agent):
    """
    Wraps orchestrator_agent so its JSON output is parsed and projected into intent/next_agent.
    """

    def orchestrator_func(state: State) -> dict:
        response = orchestrator_agent.invoke({"messages": state["current_request"]})
        _logger.Info("Orchestrator agent invoked")

        _logger.Debug(f"Orchestrator raw response={response['messages'][-1].content}")
        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Orchestrator classification={classification}")

        next_agent = classification["next_agent"]

        result: dict = {
            "called_agents": [AgentName.ORCHESTRATOR],
            "intent": classification["intent"],
            "next_agent": next_agent,
        }

        if next_agent == AgentName.END:
            result["final_response"] = UNCLASSIFIED_INTENT_MESSAGE

        return result

    return orchestrator_func


def orchestrator_fate_decision(state: State) -> str:
    """
    Function to determine the fate of the orchestrator state.
    """
    next_agent = state['next_agent'] if state['next_agent'] is not None else AgentName.END
    _logger.Debug(f"Orchestrator fate decision: next_agent={next_agent}")
    return next_agent