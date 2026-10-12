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
    Fails loudly instead of letting a call through with the LLM's unitId (a tool
    with no async implementation to wrap) or with no unit at all (a node that
    forgot set_unit_id), either of which could become an unscoped read.
    """

    for tool in tools:
        original = getattr(tool, "coroutine", None)
        assert original is not None, f"{tool.name} has no async implementation, so its unitId cannot be bound"

        async def bound(*args, __original=original, __name=tool.name, **kwargs):
            unit_id = current_unit_id.get()
            if unit_id is None:
                raise RuntimeError(f"{__name} called without a validated unit_id; set_unit_id was not called")
            kwargs["unitId"] = unit_id
            return await __original(*args, **kwargs)

        tool.coroutine = bound
    return tools
