"""Response agent: turns the (masked) result set, or an error/decline message, into
a natural-language answer for the user."""
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.state import GraphState

SYSTEM_PROMPT = """You are the response agent for a wealth & portfolio management \
NL2SQL assistant. Given the user's question and a query result (or an error/decline \
message), write a concise, clear natural-language answer that directly and completely \
answers the question. If the result rows contain identifying items the question asked \
for (e.g. names, tickers), list them explicitly rather than just giving a count or a \
vague summary. Do not invent data that isn't present."""


def response_node(state: GraphState) -> GraphState:
    if state.get("route") == "decline":
        return {
            "response": "That question is outside what I can answer from the wealth & "
            "portfolio management database (clients, portfolios, holdings, trades, assets)."
        }

    if state.get("execution_error"):
        return {"response": f"I couldn't get an answer: {state['execution_error']}"}

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
    result = llm.invoke(messages)
    return {"response": result.content.strip()}
