"""Shared graph-invocation helper used by both the Chainlit UI and the evaluation
harness. Handles the LangGraph interrupt/resume cycle for the HITL gate."""
from typing import Any, Iterator

from langgraph.types import Command

from agents.graph import get_graph
from observability.langfuse_setup import get_callback_handler

# Node execution order for progress reporting in the UI. Some runs skip stages
# (e.g. a "decline" route jumps straight to response) — the UI treats reaching
# "response" as 100% regardless of how many of these fired.
STAGE_ORDER = [
    "planner",
    "schema_linking",
    "sql_generation",
    "hitl_gate",
    "execution",
    "governance",
    "response",
]


def _config(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    handler = get_callback_handler()
    if handler:
        config["callbacks"] = [handler]
        config["metadata"] = {"langfuse_session_id": thread_id}
    return config


def start_question(question: str, thread_id: str) -> dict:
    """Runs the graph until completion or an HITL interrupt. Returns the raw
    invoke() result — check for the "__interrupt__" key to detect a pause."""
    graph = get_graph()
    return graph.invoke({"question": question}, config=_config(thread_id))


def resume_with_decision(thread_id: str, approved: bool) -> dict:
    graph = get_graph()
    return graph.invoke(Command(resume={"approved": approved}), config=_config(thread_id))


def stream_start_question(question: str, thread_id: str) -> Iterator[dict[str, Any]]:
    """Node-by-node version of start_question for progress reporting. Each yielded
    chunk is {node_name: partial_state} or {"__interrupt__": (Interrupt(...),)}."""
    graph = get_graph()
    yield from graph.stream({"question": question}, config=_config(thread_id), stream_mode="updates")


def stream_resume_with_decision(thread_id: str, approved: bool) -> Iterator[dict[str, Any]]:
    graph = get_graph()
    yield from graph.stream(
        Command(resume={"approved": approved}), config=_config(thread_id), stream_mode="updates"
    )


def get_current_state(thread_id: str) -> dict:
    """Full accumulated state for a thread, read from the checkpointer — used after
    a stream_* generator is exhausted to get the complete final state."""
    graph = get_graph()
    return graph.get_state(_config(thread_id)).values


def run_question_auto_approve(question: str, thread_id: str) -> dict:
    """Convenience path for the evaluation harness: auto-approves any HITL interrupt
    so golden-set runs don't hang waiting on a human."""
    result = start_question(question, thread_id)
    while "__interrupt__" in result:
        result = resume_with_decision(thread_id, approved=True)
    return result
