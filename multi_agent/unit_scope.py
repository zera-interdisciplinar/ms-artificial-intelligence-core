"""Carries the current request's unit_id from the graph node down to the MCP tool call.

The ms-inventory tools take unitId as a regular tool parameter, which means the
LLM could put anything there (including whatever a prompt injection asked for).
It never gets the chance: bind_unit_id() overwrites the argument right before
dispatch with the value validated against ms-administrative-core, kept here in a
ContextVar so it does not have to be threaded through every agent signature.
"""

from contextvars import ContextVar
from uuid import UUID

from langchain_core.tools import BaseTool

current_unit_id: ContextVar[str | None] = ContextVar("current_unit_id", default=None)


def set_unit_id(unit_id: UUID | str | None) -> None:
    current_unit_id.set(str(unit_id) if unit_id is not None else None)


def bind_unit_id(tools: list[BaseTool]) -> list[BaseTool]:
    """
    Wraps each tool so unitId is always the validated one, never the LLM's.
    
    The system will validate the user before ivoking the multi-agent graph, so the unit_id is guaranteed to be correct.
    """

    for tool in tools:
        original = tool.coroutine
        if original is None:
            continue

        async def bound(*args, __original=original, **kwargs):
            kwargs["unitId"] = current_unit_id.get()
            return await __original(*args, **kwargs)

        tool.coroutine = bound
    return tools
