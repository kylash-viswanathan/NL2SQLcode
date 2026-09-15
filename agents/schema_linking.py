"""Schema-Linking agent: retrieves the relevant schema, exemplars, and glossary
terms for the question from ChromaDB (Layer 2)."""
from agents.state import GraphState
from knowledge.retrieval import retrieve_exemplars, retrieve_glossary, retrieve_schema


def schema_linking_node(state: GraphState) -> GraphState:
    question = state["question"]
    return {
        "retrieved_schema": retrieve_schema(question),
        "retrieved_exemplars": retrieve_exemplars(question),
        "retrieved_glossary": retrieve_glossary(question),
    }
