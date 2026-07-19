from multi_agent.entity import AgentName, State
from multi_agent.agents.orchestrator import orchestrator_fate_decision


class TestOrchestratorFateDecision:
    def test_returns_the_next_agent_when_set(self):
        state = {"next_agent": AgentName.REPORT_AGENT}

        assert orchestrator_fate_decision(state) == AgentName.REPORT_AGENT

    def test_falls_back_to_faq_agent_when_next_agent_is_none(self):
        state = {"next_agent": None}

        assert orchestrator_fate_decision(state) == AgentName.FAQ_AGENT
