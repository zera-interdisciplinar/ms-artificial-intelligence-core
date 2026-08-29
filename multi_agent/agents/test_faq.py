import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from multi_agent.entity import AgentName, State
from multi_agent.agents.faq import FAQ


class TestFaqFunc:
    def test_parses_the_answer_and_sources_from_the_agent(self):
        faq_agent = MagicMock()
        faq_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"answer": "três perfis", "sources": ["zera_overview.pdf#p2"]}
                    )
                )
            ]
        })
        faq = FAQ(envs=MagicMock(), logger=MagicMock())
        faq.faq_agent = faq_agent

        result = asyncio.run(faq.faq_func(cast(State, {"current_request": "quais perfis existem?"})))

        assert result == {
            "called_agents": [AgentName.FAQ_AGENT],
            "answer": "três perfis",
            "sources": ["zera_overview.pdf#p2"],
        }
        faq_agent.ainvoke.assert_called_once_with({"messages": "quais perfis existem?"})


class TestMakeRetrieveContextTool:
    def test_queries_the_faiss_index_with_the_given_context(self):
        faq = FAQ(envs=MagicMock(), logger=MagicMock())
        faq._faiss_indexes = MagicMock()
        faq._faiss_indexes.similarity_search.return_value = ["doc1", "doc2"]

        tool = faq.make_retrieve_context_tool()
        result = tool.invoke({"ctx": "quais perfis existem?"})

        faq._faiss_indexes.similarity_search.assert_called_once_with(
            "quais perfis existem?", k=6
        )
        assert result == ["doc1", "doc2"]
