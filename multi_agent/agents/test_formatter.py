import json
from unittest.mock import MagicMock

from langchain.messages import HumanMessage

from multi_agent.agents.formatter import make_formatter_func


class TestFormatterFunc:
    def test_parses_the_formatted_response_from_the_agent(self):
        formatter_agent = MagicMock()
        formatter_agent.invoke.return_value = {
            "messages": [
                MagicMock(content=json.dumps({"formatted_response": "três perfis"}))
            ]
        }
        formatter_func = make_formatter_func(formatter_agent)

        result = formatter_func({"messages": [HumanMessage(content="quais perfis existem?")]})

        assert result == {"formatted_response": "três perfis"}

    def test_sends_the_faq_answer_and_sources_to_the_agent(self):
        formatter_agent = MagicMock()
        formatter_agent.invoke.return_value = {
            "messages": [
                MagicMock(content=json.dumps({"formatted_response": "três perfis"}))
            ]
        }
        formatter_func = make_formatter_func(formatter_agent)

        formatter_func(
            {
                "messages": [HumanMessage(content="quais perfis existem?")],
                "answer": "três perfis",
                "sources": ["zera_overview.pdf#p2"],
                "report_header": None,
                "report_body": None,
                "report_footer": None,
                "predictions": [],
            }
        )

        sent_messages = formatter_agent.invoke.call_args[0][0]["messages"]
        sent_state = json.loads(sent_messages[0].content)
        assert sent_state == {
            "answer": "três perfis",
            "sources": ["zera_overview.pdf#p2"],
        }
