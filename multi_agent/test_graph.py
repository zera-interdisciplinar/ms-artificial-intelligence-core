import asyncio
from typing import Any

import pytest
from langchain.messages import HumanMessage

from .agents.orchestrator import PENDING_ROUTES, ROUTES
from .entity import AgentName
from .graph import build_graph


def _node(name: AgentName, **update: Any):
    async def node(state) -> dict[str, Any]:
        return {"called_agents": [name], **update}
    return node


def _run(nodes: dict, guardrail_decision) -> list[AgentName]:
    graph = build_graph(nodes, guardrail_decision).compile()
    end = asyncio.run(graph.ainvoke({
        "messages": [HumanMessage(content="oi")],
        "called_agents": [],
        "judge_attempts": 0,
        "next_agent": None,
        "approved": None,
    }))
    return end["called_agents"]


def _nodes(**overrides) -> dict:
    nodes = {
        AgentName.GUARDRAIL_IN: _node(AgentName.GUARDRAIL_IN),
        AgentName.ORCHESTRATOR: _node(AgentName.ORCHESTRATOR, next_agent=AgentName.FAQ_AGENT),
        AgentName.PREDICT_MODEL: _node(AgentName.PREDICT_MODEL),
        AgentName.REPORT_AGENT: _node(AgentName.REPORT_AGENT),
        AgentName.INVENTORY_AGENT: _node(AgentName.INVENTORY_AGENT, next_agent=AgentName.PREDICT_MODEL),
        AgentName.FAQ_AGENT: _node(AgentName.FAQ_AGENT),
        AgentName.FORMATTER_AGENT: _node(AgentName.FORMATTER_AGENT),
        AgentName.JUDGE_AGENT: _node(AgentName.JUDGE_AGENT, approved=True, judge_attempts=1),
        AgentName.GUARDRAIL_OUT: _node(AgentName.GUARDRAIL_OUT),
    }
    nodes.update(overrides)
    return nodes


def test_blocked_input_stops_at_guardrail_in():
    assert _run(_nodes(), lambda state: AgentName.END) == [AgentName.GUARDRAIL_IN]


def test_specialist_goes_through_formatter_judge_and_guardrail_out():
    assert _run(_nodes(), lambda state: AgentName.ORCHESTRATOR) == [
        AgentName.GUARDRAIL_IN, AgentName.ORCHESTRATOR, AgentName.FAQ_AGENT,
        AgentName.FORMATTER_AGENT, AgentName.JUDGE_AGENT, AgentName.GUARDRAIL_OUT,
    ]


def test_inventory_can_hand_over_to_predict_model():
    nodes = _nodes(**{AgentName.ORCHESTRATOR: _node(AgentName.ORCHESTRATOR, next_agent=AgentName.INVENTORY_AGENT)})
    assert _run(nodes, lambda state: AgentName.ORCHESTRATOR)[2:4] == [
        AgentName.INVENTORY_AGENT, AgentName.PREDICT_MODEL,
    ]


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_every_route_the_orchestrator_accepts_has_an_edge(route):
    nodes = _nodes(**{
        AgentName.ORCHESTRATOR: _node(AgentName.ORCHESTRATOR, next_agent=route),
        AgentName.INVENTORY_AGENT: _node(AgentName.INVENTORY_AGENT, next_agent=AgentName.FORMATTER_AGENT),
    })
    assert _run(nodes, lambda state: AgentName.ORCHESTRATOR)[-1] == AgentName.GUARDRAIL_OUT


@pytest.mark.parametrize("pending", sorted(PENDING_ROUTES))
def test_every_pending_route_has_an_edge_from_inventory(pending):
    nodes = _nodes(**{
        AgentName.ORCHESTRATOR: _node(AgentName.ORCHESTRATOR, next_agent=AgentName.INVENTORY_AGENT),
        AgentName.INVENTORY_AGENT: _node(AgentName.INVENTORY_AGENT, next_agent=pending),
    })
    assert pending in _run(nodes, lambda state: AgentName.ORCHESTRATOR)


def test_rejected_answer_retries_once_from_the_orchestrator():
    nodes = _nodes(**{AgentName.JUDGE_AGENT: _node(AgentName.JUDGE_AGENT, approved=False, judge_attempts=1)})
    trace = _run(nodes, lambda state: AgentName.ORCHESTRATOR)
    assert trace.count(AgentName.ORCHESTRATOR) == 2
    assert trace[-1] == AgentName.GUARDRAIL_OUT
