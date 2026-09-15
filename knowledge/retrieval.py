"""Retrieval helpers used by the Schema-Linking agent (Layer 2 -> Layer 3)."""
from knowledge.chroma_client import get_chroma_client, get_embedding_function


def retrieve_schema(question: str, top_k: int = 8) -> list[str]:
    client = get_chroma_client()
    collection = client.get_or_create_collection("schema", embedding_function=get_embedding_function())
    result = collection.query(query_texts=[question], n_results=top_k)
    return result["documents"][0] if result["documents"] else []


def retrieve_exemplars(question: str, top_k: int = 3) -> list[dict]:
    client = get_chroma_client()
    collection = client.get_or_create_collection("exemplars", embedding_function=get_embedding_function())
    result = collection.query(query_texts=[question], n_results=top_k)
    if not result["documents"]:
        return []
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    return [{"question": d, "sql": m["sql"]} for d, m in zip(docs, metas)]


def retrieve_glossary(question: str, top_k: int = 5) -> list[dict]:
    client = get_chroma_client()
    collection = client.get_or_create_collection("glossary", embedding_function=get_embedding_function())
    result = collection.query(query_texts=[question], n_results=top_k)
    if not result["documents"]:
        return []
    metas = result["metadatas"][0]
    return [{"term": m["term"], "maps_to": m["maps_to"]} for m in metas]
