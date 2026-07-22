import json
from typing import cast
from unittest.mock import MagicMock

from langchain.messages import HumanMessage

from multi_agent.entity import AgentName, State
from multi_agent.agents.report import make_report_func


class TestReportFunc:
    def test_parses_the_report_sections_from_the_agent(self):
        report_agent = MagicMock()
        report_agent.invoke.return_value = {
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "report_header": "Relatório — Lote 45",
                            "report_body": "12 notebooks descartáveis.",
                            "report_footer": "Gerado pelo sistema Zera.",
                        }
                    )
                )
            ]
        }
        report_func = make_report_func(report_agent)

        result = report_func(cast(State, {"messages": [HumanMessage(content="gere o relatório do lote 45")]}))

        assert result == {
            "called_agents": [AgentName.REPORT_AGENT],
            "report_header": "Relatório — Lote 45",
            "report_body": "12 notebooks descartáveis.",
            "report_footer": "Gerado pelo sistema Zera.",
        }
