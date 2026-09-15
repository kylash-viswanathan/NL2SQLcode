"""Shared ChromaDB persistent client + OpenAI embedding function."""
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from config.settings import settings

_client = None
_embed_fn = None


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return _client


def get_embedding_function():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key, model_name=settings.embedding_model
        )
    return _embed_fn
