import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from multi_agent.entity import AgentName, State
from multi_agent.agents.inventory import make_inventory_func, inventory_fate_decision
from multi_agent.unit_scope import current_unit_id, set_unit_id


class TestInventoryFunc:
    def test_parses_answer_from_tool_result(self):
        inventory_agent = MagicMock()
        inventory_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "answer": "O notebook NB-4521 está classificado como 'em uso', localizado no setor de TI.",
                        }
                    )
                )
            ]
        })
        inventory_func = make_inventory_func(inventory_agent)

        result = asyncio.run(inventory_func(cast(State, {"current_request": "status do notebook NB-4521", "pending_agent": None})))

        assert result == {
            "called_agents": [AgentName.INVENTORY_AGENT],
            "inventory_answer": "O notebook NB-4521 está classificado como 'em uso', localizado no setor de TI.",
            "next_agent": AgentName.FORMATTER_AGENT,
        }

    def test_parses_answer_when_no_item_is_found(self):
        inventory_agent = MagicMock()
        inventory_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "answer": "Não foi encontrado nenhum item correspondente no inventário para essa consulta.",
                        }
                    )
                )
            ]
        })
        inventory_func = make_inventory_func(inventory_agent)

        result = asyncio.run(inventory_func(cast(State, {"current_request": "status do item XYZ-999"})))

        assert result["inventory_answer"] == "Não foi encontrado nenhum item correspondente no inventário para essa consulta."

    def test_raises_when_the_agent_returns_malformed_json(self):
        inventory_agent = MagicMock()
        inventory_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="isso não é um JSON válido")]
        })
        inventory_func = make_inventory_func(inventory_agent)

        with pytest.raises(json.JSONDecodeError):
            asyncio.run(inventory_func(cast(State, {"current_request": "status do notebook NB-4521"})))


class TestInventoryChaining:
    def test_resumes_pending_agent_with_inventory_data_appended(self):
        inventory_agent = MagicMock()
        inventory_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content=json.dumps({"answer": "NB-4521: notebook, categoria eletrônico."}))]
        })
        inventory_func = make_inventory_func(inventory_agent)

        result = asyncio.run(inventory_func(cast(State, {
            "current_request": "liste dados do NB-4521",
            "pending_agent": AgentName.PREDICT_MODEL,
            "pending_request": "Faça uma previsão de quebra para o NB-4521.",
        })))

        assert result["next_agent"] == AgentName.PREDICT_MODEL
        assert result["pending_agent"] is None
        assert result["pending_request"] is None
        assert "Faça uma previsão de quebra para o NB-4521." in result["current_request"]
        assert "NB-4521: notebook, categoria eletrônico." in result["current_request"]

    def test_fate_decision_follows_next_agent(self):
        assert inventory_fate_decision(cast(State, {"next_agent": AgentName.PREDICT_MODEL})) == AgentName.PREDICT_MODEL
        assert inventory_fate_decision(cast(State, {"next_agent": AgentName.FORMATTER_AGENT})) == AgentName.FORMATTER_AGENT


class TestUnitScope:
    def test_publishes_the_state_unit_id_for_the_mcp_tools(self):
        """The tools read the unit from the ContextVar, so the node has to set it
        before the agent runs — otherwise the call would go out unscoped."""

        set_unit_id(None)
        seen: dict[str, str | None] = {}

        async def ainvoke(_payload):
            seen["unit_id"] = current_unit_id.get()
            return {"messages": [MagicMock(content=json.dumps({"answer": "ok"}))]}

        inventory_agent = MagicMock()
        inventory_agent.ainvoke = ainvoke
        inventory_func = make_inventory_func(inventory_agent)

        asyncio.run(inventory_func(cast(State, {
            "current_request": "quais itens têm bateria de lítio",
            "unit_id": "33333333-3333-3333-3333-333333333333",
        })))

        assert seen["unit_id"] == "33333333-3333-3333-3333-333333333333"
