"""SQL Generation agent: writes a SELECT query grounded in the schema, exemplars,
and glossary terms retrieved by the Schema-Linking agent. Also serves as the target
of the self-healing retry loop when execution fails."""
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.sql_safety import extract_tables, is_select_only, strip_sql_fences
from agents.state import GraphState

SYSTEM_PROMPT = """You are a SQL generation agent for a wealth & portfolio management \
database (SQLite dialect, via Turso). Given a natural-language question, retrieved \
schema context, few-shot exemplars, and business glossary terms, write a single \
read-only SELECT query that answers the question.

Rules:
- Only ever write SELECT statements. Never write INSERT, UPDATE, DELETE, DROP, or DDL.
- Use only tables/columns that appear in the retrieved schema context.
- Return ONLY the raw SQL, no markdown fences, no explanation.
"""


def _build_context(state: GraphState) -> str:
    parts = ["Retrieved schema context:"]
    parts.extend(f"- {s}" for s in state.get("retrieved_schema", []))

    exemplars = state.get("retrieved_exemplars", [])
    if exemplars:
        parts.append("\nSimilar question/SQL exemplars:")
        for ex in exemplars:
            parts.append(f"- Q: {ex['question']}\n  SQL: {ex['sql']}")

    glossary = state.get("retrieved_glossary", [])
    if glossary:
        parts.append("\nRelevant business glossary terms:")
        for g in glossary:
            parts.append(f"- {g['term']} -> {g['maps_to']}")

    if state.get("last_error"):
        parts.append(
            f"\nThe previous attempt failed with this database error — fix the query:\n{state['last_error']}\nPrevious SQL: {state.get('sql', '')}"
        )

    return "\n".join(parts)


def sql_generation_node(state: GraphState) -> GraphState:
    llm = get_llm()
    context = _build_context(state)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Question: {state['question']}\n\n{context}"),
    ]
    result = llm.invoke(messages)
    sql = strip_sql_fences(result.content)

    if not is_select_only(sql):
        return {
            "sql": sql,
            "sql_tables": [],
            "execution_error": "Generated statement was not a read-only SELECT; blocked by guardrail.",
        }

    return {"sql": sql, "sql_tables": extract_tables(sql), "execution_error": None}
