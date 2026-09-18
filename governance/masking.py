"""Governance layer (Layer 4): deterministically masks PII-tagged columns in every
result set, independent of whether the query was HITL-approved. This is the
graph node wired in between Execution and Response."""
from agents.state import GraphState
from config.settings import mask_columns

MASK_VALUE = "***MASKED***"


def apply_masking(columns: list[str], rows: list[list], tables: list[str]) -> tuple[list[str], list[list]]:
    to_mask = mask_columns()
    mask_positions = {
        i for i, col in enumerate(columns) if any(table in tables and col == c for table, c in to_mask)
    }
    if not mask_positions:
        return columns, rows

    masked_rows = [
        [MASK_VALUE if i in mask_positions else value for i, value in enumerate(row)] for row in rows
    ]
    return columns, masked_rows


def governance_node(state: GraphState) -> GraphState:
    if state.get("execution_error"):
        return {"masked_columns": [], "masked_rows": []}

    columns, rows = apply_masking(
        state.get("execution_columns", []),
        state.get("execution_rows", []),
        state.get("sql_tables", []),
    )
    return {"masked_columns": columns, "masked_rows": rows}
