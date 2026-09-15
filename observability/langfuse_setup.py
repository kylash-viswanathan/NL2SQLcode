"""Langfuse Cloud (free tier) wiring: every LangGraph run is traced end-to-end, and
DeepEval scores get attached to the originating trace rather than living separately.

Targets Langfuse Python SDK v3+ (OpenTelemetry-based): `langfuse.langchain.CallbackHandler`
for LangGraph/LangChain tracing, `Langfuse.create_score` for attaching eval scores.
"""
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from config.settings import settings

_client = None


def _configured() -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def get_langfuse_client() -> Langfuse | None:
    global _client
    if not _configured():
        return None
    if _client is None:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _client


def get_callback_handler(session_id: str | None = None) -> CallbackHandler | None:
    """Returns a LangChain/LangGraph-compatible callback handler, or None if Langfuse
    keys aren't configured (observability is optional, not a hard dependency for the demo)."""
    client = get_langfuse_client()
    if client is None:
        return None
    return CallbackHandler()


def score_trace(trace_id: str, name: str, value: float, comment: str | None = None) -> None:
    client = get_langfuse_client()
    if client is None:
        return
    client.create_score(trace_id=trace_id, name=name, value=value, comment=comment)
