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

# enum for the role of the message sender
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class AgentName(str, Enum):
    GUARDRAIL_IN = "guardrail_in"
    ORCHESTRATOR = "orchestrator"
    FAQ_AGENT = "faq_agent"
    REPORT_AGENT = "report_agent"
    PREDICT_MODEL = "predict_model"
    FORMATTER_AGENT = "formatter_agent"
    JUDGE_AGENT = "judge_agent"
    GUARDRAIL_OUT = "guardrail_out"


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

class Thread(BaseModel):
    """
    Represents a thread in the multi-agent system. A thread is a collection of messages exchanged between the user and the multi-agent system.
    """

    user_id: UUID
    thread_id: UUID
    messages: list[Message] = []

    def add_message(self, message: Message):
        """
        Adds a message to the thread.
        """
        self.messages.append(message)

    def get_messages(self) -> list[Message]:
        """
        Returns the list of messages in the thread.
        """
        return self.messages
    
class State(MessagesState):
    """
    Represents the state of the multi-agent system.
    """

    called_agents: Annotated[list[AgentName], operator.add]

    # routing
    next_agent: str | None  # an AgentName value, or "END"
    intent: str | None

    # guardrails
    blocked: bool
    blocked_reason: str | None

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

    # guardrail_out
    final_response: str | None
    