from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any, cast

import pytest
from pydantic import ValidationError

from multi_agent.entity import (
    AgentName,
    AgentResponse,
    Message,
    Role,
    State,
)


class TestRole:
    def test_members_serialize_as_their_string_value(self):
        assert Role.USER == "user"
        assert Role.ASSISTANT == "assistant"
        assert Role.SYSTEM == "system"

    def test_has_exactly_the_three_expected_members(self):
        assert {role.value for role in Role} == {"user", "assistant", "system"}


class TestAgentName:
    def test_covers_every_node_of_the_graph(self):
        assert {agent.value for agent in AgentName} == {
            "guardrail_in",
            "orchestrator",
            "faq",
            "report",
            "predict_model",
            "formatter",
            "judge",
            "guardrail_out",
            "__end__",
            "__start__",
        }

    def test_members_serialize_as_their_string_value(self):
        assert AgentName.GUARDRAIL_IN == "guardrail_in"


class TestAgentResponse:
    def test_defaults_to_an_unblocked_response_with_no_trace(self):
        response = AgentResponse(content="olá")

        assert response.content == "olá"
        assert response.blocked is False
        assert response.blocked_reason is None
        assert response.agent_trace == []

    def test_accepts_a_blocked_response(self):
        response = AgentResponse(
            content="",
            blocked=True,
            blocked_reason="conteúdo sensível",
            agent_trace=["guardrail_in"],
        )

        assert response.blocked is True
        assert response.blocked_reason == "conteúdo sensível"
        assert response.agent_trace == ["guardrail_in"]

    def test_agent_trace_default_is_not_shared_between_instances(self):
        first = AgentResponse(content="a")
        first.agent_trace.append("orchestrator")

        assert AgentResponse(content="b").agent_trace == []

    def test_content_is_required(self):
        with pytest.raises(ValidationError):
            AgentResponse(content=cast(Any, None))


class TestMessage:
    def test_builds_from_valid_values(self, message, user_id, thread_id):
        assert message.user_id == user_id
        assert message.thread_id == thread_id
        assert message.role is Role.USER
        assert message.agent is AgentName.FAQ_AGENT

    def test_agent_is_optional(self, user_id, thread_id):
        message = Message(
            user_id=user_id,
            thread_id=thread_id,
            role=Role.USER,
            content="olá",
            created_at=datetime.now(timezone.utc),
        )

        assert message.agent is None

    def test_parses_uuid_and_enum_values_from_strings(self):
        message = Message(
            user_id=cast(Any, "11111111-1111-1111-1111-111111111111"),
            thread_id=cast(Any, "22222222-2222-2222-2222-222222222222"),
            role=cast(Any, "assistant"),
            content="olá",
            agent=cast(Any, "judge"),
            created_at=cast(Any, "2026-07-16T12:00:00Z"),
        )

        assert message.user_id == UUID("11111111-1111-1111-1111-111111111111")
        assert message.role is Role.ASSISTANT
        assert message.agent is AgentName.JUDGE_AGENT

    def test_rejects_an_unknown_role(self, user_id, thread_id):
        with pytest.raises(ValidationError):
            Message(
                user_id=user_id,
                thread_id=thread_id,
                role=cast(Any, "moderator"),
                content="olá",
                created_at=datetime.now(timezone.utc),
            )

    def test_rejects_a_malformed_uuid(self, thread_id):
        with pytest.raises(ValidationError):
            Message(
                user_id=cast(Any, "not-a-uuid"),
                thread_id=thread_id,
                role=Role.USER,
                content="olá",
                created_at=datetime.now(timezone.utc),
            )

    @pytest.mark.parametrize(
        "missing", ["user_id", "thread_id", "role", "content", "created_at"]
    )
    def test_required_fields(self, missing, user_id, thread_id):
        payload = {
            "user_id": user_id,
            "thread_id": thread_id,
            "role": Role.USER,
            "content": "olá",
            "created_at": datetime.now(timezone.utc),
        }
        payload.pop(missing)

        with pytest.raises(ValidationError):
            Message(**payload)

    def test_json_dump_round_trips(self, message):
        dumped = message.model_dump(mode="json")

        assert dumped["user_id"] == str(message.user_id)
        assert dumped["role"] == "user"
        assert dumped["agent"] == "faq"
        assert Message.model_validate(dumped) == message


class TestState:
    def test_is_a_typed_dict_carrying_the_graph_contract(self):
        state: State = {
            "messages": [],
            "called_agents": [AgentName.GUARDRAIL_IN],
            "next_agent": AgentName.ORCHESTRATOR,
            "intent": "faq",
            "blocked": False,
            "blocked_reason": None,
            "pii_map": {},
            "answer": "três perfis",
            "sources": ["zera_overview.pdf#p2"],
            "report_header": None,
            "report_body": None,
            "report_footer": None,
            "predictions": [],
            "formatted_response": None,
            "approved": True,
            "discrepancy": None,
            "judge_attempts": 0,
            "final_response": "três perfis",
        }

        assert state["called_agents"] == [AgentName.GUARDRAIL_IN]
        assert state["blocked"] is False

    def test_declares_every_key_the_agents_exchange(self):
        expected = {
            "messages",
            "called_agents",
            "next_agent",
            "intent",
            "blocked",
            "blocked_reason",
            "pii_map",
            "answer",
            "sources",
            "report_header",
            "report_body",
            "report_footer",
            "predictions",
            "formatted_response",
            "approved",
            "discrepancy",
            "final_response",
        }

        assert expected <= set(State.__annotations__)

    def test_called_agents_uses_a_reset_or_add_reducer(self):
        """The reducer lets each node append its own name to the trace within a run,
        while an empty update (used between separate invocations) resets it instead
        of accumulating forever."""
        reducer = State.__annotations__["called_agents"].__metadata__[0]

        assert reducer([AgentName.ORCHESTRATOR], [AgentName.FAQ_AGENT]) == [
            AgentName.ORCHESTRATOR,
            AgentName.FAQ_AGENT,
        ]
        assert reducer([AgentName.ORCHESTRATOR], []) == []

    def test_judge_attempts_uses_a_reset_or_add_reducer(self):
        """Same reset-or-accumulate behavior as called_agents, but for the attempts counter."""
        reducer = State.__annotations__["judge_attempts"].__metadata__[0]

        assert reducer(1, 1) == 2
        assert reducer(1, 0) == 0
