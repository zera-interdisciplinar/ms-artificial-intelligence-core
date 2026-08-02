from typing import cast
from unittest.mock import MagicMock

from multi_agent.entity import AgentName, State
from multi_agent.agents.orchestrator import (
    orchestrator_fate_decision,
    make_orchestrator_func,
    UNCLASSIFIED_INTENT_MESSAGE,
)
from multi_agent.prompt.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT_FINAL


class TestOrchestratorFateDecision:
    def test_returns_the_next_agent_when_set(self):
        state = cast(State, {"next_agent": AgentName.REPORT_AGENT})

        assert orchestrator_fate_decision(state) == AgentName.REPORT_AGENT

    def test_falls_back_to_end_when_next_agent_is_none(self):
        state = cast(State, {"next_agent": None})

        assert orchestrator_fate_decision(state) == AgentName.END

    def test_prompt_includes_agent_names_rendered_from_enum(self):
        prompt = ORCHESTRATOR_SYSTEM_PROMPT_FINAL

        assert AgentName.FAQ_AGENT.value in prompt
        assert AgentName.REPORT_AGENT.value in prompt
        assert AgentName.PREDICT_MODEL.value in prompt
        assert AgentName.END.value in prompt


class TestOrchestratorFunc:
    def _make_agent(self, content: str):
        agent = MagicMock()
        agent.invoke.return_value = {"messages": [MagicMock(content=content)]}
        return agent

    def test_sets_final_response_when_next_agent_is_end(self):
        agent = self._make_agent(
            '{"intent": "unclassified", "next_agent": "%s"}' % AgentName.END.value
        )
        orchestrator_func = make_orchestrator_func(agent)

        state = cast(State, {"current_request": "qual a capital da frança?"})
        result = orchestrator_func(state)

        assert result["next_agent"] == AgentName.END
        assert result["final_response"] == UNCLASSIFIED_INTENT_MESSAGE

    def test_does_not_set_final_response_for_regular_routing(self):
        agent = self._make_agent(
            '{"intent": "faq", "next_agent": "%s"}' % AgentName.FAQ_AGENT.value
        )
        orchestrator_func = make_orchestrator_func(agent)

        state = cast(State, {"current_request": "como funciona o zera?"})
        result = orchestrator_func(state)

        assert result["next_agent"] == AgentName.FAQ_AGENT
        assert "final_response" not in result
