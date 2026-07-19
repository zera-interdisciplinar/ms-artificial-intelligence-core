import json
from unittest.mock import MagicMock

from langchain.messages import HumanMessage

from multi_agent.agents.faq import make_faq_func


class TestFaqFunc:
    def test_parses_the_answer_and_sources_from_the_agent(self):
        faq_agent = MagicMock()
        faq_agent.invoke.return_value = {
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"answer": "três perfis", "sources": ["zera_overview.pdf#p2"]}
                    )
                )
            ]
        }
        faq_func = make_faq_func(faq_agent)

        result = faq_func({"messages": [HumanMessage(content="quais perfis existem?")]})

        assert result == {"answer": "três perfis", "sources": ["zera_overview.pdf#p2"]}
