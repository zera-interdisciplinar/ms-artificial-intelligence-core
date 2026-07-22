"""
Defines the classes for the multi-agent service and repository. The multi-agent service is responsible for processing messages and the multi-agent repository is responsible for storing and retrieving messages.
"""
from typing import Annotated, Protocol, Any
from uuid import UUID

import operator
from enum import Enum
from datetime import datetime

from langgraph.graph import MessagesState
from pydantic import BaseModel

from langgraph.graph import START, END

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

class Message(BaseModel):
    """Represents a message exchanged in the multi-agent system."""

    user_id: UUID
    thread_id: UUID
    role: Role
    content: str
    agent: AgentName | None = None
    created_at: datetime
    
class State(MessagesState):
    """
    Represents the state of the multi-agent system.
    """

    called_agents: Annotated[list[AgentName], operator.add]

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
    report_header: str | None
    report_body: str | None
    report_footer: str | None

    # predict_model
    predictions: list[dict[str, Any]]

    # formatter_agent
    formatted_response: str | None

    # judge_agent
    approved: bool | None
    discrepancy: str | None
    judge_attempts: Annotated[int, operator.add]

    # guardrail_out
    final_response: str | None
    