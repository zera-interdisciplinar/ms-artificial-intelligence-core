import json
from unittest.mock import MagicMock

import pytest
from langchain.messages import HumanMessage

from multi_agent.entity import AgentName
from multi_agent.agents.guardrail import Guardrail


@pytest.fixture(autouse=True)
def clear_pii_map():
    """PII_MAP is a class attribute shared across instances; keep tests isolated."""
    Guardrail.PII_MAP.clear()
    yield
    Guardrail.PII_MAP.clear()


@pytest.fixture
def guardrail():
    return Guardrail(guardrail_in_agent=MagicMock(), guardrail_out_agent=MagicMock())


class TestRemovePiiFromText:
    def test_masks_a_cpf(self, guardrail):
        text = "meu cpf é 123.456.789-09"

        new_text, pii_map = guardrail._remove_pii_from_text(text)

        assert "123.456.789-09" not in new_text
        assert "<CPF_0>" in new_text
        assert pii_map["<CPF_0>"] == "123.456.789-09"

    def test_masks_an_email(self, guardrail):
        text = "contato: joao@example.com"

        new_text, pii_map = guardrail._remove_pii_from_text(text)

        assert "joao@example.com" not in new_text
        assert pii_map["<EMAIL_0>"] == "joao@example.com"

    def test_masks_multiple_pii_types(self, guardrail):
        text = "email joao@example.com e cpf 123.456.789-09"

        new_text, pii_map = guardrail._remove_pii_from_text(text)

        assert pii_map["<EMAIL_0>"] == "joao@example.com"
        assert pii_map["<CPF_0>"] == "123.456.789-09"

    def test_leaves_text_without_pii_unchanged(self, guardrail):
        text = "quais perfis de usuário existem no sistema?"

        new_text, pii_map = guardrail._remove_pii_from_text(text)

        assert new_text == text
        assert pii_map == {}


class TestRetreivePiiFromText:
    def test_restores_the_original_values(self, guardrail):
        pii_map = {"<CPF_0>": "123.456.789-09", "<EMAIL_0>": "joao@example.com"}
        text = "cpf <CPF_0> email <EMAIL_0>"

        restored = guardrail._retreive_pii_from_text(text, pii_map)

        assert restored == "cpf 123.456.789-09 email joao@example.com"

    def test_returns_text_unchanged_when_map_is_empty(self, guardrail):
        assert guardrail._retreive_pii_from_text("sem pii aqui", {}) == "sem pii aqui"


class TestGuardrailInFateDecision:
    def test_routes_to_end_when_blocked(self, guardrail):
        assert guardrail.guardrail_in_fate_decision({"blocked": True}) == AgentName.END

    def test_routes_to_orchestrator_when_not_blocked(self, guardrail):
        assert (
            guardrail.guardrail_in_fate_decision({"blocked": False})
            == AgentName.ORCHESTRATOR
        )


class TestGuardrailInFunc:
    def test_returns_blocked_classification_from_the_agent(self, guardrail):
        original_message = HumanMessage(content="meu cpf é 123.456.789-09", id="msg-1")
        guardrail.guardrail_in_agent.invoke.return_value = {
            "messages": [
                MagicMock(
                    content=json.dumps({"blocked": True, "blocked_reason": "PII detectado"})
                )
            ]
        }

        result = guardrail.guardrail_in_func({"messages": [original_message]})

        assert result["blocked"] is True
        assert result["blocked_reason"] == "PII detectado"
        assert len(result["messages"]) == 2
        assert result["messages"][0].id == original_message.id

    def test_masks_pii_before_calling_the_agent(self, guardrail):
        original_message = HumanMessage(content="contato joao@example.com", id="msg-2")
        guardrail.guardrail_in_agent.invoke.return_value = {
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        }

        guardrail.guardrail_in_func({"messages": [original_message]})

        invoked_message = guardrail.guardrail_in_agent.invoke.call_args[0][0]["messages"][0]
        assert "joao@example.com" not in invoked_message.content
        assert Guardrail.PII_MAP["<EMAIL_0>"] == "joao@example.com"


class TestGuardrailOutFunc:
    def test_returns_no_final_response_when_blocked(self, guardrail):
        guardrail.guardrail_out_agent.invoke.return_value = {
            "messages": [
                MagicMock(
                    content=json.dumps({"blocked": True, "blocked_reason": "conteúdo sensível"})
                )
            ]
        }

        result = guardrail.guardrail_out_func({"formatted_response": "algo"})

        assert result["blocked"] is True
        assert result["final_response"] is None

    def test_restores_pii_in_the_final_response(self, guardrail):
        Guardrail.PII_MAP["<EMAIL_0>"] = "joao@example.com"
        guardrail.guardrail_out_agent.invoke.return_value = {
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        }

        result = guardrail.guardrail_out_func({"formatted_response": "contato <EMAIL_0>"})

        assert result["blocked"] is False
        assert result["final_response"] == "contato joao@example.com"


class TestPiiMapIsSharedBetweenInstances:
    def test_pii_map_is_a_class_level_attribute(self):
        """Documents current behavior: PII_MAP is shared across Guardrail instances."""
        first = Guardrail(guardrail_in_agent=MagicMock(), guardrail_out_agent=MagicMock())
        second = Guardrail(guardrail_in_agent=MagicMock(), guardrail_out_agent=MagicMock())

        first.PII_MAP["<EMAIL_0>"] = "joao@example.com"

        assert second.PII_MAP["<EMAIL_0>"] == "joao@example.com"
