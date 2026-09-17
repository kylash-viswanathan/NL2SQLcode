# TrustQuery AI — MVP Prototype (Phase 0)

## What this project is

TrustQuery AI is a multi-agent NL2SQL system that lets business users ask questions about enterprise data in plain English and get accurate, governed answers — without waiting on a data team and without compromising on data security or human oversight. Full context lives in `Project Documents/TrustQuery_AI_Project_Plan.docx` and `Project Documents/TrustQuery_AI_Architecture.docx`.

This file scopes **Phase 0 only**: a 2-week MVP prototype that builds all four architecture layers end-to-end on a sample database, demoed through a local Chainlit UI. Hardening, production hosting decisions, and broader business-stakeholder integration are explicitly out of scope here and land in later phases.

## Architecture — four layers + cross-cutting concerns

1. **Ingestion & parsing** — connects to the source DB, crawls schema metadata, tags sensitive columns (PII/confidential/public) before anything downstream touches them.
2. **Knowledge & RAG** — embeds schema descriptions, few-shot query exemplars, and business glossary terms into a vector store so SQL generation is grounded without stuffing the full schema into every prompt.
3. **Multi-agent generation** — Planner → Schema-Linking → SQL Generation → HITL Gate → Execution (with bounded self-healing retries) → Response, orchestrated as a graph with explicit state and interrupt/resume support.
4. **Validation & evaluation** — a Critic/Evaluation agent verifies the final result faithfully answers the question (orthogonal to the HITL gate — see below), DeepEval scores query correctness offline against a golden set, governance independently masks sensitive data in every result set, and (post-MVP) an optimization step decides when prompt/fine-tuning is warranted.

**Cross-cutting**: orchestration (LangGraph), guardrails at every layer, observability (traces + eval scores in one place), and human-in-the-loop review — none of these are bolted on after the fact.

## Tech stack (MVP, free-tier / Python-first)

| Layer | Component | Choice |
|---|---|---|
| 1. Ingestion | Sample DB | Turso (`libsql-client`), free tier |
| 1 | Schema crawler | Python script over `sqlite_master` / `PRAGMA table_info` |
| 1 | Sensitivity tagging | Static `config/sensitivity_tags.yaml` (`table.column → PII/confidential/public`) |
| 2. Knowledge & RAG | Vector store | ChromaDB `PersistentClient` (local, embedded) |
| 2 | Embeddings | OpenAI `text-embedding-3-small` |
| 2 | Exemplars / glossary | YAML, embedded at index-build time |
| 3. Generation | Orchestration | LangGraph `StateGraph` |
| 3 | LLM | OpenAI `gpt-4.1-mini`, temperature 0, via `langchain-openai` |
| 3 | HITL gate | Rule-based: triggers when generated SQL touches a PII/confidential-tagged column (`sqlparse` + tag config) |
| 3 | Execution | `libsql-client` + bounded self-healing retry (max 2) on failure |
| 4. Validation | Critic / Evaluation agent | LLM-as-judge (`gpt-4.1-mini`) faithfulness check on the masked result vs. the question, runs post-Governance, pre-Response. Orthogonal to the HITL gate — see below |
| 4. Validation | Eval | DeepEval, custom metric(s) against a 10–15 question golden set |
| 4 | Observability | Langfuse Cloud (free tier) — traces + DeepEval scores on one timeline |
| 4 | Governance | Deterministic masking of PII-tagged columns in every result set, independent of HITL outcome |
| 4 | Optimization agent | Out of scope for MVP — deferred to Phase 1 (DSPy / PEFT-LoRA) |
| Cross-cutting | Guardrails | Sensitivity tags (L1) + schema-scoped retrieval (L2) + SELECT-only execution check (L3) + masking (L4) |
| Cross-cutting | UI | Chainlit, run locally (`chainlit run app.py`); HITL approve/reject as Chainlit action buttons |

**UI conveniences**: while a question runs, a `TaskList` + progress bar show live per-agent-stage progress as `NN% (PhaseWord)` (Planning → Retrieving → Generating → Reviewing → Executing → Masking → Responding), driven by streaming the LangGraph run (`agents.runner.stream_start_question` / `stream_resume_with_decision`, `stream_mode="updates"`) instead of a single blocking `invoke()`. The welcome message has a collapsible side-panel element ("Sample Schema", `cl.Text(..., display="side")`) with the full schema (table/column/sensitivity, from `ingestion/schema_metadata.json`) and the sample-question list (from `evaluation/golden_set.yaml`). No clickable starter cards or settings-panel dropdown — both were tried and didn't render reliably in this Chainlit version; picking a sample question is copy/paste from the side panel for now.

