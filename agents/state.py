"""Shared LangGraph state schema threaded through every agent node."""
from typing import Any, Optional, TypedDict


class GraphState(TypedDict, total=False):
    question: str

    # Layer 2 retrieval (populated by schema_linking)
    retrieved_schema: list[str]
    retrieved_exemplars: list[dict]
    retrieved_glossary: list[dict]

    # Layer 3 generation
    route: str
    sql: str
    sql_tables: list[str]
    retry_count: int
    last_error: Optional[str]

    # HITL gate
    hitl_required: bool
    hitl_reason: Optional[str]
    hitl_approved: Optional[bool]

    # Execution
    execution_columns: list[str]
    execution_rows: list[list[Any]]
    execution_error: Optional[str]

    # Governance (Layer 4)
    masked_columns: list[str]
    masked_rows: list[list[Any]]

    # Response
    response: str
