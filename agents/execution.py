"""Execution agent: runs the approved SQL against Turso. Errors are surfaced back
into state so the graph can route into the bounded self-healing retry loop."""
from agents.state import GraphState
from ingestion.db import get_client


def execution_node(state: GraphState) -> GraphState:
    if state.get("hitl_required") and not state.get("hitl_approved"):
        return {
            "execution_error": "Query was rejected by the human reviewer and was not executed.",
            "execution_columns": [],
            "execution_rows": [],
        }

    client = get_client()
    try:
        result = client.execute(state["sql"])
        columns = list(result.columns) if result.columns else []
        rows = [list(row) for row in result.rows]
        return {"execution_columns": columns, "execution_rows": rows, "execution_error": None}
    except Exception as exc:  # noqa: BLE001 - surfaced to the self-heal loop, not swallowed
        return {
            "execution_error": str(exc),
            "execution_columns": [],
            "execution_rows": [],
            "retry_count": state.get("retry_count", 0) + 1,
            "last_error": str(exc),
        }
    finally:
        client.close()
