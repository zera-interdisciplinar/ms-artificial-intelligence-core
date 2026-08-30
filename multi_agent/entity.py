"""
Defines the classes for the multi-agent service and repository. The multi-agent service is responsible for processing messages and the multi-agent repository is responsible for storing and retrieving messages.
"""
from typing import Annotated, Any, Protocol
from uuid import UUID

from enum import Enum
from datetime import datetime

from langgraph.graph import MessagesState
from pydantic import BaseModel

from langgraph.graph import START, END


def _reset_or_add_list(existing: list, new: list) -> list:
    """
    Reducer for procedural fields in State, if a empty list is passed, it resets the field instead of accumulating. It will be used when we want to reset some data from the state, for example when we want to reset the called_agents list.
    """
    if not new:
        return new
    return existing + new


def _reset_or_add_int(existing: int, new: int) -> int:
    """
    Reducer for procedural fields in State, if a zero is passed, it resets the field instead of accumulating. It will be used when we want to reset some data from the state, for example when we want to reset the judge_attempts counter.
    """
    if not new:
        return new
    return existing + new

# enum for the role of the message sender
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class AgentName(str, Enum):
    GUARDRAIL_IN = "guardrail_in"
    ORCHESTRATOR = "orchestrator"
    FAQ_AGENT = "faq"
    REPORT_AGENT = "report"
    PREDICT_MODEL = "predict_model"
    FORMATTER_AGENT = "formatter"
    JUDGE_AGENT = "judge"
    GUARDRAIL_OUT = "guardrail_out"

    END = END  # special value to indicate the end of the flow
    START = START  # special value to indicate the start of the flow


class AgentResponse(BaseModel):
    """Structured response from an agent in the multi-agent system after the all processing is done, including the guardrails."""

    content: str
    blocked: bool = False
    blocked_reason: str | None = None
    agent_trace: list[str] = []
    report_url: str | None = None

class Message(BaseModel):
    """Represents a message exchanged in the multi-agent system."""

    user_id: UUID
    thread_id: UUID
    role: Role
    content: str
    agent: AgentName | None = None
    created_at: datetime

class UserPreferences(BaseModel):
    """Long-term, cross-session memory about a user: writing style, company
    context and recurring requests. Updated out-of-band (fire-and-forget)
    when a session's MemorySaver expires, over the whole conversation."""

    user_id: UUID
    writing_style: str | None = None
    company_context: str | None = None
    frequent_requests: list[str] = []
    updated_at: datetime


class PredictionItem(BaseModel):
    """A single predict_model result, validated right after the LLM call so a
    malformed/hallucinated shape fails loudly there instead of propagating as
    a plain dict into formatter/judge."""

    item: str
    estimated_remaining_months: int | None
    adjusted: bool
    adjustment_reason: str | None


class State(MessagesState):
    """
    Represents the state of the multi-agent system.
    """

    # general
    called_agents: Annotated[list[AgentName], _reset_or_add_list]
    current_request: str | None
    user_preferences: str | None  # rendered long-term memory, seeded on session hydration

    # routing
    next_agent: AgentName | None  # an AgentName value
    intent: str | None

    # guardrails
    blocked: bool
    blocked_reason: str | None
    pii_map: dict[str, str]

    # faq_agent
    answer: str | None
    sources: list[str]

    # report_agent
    report_html: str | None

    # predict_model
    predictions: list[PredictionItem]

    # formatter_agent
    formatted_response: str | None

    # judge_agent
    approved: bool | None
    discrepancy: str | None
    judge_attempts: Annotated[int, _reset_or_add_int]

    # guardrail_out
    final_response: str | None


class GraphNodeFunc(Protocol):
    """Callable shape of an async LangGraph state-graph node function.

    StateGraph.add_node calls a node as node(state=...) (by keyword), so the
    `state` parameter must keep its name. A plain `Callable[[State],
    Awaitable[dict[str, Any]]]` type alias erases that name, which makes
    pyright/mypy reject it as incompatible with add_node's overloads even
    though the same function passed in unannotated (or as a bound method)
    type-checks fine.

    Every node is async because the predict_model node calls an MCP tool
    that only has an async implementation (langchain-mcp-adapters wraps MCP
    tools with `coroutine=...`, no sync `func=`); mixing a sync StateGraph
    with that async-only node isn't possible, so the whole graph — and every
    node in it — runs via ainvoke."""

    async def __call__(self, state: State) -> dict[str, Any]: ...
