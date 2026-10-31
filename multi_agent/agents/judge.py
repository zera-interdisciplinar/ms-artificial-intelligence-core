import json
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ..entity import State, AgentName, GraphNodeFunc
from .message_utils import parse_json_message
from langchain.messages import HumanMessage
from logger.logger import Logger

# module-level logger instance
_logger = Logger()

# total number of judge_agent evaluations allowed per user message: 1 execution + 1 retry.
MAX_JUDGE_ATTEMPTS: int = 2


def make_judge_func(judge_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps judge_agent so its JSON output is parsed and projected into approved/discrepancy.
    When the response is not approved and there are attempts left, resets the routing
    fields; the orchestrator reads `discrepancy` on the next attempt and carries it
    into the request, so it never lands in the persisted message history.
    """

    async def judge_func(state: State) -> dict[str, Any]:
        request = state["current_request"]
        _logger.Debug(f"Judge: request preview={request}")

        response = await judge_agent.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=json.dumps(
                            {
                                "request": request,
                                "formatted_response": state["formatted_response"],
                                **_specialist_output(state),
                            }
                        )
                    )
                ]
            }
        )
        _logger.Info("Judge agent invoked")
        _logger.Debug(f"Judge raw response={response['messages'][-1].content}")

        classification = parse_json_message(response["messages"][-1].content, "approved", "discrepancy")
        _logger.Debug(f"Judge classification={classification}")
        approved = classification["approved"]
        discrepancy = classification["discrepancy"]

        attempts_done = state.get("judge_attempts", 0) + 1 # this func is also a attempt, so we increment the attempts done by 1

        result: dict[str, Any] = {
            "called_agents": [AgentName.JUDGE_AGENT],
            "approved": approved,
            "discrepancy": discrepancy,
            "judge_attempts": 1, # this is the first attempt, so we set it to 1. If there are more attempts, it will be incremented in the next call
        }

        # a rejection with no discrepancy cannot be corrected; shipping the last answer
        # is safer than a blind second pass
        will_retry = not approved and bool(discrepancy) and attempts_done < MAX_JUDGE_ATTEMPTS

        if will_retry:
            _logger.Warning(f"Judge: will retry due to discrepancy={discrepancy}")
            result.update({
                "next_agent": None,
                "intent": None,
                # the next specialist must not inherit this attempt's output
                "answer": None,
                "sources": [],
                "report_html": None,
                "predictions": [],
                "inventory_answer": None,
                "redirect_to": None,
                "formatted_response": None,
            })

        return result

    return judge_func


def _specialist_output(state: State) -> dict[str, Any]:
    """This turn's specialist fields. History stays out: a reply that only matches
    an older turn would look coherent."""

    payload: dict[str, Any] = {}
    for key in ("answer", "sources", "report_html", "inventory_answer"):
        value = state.get(key)
        if value not in (None, [], ""):
            payload[key] = value
    predictions = state.get("predictions")
    if predictions:
        payload["predictions"] = [item.model_dump() for item in predictions]
    return payload


def judge_fate_decision(state: State) -> str:
    """
    Function to decide the next agent based on the judge_agent's decision and the number of attempts done.
    If the response is approved, it goes to guardrail_out. If not approved, a discrepancy
    was recorded and there are attempts left, it goes back to orchestrator. Otherwise it
    goes to guardrail_out and the flow finishes with the last response generated.
    """
    if state["approved"]:
        return AgentName.GUARDRAIL_OUT

    if state["judge_attempts"] < MAX_JUDGE_ATTEMPTS and state.get("discrepancy"):
        return AgentName.ORCHESTRATOR

    return AgentName.GUARDRAIL_OUT
