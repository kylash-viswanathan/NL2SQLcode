# TrustQuery AI

A multi-agent NL2SQL prototype: business users ask questions about enterprise
data in plain English and get accurate, governed answers — without waiting on
a data team, and without compromising on data security or human oversight.

**Status**: MVP Phase 0, tagged `v2.0`. Local demo only (Chainlit UI, run on
your machine) — see [Status](#status) below.

## What it does

- **NL → SQL** over a sample wealth & portfolio management database (clients,
  portfolios, holdings, trades, assets), grounded in retrieved schema,
  exemplars, and a business glossary — not a full-schema-in-every-prompt approach.
- **HITL gate**: any generated query touching a PII/confidential-tagged
  column pauses for human approve/reject before it runs.
- **Critic/Evaluation agent**: an LLM-as-judge check that the final answer
  actually and faithfully answers the question — orthogonal to the HITL gate
  (access control vs. quality control). Self-heals via a bounded retry loop.
- **Governance masking**: PII columns are masked in every result set,
  independent of HITL outcome.
- **Full tracing**: every run is traced end-to-end in Langfuse, with PII
  redacted before export and DeepEval correctness scores attached to the
  exact trace that produced them.

## Architecture at a glance

Four layers, plus a Critic agent added on top of the original design:

1. **Ingestion** — crawls the sample DB schema, tags sensitive columns.
2. **Knowledge & RAG** — embeds schema/exemplars/glossary into ChromaDB.
3. **Multi-agent generation** — Planner → Schema-Linking → SQL Generation →
   HITL Gate → Execution (self-healing retry) → Governance → **Critic** →
   Response, orchestrated as a LangGraph `StateGraph`.
4. **Validation & evaluation** — the live Critic agent, plus DeepEval scoring
   offline against a golden question set.

Full use-case flow diagram (swimlanes per agent, separate lanes for LLM/HITL
calls, offline eval loop kept separate): [`Project Documents/Agent_Orchestration_Flow.md`](Project%20Documents/Agent_Orchestration_Flow.md).

## Tech stack

| Component | Choice |
|---|---|
| Sample DB | Turso (libSQL), free tier |
| Vector store | ChromaDB (local, embedded) |
| LLM | OpenAI `gpt-4.1-mini` (generation + judging), `text-embedding-3-small` (embeddings) |
| Orchestration | LangGraph `StateGraph`, interrupt/resume for HITL |
| Evaluation | DeepEval (offline golden-set scoring) + a live Critic agent |
| Observability | Langfuse Cloud (free tier) — full tracing, PII-masked on export |
| UI | Chainlit, run locally |

Everything is free-tier or self-hosted except the OpenAI API calls, which are
low-cost, deterministic (temperature 0), and tracked per-query in Langfuse.

## Project structure

```
NL2SQLcode/
  config/          # settings.py (.env loader), sensitivity_tags.yaml
  data/            # sample DB schema + seed data
  ingestion/       # schema crawler, Turso client
  knowledge/       # exemplars/glossary, Chroma index build + retrieval
  agents/          # Planner, Schema-Linking, SQL Generation, HITL Gate,
                   #   Execution, Critic, Response — wired in graph.py
  governance/      # result-set PII masking
  observability/   # Langfuse client + tracing setup
  evaluation/      # golden_set.yaml + DeepEval test suite
  app.py           # Chainlit entrypoint
  Project Documents/  # original project plan/architecture docs + flow diagram
```

## Getting started

Requires **Python 3.12** in a project-local venv (Chainlit's event-loop
patch is incompatible with Python 3.14 — see `CLAUDE.md` for details).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt langchain

Copy-Item .env.example .env        # fill in OPENAI_API_KEY, TURSO_*, LANGFUSE_* (Langfuse optional)

.\.venv\Scripts\python.exe data\seed.py                    # create schema + load sample data into Turso
.\.venv\Scripts\python.exe -m ingestion.schema_crawler      # crawl schema metadata
.\.venv\Scripts\python.exe -m knowledge.build_index         # embed schema/exemplars/glossary into ChromaDB

.\.venv\Scripts\python.exe -m chainlit run app.py           # launch the local demo UI
.\.venv\Scripts\python.exe -m pytest evaluation\deepeval_tests.py -v  # score the golden set with DeepEval
```

## Status

Phase 0 success criteria — all met:

- ✅ End-to-end demo correctly answers the golden question set across all four layers
- ✅ HITL gate triggers on seeded high-risk (PII-touching) queries
- ✅ DeepEval scores are visible in Langfuse, attached to their originating trace

**Explicitly out of scope for this build**: automated/nightly schema
crawling, self-hosted Langfuse, DSPy/fine-tuning optimization, production UI,
multi-source connectors, cloud hosting of the Chainlit UI. See `CLAUDE.md`
for the full list and what's sequenced into later phases.

## Future scope (per the project plan)

This build is Phase 0 only. Later phases, per `Project Documents/TrustQuery_AI_Project_Plan.docx`:

- **Phase 1 — Validation, governance & HITL hardening**: tune HITL thresholds on
  real signal, expand PII governance rules, grow the golden set to 100+
  questions. Target: ≥85% DeepEval composite accuracy, 100% of tagged
  sensitive columns auto-masked, HITL false-positive rate <5%.
- **Phase 2 — Pilot with real users**: roll out to one business unit,
  instrument a feedback loop, run the first DSPy/fine-tuning optimization
  cycle (deployed via MLflow). Target: pilot user satisfaction ≥4/5, median
  latency <10s, HITL false-positive rate <10%.
- **Phase 3 — Production hardening & scale**: multi-source connectors, cost
  monitoring dashboards, security/compliance review, runbooks, and a
  production UI replacing Chainlit (native Bedrock Agents chat UI or a
  custom UI on API Gateway); directional evaluation of Amazon Bedrock
  AgentCore as a hosting option.

Also flagged during this build, not in the original plan but natural
follow-ons: automating the offline DeepEval → SME-curation → golden-set-update
loop (currently just the design in the orchestration diagram), and unifying
the live Critic agent's judgment with DeepEval's `GEval` metric so "what
counts as correct" is defined in one place instead of two independent judges.

## Docs

- [`CLAUDE.md`](CLAUDE.md) — full architecture, tech stack rationale, and design decisions
- [`CHANGE_LOG_FEATURES.md`](CHANGE_LOG_FEATURES.md) / [`CHANGE_LOG_INFRA.md`](CHANGE_LOG_INFRA.md) — build history
- [`Project Documents/`](Project%20Documents/) — original project plan, architecture doc, and the agent orchestration flow diagram
