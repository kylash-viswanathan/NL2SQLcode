# TrustQuery AI — Multi-Agent Orchestration Flow

Use-case flow for a single user query: vertical lanes are the agents/steps the
query moves through, left to right. Two horizontal lanes underneath the main
pipeline break out calls into cross-cutting resources — the LLM and the human
reviewer — so it's clear which steps reach outside the agent pipeline itself
and which stay purely internal. The offline DeepEval evaluation loop is a
separate diagram further down — it runs on its own schedule, independent of
any single query.

Rendered with [Mermaid](https://mermaid.js.org/) — displays natively on GitHub
and in VS Code (with the Mermaid preview extension).

## Live query flow

```mermaid
flowchart TB
    subgraph Pipeline["Agent Pipeline — vertical lanes, one per step, left to right"]
        direction LR
        User(["User"])
        Planner["Planner"]
        SchemaLinking["Schema-Linking<br/>(ChromaDB RAG)"]
        SQLGen["SQL Generation"]
        HITLGate{"HITL Gate<br/>(rule-based)"}
        Execution["Execution<br/>(Turso, self-heal)"]
        Governance["Governance<br/>(mask PII)"]
        Critic{{"Critic / Evaluation<br/>Agent"}}
        Response["Response"]

        User --> Planner --> SchemaLinking --> SQLGen --> HITLGate
        HITLGate --> Execution --> Governance --> Critic --> Response
        Response --> User
        Critic -. fails check, retry bounded .-> SQLGen
    end

    subgraph LLMLane["Horizontal lane — LLM calls (gpt-4.1-mini via OpenAI)"]
        direction LR
        LLM1["LLM: route question"]
        LLM2["LLM: write SQL"]
        LLM3["LLM: judge faithfulness"]
        LLM4["LLM: compose answer"]
    end

    subgraph HITLLane["Horizontal lane — Human-in-the-loop"]
        direction LR
        Human[["Human Reviewer<br/>(Approve / Reject)"]]
    end

    Planner -. calls .-> LLM1
    LLM1 -. returns route .-> Planner
    SQLGen -. calls .-> LLM2
    LLM2 -. returns SQL .-> SQLGen
    Critic -. calls .-> LLM3
    LLM3 -. returns verdict .-> Critic
    Response -. calls .-> LLM4
    LLM4 -. returns answer .-> Response

    HITLGate -. sensitive query .-> Human
    Human -. approve / reject .-> HITLGate
```

### Reading this diagram

- **Top lane (Pipeline)**: the actual sequence a query moves through, in
  order. Every step here runs inside the LangGraph process — no external
  calls happen unless a dashed line drops down to one of the two lanes below.
- **LLM lane**: four of the nine steps call out to the LLM — Planner (routes
  the question), SQL Generation (writes the query), Critic (judges the
  result), Response (composes the final answer). Schema-Linking, HITL Gate,
  Execution, and Governance do **not** call an LLM — they're retrieval, a
  rule-based check, a DB call, and deterministic masking, respectively.
- **HITL lane**: only the HITL Gate reaches into this lane, and only when the
  generated SQL touches a PII/confidential-tagged column. Every other step
  skips it entirely.
- **Retry loop**: the Critic is the only step with an edge going *backward*
  in the pipeline (back to SQL Generation) — bounded by the shared
  `retry_count`/`max_self_heal_retries` budget it shares with Execution's own
  self-heal retries on DB errors.

## Offline evaluation loop (separate — not part of the live query flow)

DeepEval scoring against the golden set is a manual/CI `pytest` run today
(`evaluation/deepeval_tests.py`), not something that fires per live query.
This diagram shows the target design for that loop; only the DeepEval-against-
golden-set part is built, everything downstream of it (auto-flagging from
production traces, SME curation, golden-set auto-update) is still proposed.

```mermaid
flowchart LR
    Traces["Production Traces<br/>(Langfuse)"] --> DeepEval["DeepEval<br/>(offline / batch evaluator)"]
    DeepEval -- flags regressions / candidates --> SME[["SME Curation"]]
    SME -- periodic update --> Golden[("Golden Set<br/>curated reference")]
```

**Status**: only `DeepEval` reading `golden_set.yaml` directly (manual/CI
`pytest` run) is implemented. `Traces → DeepEval` (DeepEval doesn't read
Langfuse traces today), `SME Curation`, and the auto-update of `Golden Set`
are all proposed, not built. The live Critic agent (see the diagram above)
does **not** read from `Golden Set` in this version — see `CLAUDE.md` for why
that's deferred.
