from typing import cast

from multi_agent.entity import AgentName, State
from multi_agent.agents.orchestrator import orchestrator_fate_decision
from multi_agent.prompt.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT_FINAL


class TestOrchestratorFateDecision:
    def test_returns_the_next_agent_when_set(self):
        state = cast(State, {"next_agent": AgentName.REPORT_AGENT})

        assert orchestrator_fate_decision(state) == AgentName.REPORT_AGENT

    def test_falls_back_to_faq_agent_when_next_agent_is_none(self):
        state = cast(State, {"next_agent": None})

        assert orchestrator_fate_decision(state) == AgentName.FAQ_AGENT

    def test_prompt_includes_agent_names_rendered_from_enum(self):
        prompt = ORCHESTRATOR_SYSTEM_PROMPT_FINAL

        assert AgentName.FAQ_AGENT.value in prompt
        assert AgentName.REPORT_AGENT.value in prompt
        assert AgentName.PREDICT_MODEL.value in prompt
