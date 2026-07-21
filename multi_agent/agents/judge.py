import json

from ..entity import State, AgentName
from .message_utils import parse_json_message
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from logger.logger import logger

# module-level logger instance
_logger = logger()

# total number of judge_agent evaluations allowed per user message: 1 execution + 1 retry.
MAX_JUDGE_ATTEMPTS = 2


def make_judge_func(judge_agent):
    """
    Wraps judge_agent so its JSON output is parsed and projected into approved/discrepancy.
    When the response is not approved and there are attempts left, resets the fields
    produced by the specialist/formatter agents and appends the discrepancy to the
    conversation so the next attempt (starting from orchestrator) can address it.
    """

    def judge_func(state: State) -> dict:
        request = state["messages"][0].content
        _logger.Debug(f"Judge: request preview={request}")

        response = judge_agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=json.dumps(
                            {
                                "request": request,
                                "formatted_response": state["formatted_response"],
                            }
                        )
                    )
                ]
            }
        )
        _logger.Info("Judge agent invoked")
        _logger.Debug(f"Judge raw response={response['messages'][-1].content}")

        classification = parse_json_message(response["messages"][-1].content)
        _logger.Debug(f"Judge classification={classification}")
        approved = classification["approved"]
        discrepancy = classification["discrepancy"]

        attempts_done = state.get("judge_attempts", 0) + 1 # this func is also a attempt, so we increment the attempts done by 1

        result: dict = {
            "approved": approved,
            "discrepancy": discrepancy,
            "judge_attempts": 1, # this is the first attempt, so we set it to 1. If there are more attempts, it will be incremented in the next call
        }

        will_retry = not approved and attempts_done < MAX_JUDGE_ATTEMPTS

        if will_retry:
            _logger.Warning(f"Judge: will retry due to discrepancy={discrepancy}")
            result.update(
                {
                    "next_agent": None,
                    "intent": None,
                    "answer": None,
                    "sources": [],
                    "report_header": None,
                    "report_body": None,
                    "report_footer": None,
                    "predictions": [],
                    "formatted_response": None,
                    "messages": [
                        HumanMessage(
                            content=(
                                "A resposta anterior foi reprovada pelo judge_agent pelo "
                                f"seguinte motivo: {discrepancy}. Corrija esse ponto na nova tentativa."
                            )
                        )
                    ],
                }
            )

        return result

    return judge_func


def judge_fate_decision(state: State) -> str:
    """
    Function to decide the next agent based on the judge_agent's decision and the number of attempts done.
    If the response is approved, it goes to guardrail_out. If not approved and there are attempts left, it goes back to orchestrator. If not approved and no attempts left, it goes to guardrail_out and the flow finishes with the last response generated.
    """
    if state["approved"]:
        return AgentName.GUARDRAIL_OUT

    if state["judge_attempts"] < MAX_JUDGE_ATTEMPTS:
        return AgentName.ORCHESTRATOR

    return AgentName.GUARDRAIL_OUT
