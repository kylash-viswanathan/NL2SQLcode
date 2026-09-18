"""Planner agent: classifies whether the question is an in-domain data question we
should attempt to answer via SQL, or something we should decline (out of scope for
the wealth & portfolio management sample DB)."""
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.state import GraphState

SYSTEM_PROMPT = """You are the routing planner for a wealth & portfolio management \
NL2SQL assistant. The database covers clients, portfolios, holdings, trades, and \
assets (tickers), including sensitive client fields like SSN, account number, and \
contact info. Decide whether the user's question can plausibly be answered by \
querying this database.

Questions asking for sensitive/PII fields (e.g. a client's SSN or account number) \
ARE in scope — a separate downstream human-review gate handles access control and \
masking for those, so you should NOT decline a question just because it touches \
sensitive data.

Respond with exactly one word: "generate" if the question is answerable via SQL \
against this domain, or "decline" only if it is truly out of scope (e.g. unrelated \
small talk, requests to modify/delete data, or questions about data this database \
doesn't contain at all)."""


def planner_node(state: GraphState) -> GraphState:
    llm = get_llm()
    result = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=state["question"])]
    )
    route = result.content.strip().lower()
    return {"route": "generate" if "generate" in route else "decline"}
