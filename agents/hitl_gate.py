"""HITL Gate: rule-based check that pauses the graph (via LangGraph interrupt) when
the generated SQL touches a PII or confidential-tagged column, requiring a human
approve/reject decision before execution proceeds."""
from langgraph.types import interrupt

from agents.sql_safety import hitl_check
from agents.state import GraphState
from config.settings import hitl_trigger_columns


def hitl_gate_node(state: GraphState) -> GraphState:
    triggered, matched_columns = hitl_check(
        state["sql"], state.get("sql_tables", []), hitl_trigger_columns()
    )

    if not triggered:
        return {"hitl_required": False, "hitl_reason": None, "hitl_approved": True}

    reason = f"Query references sensitive column(s): {', '.join(matched_columns)}"

    decision = interrupt(
        {
            "type": "hitl_review",
            "question": state["question"],
            "sql": state["sql"],
            "reason": reason,
        }
    )

    return {
        "hitl_required": True,
        "hitl_reason": reason,
        "hitl_approved": bool(decision.get("approved", False)) if isinstance(decision, dict) else bool(decision),
    }
