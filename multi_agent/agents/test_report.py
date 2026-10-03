import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from multi_agent.entity import AgentName, State
from multi_agent.agents.report import make_report_func


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
