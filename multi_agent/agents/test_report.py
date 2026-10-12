import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from multi_agent.entity import AgentName, State
from multi_agent.agents.report import make_report_func
from multi_agent.unit_scope import current_unit_id, set_unit_id


class TestReportFunc:
    def test_parses_the_report_html_from_the_agent(self):
        report_agent = MagicMock()
        report_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "quote_number": "Lote 45",
                            "categories": [{"name": "Notebooks", "quantity": "12", "unit": "unidades"}],
                            "items": [],
                        }
                    )
                )
            ]
        })
        report_func = make_report_func(report_agent)

        result = asyncio.run(report_func(cast(State, {"current_request": "gere o relatório do lote 45"})))

        assert result["called_agents"] == [AgentName.REPORT_AGENT]
        assert "Cotação de equipamentos" in result["report_html"]
        assert "Lote 45" in result["report_html"]
        assert "Notebooks: 12 unidades" in result["report_html"]
        report_agent.ainvoke.assert_called_once_with({"messages": "gere o relatório do lote 45"})

    def test_publishes_the_state_unit_id_for_the_disposal_tool(self):
        set_unit_id(None)
        seen: dict[str, str | None] = {}

        async def ainvoke(_payload):
            seen["unit_id"] = current_unit_id.get()
            return {"messages": [MagicMock(content=json.dumps({"items": []}))]}

        report_agent = MagicMock()
        report_agent.ainvoke = ainvoke
        report_func = make_report_func(report_agent)

        asyncio.run(report_func(cast(State, {
            "current_request": "gere o relatório do descarte 42",
            "unit_id": "33333333-3333-3333-3333-333333333333",
        })))

        assert seen["unit_id"] == "33333333-3333-3333-3333-333333333333"
