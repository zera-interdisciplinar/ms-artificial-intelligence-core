import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from multi_agent.entity import AgentName, RedirectTo, State
from multi_agent.agents.faq import FAQ, make_faq_func


class TestFaqFunc:
    def test_parses_the_answer_and_sources_from_the_agent(self):
        faq_agent = MagicMock()
        faq_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "answer": "três perfis",
                            "sources": ["zera_overview.pdf#p2"],
                            "redirect_to": {"screen": "Profile", "message": "Abrir Perfil"},
                        }
                    )
                )
            ]
        })

        result = asyncio.run(make_faq_func(faq_agent)(cast(State, {"current_request": "quais perfis existem?"})))

        assert result == {
            "called_agents": [AgentName.FAQ_AGENT],
            "answer": "três perfis",
            "sources": ["zera_overview.pdf#p2"],
            "redirect_to": RedirectTo(screen="Profile", message="Abrir Perfil"),
        }
        faq_agent.ainvoke.assert_called_once_with({"messages": "quais perfis existem?"})

    def test_parses_a_null_redirect_to_as_none(self):
        faq_agent = MagicMock()
        faq_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {"answer": "não sei", "sources": [], "redirect_to": None}
                    )
                )
            ]
        })

        result = asyncio.run(make_faq_func(faq_agent)(cast(State, {"current_request": "preço?"})))

        assert result["redirect_to"] is None

    def test_invalid_or_missing_redirect_to_becomes_none(self):
        faq_agent = MagicMock()
        faq_agent.ainvoke = AsyncMock(side_effect=[
            {"messages": [MagicMock(content=json.dumps({"answer": "x", "sources": [], "redirect_to": {"screen": "Scan"}}))]},
            {"messages": [MagicMock(content=json.dumps({"answer": "x", "sources": []}))]},
        ])
        faq_func = make_faq_func(faq_agent)

        assert asyncio.run(faq_func(cast(State, {"current_request": "a"})))["redirect_to"] is None
        assert asyncio.run(faq_func(cast(State, {"current_request": "b"})))["redirect_to"] is None


class TestMakeRetrieveContextTool:
    def test_queries_the_store_with_the_given_context(self):
        faq = FAQ(envs=MagicMock(), logger=MagicMock())
        faq._store = MagicMock()
        faq._store.similarity_search.return_value = ["doc1", "doc2"]

        tool = faq.make_retrieve_context_tool()
        result = tool.invoke({"ctx": "quais perfis existem?"})

        faq._store.similarity_search.assert_called_once_with(
            "quais perfis existem?", k=6
        )
        assert result == ["doc1", "doc2"]
