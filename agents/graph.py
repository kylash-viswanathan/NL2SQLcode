"""Wires the Planner -> Schema-Linking -> SQL Generation -> HITL Gate -> Execution ->
Governance -> Critic -> Response agents into a single LangGraph StateGraph, with a
bounded self-healing retry loop (shared between Execution's DB-error retries and the
Critic's correctness-check retries) and an interrupt-based HITL pause/resume.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.critic import critic_node
from agents.execution import execution_node
from agents.hitl_gate import hitl_gate_node
from agents.planner import planner_node
from agents.response import response_node
from agents.schema_linking import schema_linking_node
from agents.sql_generation import sql_generation_node
from agents.state import GraphState
from config.settings import settings
from governance.masking import governance_node


def route_after_planner(state: GraphState) -> str:
    return "schema_linking" if state.get("route") == "generate" else "response"


def route_after_sql_generation(state: GraphState) -> str:
    # sql_generation sets execution_error directly when the SELECT-only guardrail blocks it.
    return "response" if state.get("execution_error") else "hitl_gate"


def route_after_execution(state: GraphState) -> str:
    if state.get("hitl_required") and not state.get("hitl_approved"):
        return "governance"  # rejected by reviewer, no point retrying
    if state.get("execution_error") and state.get("retry_count", 0) < settings.max_self_heal_retries:
        return "sql_generation"
    return "governance"


def route_after_critic(state: GraphState) -> str:
    if state.get("critic_passed", True):
        return "response"
    if state.get("retry_count", 0) < settings.max_self_heal_retries:
        return "sql_generation"
    return "response"  # retries exhausted — response.py adds an unverified-answer caveat


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("planner", planner_node)
    graph.add_node("schema_linking", schema_linking_node)
    graph.add_node("sql_generation", sql_generation_node)
    graph.add_node("hitl_gate", hitl_gate_node)
    graph.add_node("execution", execution_node)
    graph.add_node("governance", governance_node)
    graph.add_node("critic", critic_node)
    graph.add_node("response", response_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_after_planner, ["schema_linking", "response"])
    graph.add_edge("schema_linking", "sql_generation")
    graph.add_conditional_edges(
        "sql_generation", route_after_sql_generation, ["hitl_gate", "response"]
    )
    graph.add_edge("hitl_gate", "execution")
    graph.add_conditional_edges(
        "execution", route_after_execution, ["sql_generation", "governance"]
    )
    graph.add_edge("governance", "critic")
    graph.add_conditional_edges("critic", route_after_critic, ["sql_generation", "response"])
    graph.add_edge("response", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
