"""
Topology of the multi-agent graph: which node runs after which. Pure — it only
wires already-built nodes, so routing can be tested without LLMs or network.
"""

from collections.abc import Callable, Mapping

from langgraph.graph import StateGraph

from .entity import AgentName, GraphNodeFunc, State
from .agents.orchestrator import orchestrator_fate_decision
from .agents.inventory import inventory_fate_decision
from .agents.judge import judge_fate_decision


def build_graph(
    nodes: Mapping[AgentName, GraphNodeFunc],
    guardrail_in_fate_decision: Callable[[State], str],
) -> StateGraph:
    graph = StateGraph(State)

    for name, node in nodes.items():
        graph.add_node(name, node)

    graph.set_entry_point(AgentName.GUARDRAIL_IN)

    graph.add_conditional_edges(
        AgentName.GUARDRAIL_IN,
        guardrail_in_fate_decision,
        {
            AgentName.ORCHESTRATOR: AgentName.ORCHESTRATOR,
            AgentName.END: AgentName.END,
        },
    )

    # unclassified intent still leaves through guardrail_out (suggestion goes through the safety check)
    graph.add_conditional_edges(
        AgentName.ORCHESTRATOR,
        orchestrator_fate_decision,
        {
            AgentName.PREDICT_MODEL: AgentName.PREDICT_MODEL,
            AgentName.REPORT_AGENT: AgentName.REPORT_AGENT,
            AgentName.FAQ_AGENT: AgentName.FAQ_AGENT,
            AgentName.INVENTORY_AGENT: AgentName.INVENTORY_AGENT,
            AgentName.END: AgentName.GUARDRAIL_OUT,
        },
    )

    graph.add_edge(AgentName.PREDICT_MODEL, AgentName.FORMATTER_AGENT)
    graph.add_edge(AgentName.REPORT_AGENT, AgentName.FORMATTER_AGENT)
    graph.add_edge(AgentName.FAQ_AGENT, AgentName.FORMATTER_AGENT)

    graph.add_conditional_edges(
        AgentName.INVENTORY_AGENT,
        inventory_fate_decision,
        {
            AgentName.PREDICT_MODEL: AgentName.PREDICT_MODEL,
            AgentName.FORMATTER_AGENT: AgentName.FORMATTER_AGENT,
        },
    )

    graph.add_edge(AgentName.FORMATTER_AGENT, AgentName.JUDGE_AGENT)

    graph.add_conditional_edges(
        AgentName.JUDGE_AGENT,
        judge_fate_decision,
        {
            AgentName.ORCHESTRATOR: AgentName.ORCHESTRATOR,
            AgentName.GUARDRAIL_OUT: AgentName.GUARDRAIL_OUT,
        },
    )

    graph.add_edge(AgentName.GUARDRAIL_OUT, AgentName.END)

    return graph