**Langfuse tracing** (`observability/langfuse_setup.py`, wired into every graph call via `agents/runner.py`): uses the `langfuse.langchain.CallbackHandler` framework integration (per the [Langfuse AI Skill](https://github.com/langfuse/skills), installed as a project skill at `.claude/skills/langfuse/`) — model name, token usage, and generation/chain observation types are captured automatically, no manual instrumentation. On top of the integration:
- **PII masking on export** (`mask_otel_spans`): regex-redacts SSN, account-number, email, and phone patterns from every span attribute before it leaves the app for Langfuse Cloud — stricter than the app's own governance masking, since this data is going to a third-party SaaS. Verified via the Observations API that raw `execution_rows` (which briefly hold unmasked PII between Execution and Governance) show up redacted in the actual exported trace.
- **Noise filtering** (`should_export_span`): drops LangGraph's internal `route_after_*` conditional-edge functions from the trace tree — pure control-flow glue, not something a reviewer needs to see.
- **Sessions**: `propagate_attributes(session_id=thread_id)` groups a HITL pause + resume into one Langfuse session (two traces, one session) — matches Langfuse's own guidance for "workflow spans multiple requests with human-in-the-loop steps in between."
- **Trace names**: `answer-nl2sql-question` / `resume-hitl-review` — verb-first, low-cardinality, per Langfuse's naming best practices (no dynamic values in the name itself).
- **Flush**: `evaluation/deepeval_tests.py` flushes at pytest session teardown (short-lived process — the SDK's background batching can otherwise lose buffered spans on exit); Chainlit flushes on `on_chat_end`.
- **DeepEval scores attached to their trace**: `evaluation/deepeval_tests.py::_run_scored()` pre-generates a trace ID (`client.create_trace_id()`) and runs the graph inside `client.start_as_current_observation(as_type="evaluator", trace_context={"trace_id": ...})` so the ID is still known after the trace closes; `correctness_metric.measure(test_case)` (called directly, not via `assert_test`, to get `.score`/`.reason`) and the HITL/masking check both push their result to that exact trace via `score_trace()`. Verified via the Scores and Observations APIs: each `deepeval-correctness`/`deepeval-hitl-masking` score's `subject.id` matches a trace whose observation tree is the full LangGraph run (Planner through Response, including the Critic). This closes out the third Phase 0 success criterion below ("DeepEval scores are visible in Langfuse for every run") — previously `score_trace()` existed but was never called anywhere.

**Critic / Evaluation agent** (`agents/critic.py`), added Phase 0 post-MVP-1.0: sits between Governance and Response in the graph. Deliberately orthogonal to the HITL gate — HITL asks "is a human allowed to let this query touch this data?" (access control, on column sensitivity, decided by a human, **pre**-execution); the Critic asks "is this actually a correct answer to the question?" (quality control, on faithfulness, decided by an LLM judge, **post**-execution — it needs the real result set to judge against). A query can be sensitive-and-correct, sensitive-and-wrong (HITL alone can't catch this), or non-sensitive-and-wrong (the Critic is the only safety net). On failure the Critic routes back to SQL Generation, **sharing** Execution's `retry_count`/`max_self_heal_retries` budget rather than tracking a separate counter (one shared "how many times has the graph retried this question" limit, decided deliberately for v1 simplicity). If retries are exhausted and the Critic still fails, the answer still goes out — `agents/response.py` prepends a "could not be fully verified" caveat rather than blocking. The Critic auto-passes (no LLM call) when `execution_error` is already set (a HITL rejection or an already-exhausted execution retry) — nothing for it to judge in that case. It does *not* consume the golden set (`evaluation/golden_set.yaml`) directly — that stays DeepEval's offline job; see `Project Documents/Agent_Orchestration_Flow.md` for the full proposed offline-loop design, now partially implemented (the Critic; the offline DeepEval→SME-curation→golden-set-update loop itself is still just the diagram, not built).

The Critic's judgment is a hand-written LLM-as-judge prompt (`agents/critic.py`), not built on any eval framework — it's a separate rubric from DeepEval's `GEval` correctness metric used offline in `evaluation/deepeval_tests.py`. **Post-MVP (Phase 1+) idea, deliberately deferred**: DeepEval's metric classes can be invoked directly (`GEval(...).measure(test_case)`) outside `pytest`, so the live Critic could reuse the exact same `correctness_metric` object as the offline golden-set scoring instead of maintaining two separate judge prompts that can drift out of sync over time — "what counts as correct" would then be defined in exactly one place, with the same rubric and threshold applied live and offline. Not done for MVP 1.x; the two judges today are independent and can diverge.

Everything is free-tier or self-hosted except the OpenAI API calls (generation + embeddings), which are low-cost, deterministic (temperature 0), and tracked per-query in Langfuse.

## Data domain

**Wealth & portfolio management**: `clients`, `portfolios`, `holdings`, `trades`, `assets` (ticker/instrument reference data). PII lives on `clients` (e.g. `ssn`, `account_number`, contact info); `holdings`/`trades`/`assets` are non-PII financial data joined against `portfolios`/`clients`. This gives a natural HITL trigger surface (any query touching `clients` PII columns) and supports a golden set spanning portfolio valuation, holdings breakdowns, and trade history questions.

## Project structure

```
NL2SQLcode/
  .env.example              # documents required env vars, no real values
  .gitignore
  requirements.txt
  CLAUDE.md
  config/
    settings.py              # loads .env
    sensitivity_tags.yaml    # table.column -> PII/confidential/public
  data/
    schema.sql                # DDL for the wealth & portfolio management domain
    seed.py                   # loads DDL + sample rows into Turso
  ingestion/
    schema_crawler.py         # introspects Turso, writes metadata
  knowledge/
    exemplars.yaml            # NL question -> SQL few-shot pairs
    glossary.yaml              # business term -> schema mapping
    build_index.py            # embeds schema/exemplars/glossary into Chroma
  agents/
    state.py                  # shared LangGraph state schema
    graph.py                  # wires Planner -> SchemaLinking -> SQLGen -> HITL -> Execution -> Governance -> Critic -> Response
    planner.py
    schema_linking.py
    sql_generation.py
    hitl_gate.py
    execution.py
    critic.py                 # LLM-as-judge faithfulness check, post-Governance
    response.py
  governance/
    masking.py                # applies sensitivity_tags.yaml masking to result sets
  observability/
    langfuse_setup.py         # Langfuse client init, LangGraph callback wiring
  evaluation/
    golden_set.yaml           # 10-15 NL question / expected SQL or result pairs
    deepeval_tests.py         # DeepEval test suite scoring against golden_set
  app.py                      # Chainlit entrypoint, drives the LangGraph graph incl. HITL UI
```

## Environment setup

Copy `.env.example` to `.env` and fill in real values — **never commit `.env` or hardcode keys in code**; everything is loaded via `python-dotenv`.

```
OPENAI_API_KEY=
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Running the MVP

**Python version**: this project runs on **Python 3.12** in a project-local virtual
environment (`.venv`), not the machine's global Python. Chainlit's `nest_asyncio`
event-loop patch is incompatible with `anyio`'s event-loop detection on Python 3.14
(`anyio._core._exceptions.NoEventLoopError`) — an upstream library issue, not fixable
in this codebase. Python 3.12 was installed side-by-side via `winget install
Python.Python.3.12` without changing the machine's default `python`/`py` (still 3.14).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt langchain

Copy-Item .env.example .env        # fill in OPENAI_API_KEY, TURSO_*, LANGFUSE_* (Langfuse optional)

.\.venv\Scripts\python.exe data\seed.py                    # creates schema + loads sample data into Turso
.\.venv\Scripts\python.exe -m ingestion.schema_crawler      # crawls Turso, writes ingestion/schema_metadata.json
.\.venv\Scripts\python.exe -m knowledge.build_index         # embeds schema/exemplars/glossary into ChromaDB

.\.venv\Scripts\python.exe -m chainlit run app.py           # launches the local demo UI
.\.venv\Scripts\python.exe -m pytest evaluation\deepeval_tests.py -v  # scores the golden set with DeepEval
```

Runs locally only for the MVP. Hosting on Hugging Face Spaces is planned for after the MVP is validated — not part of this build.

## Phase 0 success criteria

- End-to-end demo correctly answers ≥10–15 predefined questions against the Turso sample DB, touching all four layers
- HITL gate triggers in rule-based form on at least one seeded high-risk (PII-touching) query
- DeepEval scores are visible in Langfuse for every run

## Explicitly out of scope for this build

- Automated/nightly schema crawling (static tagging is enough for the MVP)
- Self-hosted Langfuse, Presidio-style NLP PII detection, DSPy/fine-tuning optimization
- Production UI, multi-source connectors, security/compliance review, cost dashboards
- Cloud hosting of the Chainlit UI (local only for now)

These are sequenced into Phase 1–3 per the Project Plan and should not be pulled forward into this MVP.
