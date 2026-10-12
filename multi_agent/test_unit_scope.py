import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from langchain_core.tools import StructuredTool

from .unit_scope import bind_unit_id, current_unit_id, set_unit_id

UNIT_ID = UUID("33333333-3333-3333-3333-333333333333")


def _tool(coroutine) -> StructuredTool:
    return StructuredTool(
        name="search_inventory",
        description="busca itens",
        args_schema={"type": "object", "properties": {"unitId": {"type": "string"}}},
        coroutine=coroutine,
    )


class TestBindUnitId:
    def test_overwrites_the_unit_the_llm_produced(self):
        """The whole point: a prompt injection can make the model ask for another
        unit, and the argument is replaced before the call leaves the process."""

        called = {}

        async def call_tool(**kwargs):
            called.update(kwargs)
            return "ok"

        tool = bind_unit_id([_tool(call_tool)])[0]
        set_unit_id(UNIT_ID)

        asyncio.run(tool.coroutine(unitId="99999999-9999-9999-9999-999999999999", query="notebook"))

        assert called == {"unitId": str(UNIT_ID), "query": "notebook"}

    def test_fills_the_unit_when_the_llm_omits_it(self):
        called = {}

        async def call_tool(**kwargs):
            called.update(kwargs)
            return "ok"

        tool = bind_unit_id([_tool(call_tool)])[0]
        set_unit_id(UNIT_ID)

        asyncio.run(tool.coroutine(query="notebook"))

        assert called["unitId"] == str(UNIT_ID)

    def test_refuses_a_tool_without_a_coroutine_at_boot(self):
        tool = MagicMock()
        tool.coroutine = None

        with pytest.raises(AssertionError, match="cannot be bound"):
            bind_unit_id([tool])

    def test_never_calls_the_tool_without_a_validated_unit(self):
        call_tool = AsyncMock()
        tool = bind_unit_id([_tool(call_tool)])[0]
        set_unit_id(None)

        with pytest.raises(RuntimeError, match="without a validated unit_id"):
            asyncio.run(tool.coroutine(unitId="99999999-9999-9999-9999-999999999999"))

        call_tool.assert_not_awaited()


class TestSetUnitId:
    def test_stores_none_as_none_instead_of_the_string(self):
        set_unit_id(None)
        assert current_unit_id.get() is None
