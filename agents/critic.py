"""Critic / Evaluation Agent: an LLM-as-judge check that verifies the final
(masked) result set actually and faithfully answers the user's question before
it reaches the Response agent.

This is deliberately orthogonal to the HITL Gate: HITL asks "is a human allowed
to let this query touch this data?" (access control, on column sensitivity,
decided by a human, pre-execution). This agent asks "is this actually a correct
answer to the question?" (quality control, on faithfulness, decided by an LLM
judge, post-execution — it needs the real result set to judge against).

On failure, routes back to SQL Generation for a bounded retry. Shares the same
retry budget as Execution's self-healing loop (agents.execution) rather than
tracking a separate counter — one shared "how many times has the graph retried
this question" limit. If retries are exhausted and the critic still fails, the
answer still goes out (agents.response adds a caveat) rather than blocking.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.state import GraphState

SYSTEM_PROMPT = """You are a critic agent verifying a wealth & portfolio management \
NL2SQL assistant's answer before it is shown to the user. Given the user's question, \
the SQL that was run, and the resulting (possibly masked) result set, judge whether \
the result set faithfully and completely supports answering the question.

Respond with exactly one line, in one of these two forms:
PASS
FAIL: <one-sentence reason>

Rules:
- FAIL if the result set is empty when the question implies matching data should \
exist, if the columns/rows returned don't match what the question actually asked \
for, or if the SQL clearly answers a different question than the one asked.
- PASS if values are masked (e.g. contain ***MASKED-...***) as long as the right \
columns were selected for the question — masking is expected governance behavior, \
not a defect to flag.
- Judge only whether the result answers the question. Do not judge SQL style, \
efficiency, or phrasing of a hypothetical final response."""


def critic_node(state: GraphState) -> GraphState:
    if state.get("execution_error"):
        # Nothing to verify: the query was rejected by a reviewer, or execution
        # failed and self-heal retries are already exhausted — response.py handles
        # surfacing that error directly, the critic has no result set to judge.
        return {"critic_passed": True, "critic_reason": None}

    llm = get_llm()
    columns = state.get("masked_columns", [])
    rows = state.get("masked_rows", [])
    table_text = f"Columns: {columns}\nRows: {rows}" if columns else "No rows returned."

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"Question: {state['question']}\nSQL: {state.get('sql', '')}\n{table_text}"
        ),
    ]
    verdict = llm.invoke(messages).content.strip()

    if verdict.upper().startswith("PASS"):
        return {"critic_passed": True, "critic_reason": None}

    reason = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict
    return {
        "critic_passed": False,
        "critic_reason": reason,
        "retry_count": state.get("retry_count", 0) + 1,
        "last_error": f"A quality check flagged this result: {reason}",
    }
