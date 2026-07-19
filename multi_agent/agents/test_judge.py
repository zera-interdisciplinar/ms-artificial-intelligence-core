import json
from unittest.mock import MagicMock

from langchain.messages import HumanMessage

from multi_agent.entity import AgentName
from multi_agent.agents.judge import MAX_JUDGE_ATTEMPTS, make_judge_func, judge_fate_decision


def _state(**overrides):
    state = {
        "messages": [HumanMessage(content="quais perfis existem?")],
        "formatted_response": "três perfis",
        "judge_attempts": 0,
    }
    state.update(overrides)
    return state


class TestJudgeFateDecision:
    def test_routes_to_guardrail_out_when_approved(self):
        state = {"approved": True, "judge_attempts": 1}

        assert judge_fate_decision(state) == AgentName.GUARDRAIL_OUT

    def test_routes_to_orchestrator_when_not_approved_and_attempts_remain(self):
        state = {"approved": False, "judge_attempts": 1}

        assert judge_fate_decision(state) == AgentName.ORCHESTRATOR
        assert MAX_JUDGE_ATTEMPTS > 1

    def test_routes_to_guardrail_out_when_not_approved_and_attempts_exhausted(self):
        state = {"approved": False, "judge_attempts": MAX_JUDGE_ATTEMPTS}

        assert judge_fate_decision(state) == AgentName.GUARDRAIL_OUT


class TestJudgeFunc:
    def test_increments_judge_attempts(self):
        judge_agent = MagicMock()
        judge_agent.invoke.return_value = {
            "messages": [MagicMock(content=json.dumps({"approved": True, "discrepancy": None}))]
        }
        judge_func = make_judge_func(judge_agent)

        result = judge_func(_state())

        assert result["judge_attempts"] == 1
        assert result["approved"] is True

    def test_keeps_formatted_response_when_approved(self):
        judge_agent = MagicMock()
        judge_agent.invoke.return_value = {
            "messages": [MagicMock(content=json.dumps({"approved": True, "discrepancy": None}))]
        }
        judge_func = make_judge_func(judge_agent)

        result = judge_func(_state())

        assert "formatted_response" not in result

    def test_resets_downstream_fields_when_rejected_with_attempts_left(self):
        judge_agent = MagicMock()
        judge_agent.invoke.return_value = {
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"approved": False, "discrepancy": "response_omits_data"}
                    )
                )
            ]
        }
        judge_func = make_judge_func(judge_agent)

        result = judge_func(_state(judge_attempts=0))

        assert result["approved"] is False
        assert result["discrepancy"] == "response_omits_data"
        assert result["formatted_response"] is None
        assert result["answer"] is None
        assert result["sources"] == []
        assert result["report_header"] is None
        assert result["predictions"] == []
        assert result["next_agent"] is None
        assert len(result["messages"]) == 1
        assert "response_omits_data" in result["messages"][0].content

    def test_does_not_reset_fields_when_rejected_and_attempts_exhausted(self):
        judge_agent = MagicMock()
        judge_agent.invoke.return_value = {
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"approved": False, "discrepancy": "response_omits_data"}
                    )
                )
            ]
        }
        judge_func = make_judge_func(judge_agent)

        result = judge_func(_state(judge_attempts=MAX_JUDGE_ATTEMPTS - 1))

        assert result["approved"] is False
        assert "formatted_response" not in result
        assert "messages" not in result
        assert result["judge_attempts"] == 1
