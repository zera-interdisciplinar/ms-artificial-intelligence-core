import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.messages import HumanMessage, RemoveMessage
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from multi_agent.entity import AgentName
from multi_agent.agents.guardrail import Guardrail
from multi_agent.prompt.guardrail_in import GUARDRAIL_IN_SYSTEM_PROMPT_FINAL
from multi_agent.prompt.guardrail_out import GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL


@pytest.fixture
def guardrail():
    return Guardrail(
        guardrail_in_agent=MagicMock(),
        guardrail_out_agent=MagicMock(),
        logger=MagicMock(),
    )


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

    def test_does_not_mask_disposal_ids_or_asset_numbers(self, guardrail):
        text = (
            "descarte b7e2c1a0-4f3b-4c2a-8d1e-9a0b1c2d3e4f "
            "patrimônio 12345678901 lote 12345678 código 12345-678"
        )

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


class TestGuardrailPromptPolicy:
    def test_in_blocks_the_whole_message_when_a_zera_request_hides_another_deliverable(self):
        prompt = GUARDRAIL_IN_SYSTEM_PROMPT_FINAL
        assert "task_hijack" in prompt
        assert "mensagem inteira" in prompt
        assert "Não existe metade permitida" in prompt

    def test_out_blocks_source_code_shipped_as_an_answer(self):
        assert "off_scope_output" in GUARDRAIL_OUT_SYSTEM_PROMPT_FINAL


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
        guardrail.guardrail_in_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps({"blocked": True, "blocked_reason": "PII detectado"})
                )
            ]
        })

        result = asyncio.run(guardrail.guardrail_in_func({"messages": [original_message]}))

        assert result["blocked"] is True
        assert result["blocked_reason"] == "PII detectado"
        # the blocked message leaves the history instead of being fed back on later turns
        assert add_messages([original_message], result["messages"]) == []
        assert isinstance(result["messages"][0], RemoveMessage)

    def test_masks_pii_before_calling_the_agent(self, guardrail):
        original_message = HumanMessage(content="contato joao@example.com", id="msg-2")
        guardrail.guardrail_in_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        })

        result = asyncio.run(guardrail.guardrail_in_func({"messages": [original_message]}))

        invoked_message = guardrail.guardrail_in_agent.ainvoke.call_args[0][0]["messages"][0]
        assert "joao@example.com" not in invoked_message.content
        assert result["pii_map"]["<EMAIL_0>"] == "joao@example.com"

    def test_replaces_the_original_in_place_with_the_masked_text(self, guardrail):
        earlier = HumanMessage(content="oi", id="msg-0")
        original_message = HumanMessage(content="contato joao@example.com", id="msg-3")
        guardrail.guardrail_in_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        })

        result = asyncio.run(guardrail.guardrail_in_func({"messages": [earlier, original_message]}))

        history = cast(list[BaseMessage], add_messages([earlier, original_message], result["messages"]))
        assert [m.id for m in history] == ["msg-0", "msg-3"]
        assert history[1].content == "contato <EMAIL_0>"


class TestGuardrailOutFunc:
    def test_returns_no_final_response_when_blocked(self, guardrail):
        guardrail.guardrail_out_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps({"blocked": True, "blocked_reason": "conteúdo sensível"})
                )
            ]
        })

        result = asyncio.run(guardrail.guardrail_out_func({"formatted_response": "algo"}))

        assert result["blocked"] is True
        assert result["final_response"] is None

    def test_restores_pii_in_the_final_response(self, guardrail):
        guardrail.guardrail_out_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        })

        result = asyncio.run(guardrail.guardrail_out_func(
            {"formatted_response": "contato <EMAIL_0>", "pii_map": {"<EMAIL_0>": "joao@example.com"}}
        ))

        assert result["blocked"] is False
        assert result["final_response"] == "contato <EMAIL_0>"


class TestPiiMapIsRequestScoped:
    def test_concurrent_requests_do_not_leak_pii_across_each_other(self, guardrail):
        """pii_map now travels via State (per-invocation), not a shared class attribute."""
        message_a = HumanMessage(content="contato joao@example.com", id="msg-a")
        message_b = HumanMessage(content="contato maria@example.com", id="msg-b")
        guardrail.guardrail_in_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        })

        result_a = asyncio.run(guardrail.guardrail_in_func({"messages": [message_a]}))
        result_b = asyncio.run(guardrail.guardrail_in_func({"messages": [message_b]}))

        guardrail.guardrail_out_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"blocked": False, "blocked_reason": None}))]
        })

        out_a = asyncio.run(guardrail.guardrail_out_func(
            {"formatted_response": "contato <EMAIL_0>", "pii_map": result_a["pii_map"]}
        ))
        out_b = asyncio.run(guardrail.guardrail_out_func(
            {"formatted_response": "contato <EMAIL_0>", "pii_map": result_b["pii_map"]}
        ))

        assert out_a["final_response"] == "contato <EMAIL_0>"
        assert out_b["final_response"] == "contato <EMAIL_0>"
        assert guardrail._retreive_pii_from_text(out_a["final_response"], result_a["pii_map"]) == "contato joao@example.com"
        assert guardrail._retreive_pii_from_text(out_b["final_response"], result_b["pii_map"]) == "contato maria@example.com"
