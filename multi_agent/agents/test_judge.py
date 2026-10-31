import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from langchain.messages import HumanMessage

from multi_agent.entity import AgentName, PredictionItem, State
from multi_agent.agents.judge import MAX_JUDGE_ATTEMPTS, make_judge_func, judge_fate_decision


def _state(**overrides) -> State:
    state = {
        "messages": [HumanMessage(content="quais perfis existem?")],
        "current_request": "quais perfis existem?",
        "formatted_response": "três perfis",
        "judge_attempts": 0,
    }
    state.update(overrides)
    return cast(State, state)


class TestJudgeFateDecision:
    def test_routes_to_guardrail_out_when_approved(self):
        state = cast(State, {"approved": True, "judge_attempts": 1})

        assert judge_fate_decision(state) == AgentName.GUARDRAIL_OUT

    def test_routes_to_orchestrator_when_not_approved_and_attempts_remain(self):
        state = cast(State, {"approved": False, "judge_attempts": 1, "discrepancy": "response_omits_data"})

        assert judge_fate_decision(state) == AgentName.ORCHESTRATOR
        assert MAX_JUDGE_ATTEMPTS > 1

    def test_routes_to_guardrail_out_when_not_approved_and_attempts_exhausted(self):
        state = cast(State, {"approved": False, "judge_attempts": MAX_JUDGE_ATTEMPTS, "discrepancy": "x"})

        assert judge_fate_decision(state) == AgentName.GUARDRAIL_OUT

    def test_routes_to_guardrail_out_when_rejected_without_discrepancy(self):
        state = cast(State, {"approved": False, "judge_attempts": 1, "discrepancy": None})

        assert judge_fate_decision(state) == AgentName.GUARDRAIL_OUT


class TestJudgeFunc:
    def test_increments_judge_attempts(self):
        judge_agent = MagicMock()
        judge_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"approved": True, "discrepancy": None}))]
        })
        judge_func = make_judge_func(judge_agent)

        result = asyncio.run(judge_func(_state()))

        assert result["judge_attempts"] == 1
        assert result["approved"] is True

    def test_keeps_formatted_response_when_approved(self):
        judge_agent = MagicMock()
        judge_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"approved": True, "discrepancy": None}))]
        })
        judge_func = make_judge_func(judge_agent)

        result = asyncio.run(judge_func(_state()))

        assert "formatted_response" not in result

    def test_resets_downstream_fields_when_rejected_with_attempts_left(self):
        judge_agent = MagicMock()
        judge_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"approved": False, "discrepancy": "response_omits_data"}
                    )
                )
            ]
        })
        judge_func = make_judge_func(judge_agent)

        result = asyncio.run(judge_func(_state(judge_attempts=0)))

        assert result["approved"] is False
        assert result["discrepancy"] == "response_omits_data"
        assert result["next_agent"] is None
        assert result["intent"] is None
        assert result["answer"] is None
        assert result["sources"] == []
        assert result["report_html"] is None
        assert result["predictions"] == []
        assert result["inventory_answer"] is None
        assert result["redirect_to"] is None
        assert result["formatted_response"] is None
        # the reason travels through state["discrepancy"], never the persisted history
        assert "messages" not in result

    def test_sends_this_turn_specialist_output_and_not_the_history(self):
        judge_agent = MagicMock()
        judge_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"approved": True, "discrepancy": None}))]
        })
        judge_func = make_judge_func(judge_agent)

        asyncio.run(judge_func(_state(
            messages=[
                HumanMessage(content="turno antigo"),
                HumanMessage(content="quais perfis existem?"),
            ],
            predictions=[
                PredictionItem(
                    item="Notebook",
                    estimated_remaining_months=8,
                    adjusted=False,
                    adjustment_reason=None,
                )
            ],
        )))

        sent = json.loads(judge_agent.ainvoke.call_args[0][0]["messages"][0].content)
        assert sent["request"] == "quais perfis existem?"
        assert sent["formatted_response"] == "três perfis"
        assert sent["predictions"][0]["estimated_remaining_months"] == 8
        assert "turno antigo" not in judge_agent.ainvoke.call_args[0][0]["messages"][0].content

    def test_does_not_clear_fields_when_rejected_without_discrepancy(self):
        judge_agent = MagicMock()
        judge_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"approved": False, "discrepancy": None}))]
        })
        judge_func = make_judge_func(judge_agent)

        result = asyncio.run(judge_func(_state(judge_attempts=0)))

        assert result["approved"] is False
        assert "formatted_response" not in result
        assert "answer" not in result

    def test_does_not_reset_fields_when_rejected_and_attempts_exhausted(self):
        judge_agent = MagicMock()
        judge_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"approved": False, "discrepancy": "response_omits_data"}
                    )
                )
            ]
        })
        judge_func = make_judge_func(judge_agent)

        result = asyncio.run(judge_func(_state(judge_attempts=MAX_JUDGE_ATTEMPTS - 1)))

        assert result["approved"] is False
        assert "formatted_response" not in result
        assert "messages" not in result
        assert result["judge_attempts"] == 1
