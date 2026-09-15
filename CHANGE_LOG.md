# Change Log — Index

## 🏷 Milestone: MVP 1.0 — 2026-09-15 (end of day)

First reference snapshot of the working MVP prototype: all four architecture layers
wired end-to-end (Turso sample DB → ChromaDB RAG → LangGraph multi-agent generation
with HITL gate and self-healing retries → DeepEval golden-set scoring + governance
masking), Chainlit UI with live per-stage progress and a collapsible schema/sample-
question side panel, running locally on a Python 3.12 project venv. 12/12 DeepEval
golden-set tests passing at this point. Tagged in git as `mvp-1.0`.

Not yet in this version (picked up next session): the Critic/Evaluation Agent
(currently only a proposed/NEW node in `Project Documents/Agent_Orchestration_Flow.md`)
and wiring Langfuse tracing into the live app (`observability/langfuse_setup.py`
exists but isn't exercised by a configured Langfuse project yet).

The change log is split into two documents so business/product history and
infra/troubleshooting history can be scanned independently:

- **[CHANGE_LOG_FEATURES.md](CHANGE_LOG_FEATURES.md)** — business, architecture, and
  feature-level changes: scope decisions, agent behavior, data/domain design, prompt
  and quality fixes.
- **[CHANGE_LOG_INFRA.md](CHANGE_LOG_INFRA.md)** — infrastructure, environment, and
  troubleshooting: dependency/version issues, external-service (Turso/Langfuse/OpenAI)
  connectivity problems, local run/deploy issues.

When logging a new change, add it to whichever of the two documents it belongs to
(both are chronological, dated entries).
