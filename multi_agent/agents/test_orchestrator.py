import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from langchain.messages import HumanMessage

from multi_agent.entity import AgentName, State
from multi_agent.agents.orchestrator import (
    orchestrator_fate_decision,
    make_orchestrator_func,
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
        agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content=content)]})
        return agent

    def test_sets_formatted_response_from_agent_suggestion_when_next_agent_is_end(self):
        # unclassified intent still routes through guardrail_out (see orchestrator_fate_decision /
        # the graph wiring in service.py), so the suggestion goes through formatted_response like
        # any other agent's answer, not final_response directly.
        agent = self._make_agent(
            '{"intent": "unclassified", "next_agent": "%s", "suggestion": "posso ajudar com dúvidas sobre o Zera"}'
            % AgentName.END.value
        )
        orchestrator_func = make_orchestrator_func(agent)

        state = cast(State, {
            "current_request": "qual a capital da frança?",
            "messages": [HumanMessage(content="qual a capital da frança?")],
        })
        result = asyncio.run(orchestrator_func(state))

        assert result["next_agent"] == AgentName.END
        assert result["formatted_response"] == "posso ajudar com dúvidas sobre o Zera"
        assert "final_response" not in result

    def test_uses_resolved_request_from_the_agent_when_history_resolves_a_reference(self):
        agent = self._make_agent(
            '{"intent": "lifetime_prediction", "next_agent": "%s", "resolved_request": "Quanto tempo de vida útil resta para as baterias do lote 15?"}'
            % AgentName.PREDICT_MODEL.value
        )
        orchestrator_func = make_orchestrator_func(agent)

        state = cast(State, {
            "current_request": "E para o lote 15?",
            "messages": [
                HumanMessage(content="Quanto tempo de vida útil resta para as baterias do lote 12?"),
                HumanMessage(content="E para o lote 15?"),
            ],
        })
        result = asyncio.run(orchestrator_func(state))

        assert result["current_request"] == "Quanto tempo de vida útil resta para as baterias do lote 15?"
        request_sent = agent.ainvoke.call_args[0][0]["messages"]
        assert "Histórico recente da conversa" in request_sent
        assert "lote 12" in request_sent

    def test_does_not_set_final_response_for_regular_routing(self):
        agent = self._make_agent(
            '{"intent": "faq", "next_agent": "%s"}' % AgentName.FAQ_AGENT.value
        )
        orchestrator_func = make_orchestrator_func(agent)

        state = cast(State, {
            "current_request": "como funciona o zera?",
            "messages": [HumanMessage(content="como funciona o zera?")],
        })
        result = asyncio.run(orchestrator_func(state))

        assert result["next_agent"] == AgentName.FAQ_AGENT
        assert "final_response" not in result
        assert result["current_request"] == "como funciona o zera?"
