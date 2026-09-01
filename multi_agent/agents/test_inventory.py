import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from multi_agent.entity import AgentName, State
from multi_agent.agents.inventory import make_inventory_func


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

        result = asyncio.run(inventory_func(cast(State, {"current_request": "status do notebook NB-4521"})))

        assert result == {
            "called_agents": [AgentName.INVENTORY_AGENT],
            "inventory_answer": "O notebook NB-4521 está classificado como 'em uso', localizado no setor de TI.",
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
