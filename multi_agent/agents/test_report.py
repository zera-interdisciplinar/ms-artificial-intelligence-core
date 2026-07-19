import json
from unittest.mock import MagicMock

from langchain.messages import HumanMessage

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

        result = report_func({"messages": [HumanMessage(content="gere o relatório do lote 45")]})

        assert result == {
            "report_header": "Relatório — Lote 45",
            "report_body": "12 notebooks descartáveis.",
            "report_footer": "Gerado pelo sistema Zera.",
        }
