"""Shared LLM client for all generation-layer agents."""
from langchain_openai import ChatOpenAI

from config.settings import settings

_llm = None


def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.generation_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )
    return _llm
