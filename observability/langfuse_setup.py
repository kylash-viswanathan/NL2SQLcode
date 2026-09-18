"""Langfuse Cloud (free tier) wiring: every LangGraph run is traced end-to-end, and
DeepEval scores get attached to the originating trace rather than living separately.

Targets Langfuse Python SDK v3+ (OpenTelemetry-based): `langfuse.langchain.CallbackHandler`
for LangGraph/LangChain tracing, `Langfuse.create_score` for attaching eval scores.

IMPORTANT — import ordering: this module must be imported AFTER `config.settings` has
loaded `.env` (it is — `config.settings` is imported below) and its `get_langfuse_client()`
must run BEFORE any `CallbackHandler()` is constructed, since `mask_otel_spans` is
registered on this module's `Langfuse` client instance and the callback handler resolves
that same client. `get_callback_handler()` below already enforces this ordering.
"""
import re
from typing import Optional

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanPatch

from config.settings import settings

_client = None

# PII patterns redacted from every span exported to Langfuse — a stricter, defense-in-
# depth bar than the app's own governance masking (which only masks columns tagged
# PII in results), since this data is leaving the app for a third-party SaaS trace
# store. Matches the sample data's own formats: SSN "123-45-6789", account numbers
# "ACC-100234", plus generic email/phone patterns for any other client PII that ends
# up in a prompt, tool arg, or query result.
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_ACCOUNT_RE = re.compile(r"\bACC-\d{4,}\b")
_EMAIL_RE = re.compile(r"\b[\w.-]+?@[\w.-]+?\.\w+?\b")
_PHONE_RE = re.compile(r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")


def _redact(value: str) -> str:
    redacted = _SSN_RE.sub("***MASKED-SSN***", value)
    redacted = _ACCOUNT_RE.sub("***MASKED-ACCOUNT***", redacted)
    redacted = _EMAIL_RE.sub("***MASKED-EMAIL***", redacted)
    redacted = _PHONE_RE.sub("***MASKED-PHONE***", redacted)
    return redacted


def should_export_span(span) -> bool:
    """Drops LangGraph's internal conditional-edge routing functions (e.g.
    route_after_execution) from the exported trace — they're pure control-flow
    glue, not application steps a reviewer needs to see, and otherwise clutter
    every trace tree with one extra node per branch (see Langfuse best practices:
    https://langfuse.com/docs/observability/best-practices, "Is there noise you
    don't need?")."""
    return not span.name.startswith("route_after_")


def mask_otel_spans(*, params: MaskOtelSpansParams) -> Optional[MaskOtelSpansResult]:
    """Redacts PII patterns from every OpenTelemetry span attribute before export to
    Langfuse. Runs for every span this client exports, regardless of whether it came
    from the LangGraph/LangChain integration or elsewhere."""
    patches = {}
    for identifier, span in params.spans.items():
        replacements = {}
        for key, value in span.attributes.items():
            if isinstance(value, str):
                redacted = _redact(value)
                if redacted != value:
                    replacements[key] = redacted
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches)


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
            mask_otel_spans=mask_otel_spans,
            should_export_span=should_export_span,
        )
    return _client


def get_callback_handler() -> CallbackHandler | None:
    """Returns a LangChain/LangGraph-compatible callback handler, or None if Langfuse
    keys aren't configured (observability is optional, not a hard dependency for the
    demo). Must call get_langfuse_client() first so mask_otel_spans is registered on
    the client this handler resolves to."""
    client = get_langfuse_client()
    if client is None:
        return None
    return CallbackHandler()


def score_trace(trace_id: str, name: str, value: float, comment: str | None = None) -> None:
    client = get_langfuse_client()
    if client is None:
        return
    client.create_score(trace_id=trace_id, name=name, value=value, comment=comment)


def flush() -> None:
    """Blocks until all buffered spans/scores are sent. Required in short-lived
    processes (scripts, pytest runs) — the SDK otherwise batches and flushes on its
    own schedule, which a process can exit before reaching."""
    client = get_langfuse_client()
    if client is not None:
        client.flush()
