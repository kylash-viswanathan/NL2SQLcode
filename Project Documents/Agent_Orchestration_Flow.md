# TrustQuery AI — Multi-Agent Orchestration Flow

Architectural flow between agents for a single user query, plus the offline
evaluation loop that keeps the golden reference set current. Rendered with
[Mermaid](https://mermaid.js.org/) — displays natively on GitHub and in VS Code
(with the Mermaid preview extension).

```mermaid
flowchart TB
    User([User]) --> Planner
    Planner --> SchemaLinking["Schema-Linking<br/>(ChromaDB RAG)"]
    SchemaLinking --> SQLGen["SQL Generation<br/>(gpt-4.1-mini)"]
    SQLGen --> HITL{"HITL Gate<br/>(rule-based)"}
    HITL -- sensitive query --> Human[["Human Reviewer<br/>(Approve / Reject)"]]
    Human -. decision .-> HITL
    HITL -- approved --> Execution["Execution<br/>(Turso, self-heal retry)"]
    Execution --> Governance["Governance<br/>(mask PII columns)"]
    Governance --> Critic{{"Critic / Evaluation Agent — NEW<br/>checks vs. golden exemplars"}}
    Critic -. fails check, retry bounded .-> SQLGen
    Critic -- pass --> Response
    Response --> User

    subgraph Offline["Offline / Periodic Evaluation Loop (nightly batch or CI-triggered)"]
        direction LR
        Traces["Production Traces<br/>(Langfuse)"] --> DeepEval["DeepEval<br/>(offline / batch evaluator)"]
        DeepEval -- flags regressions / candidates --> SME[["SME Curation"]]
        SME -- periodic update --> Golden[("Golden Set<br/>curated reference")]
    end

    Response -. logs .-> Traces
    Golden -. reference exemplars and thresholds, read at runtime .-> Critic
```

## Legend

- **Solid arrows** — live, per-query path through the agent graph.
- **Dashed arrows** — the HITL branch, or offline/periodic flow.
- **Critic / Evaluation Agent** — not yet implemented in the MVP graph; shown as
  the natural place for a runtime self-check against the golden set, distinct
  from DeepEval's offline scoring.

## How the golden set actually gets updated

DeepEval does **not** write to the golden set directly — it scores production
traces against the *existing* golden set and flags regressions or candidate
new examples. An SME then reviews those flags and curates the update. That
refreshed golden set is what the (proposed) Critic/Evaluation Agent would read
from at runtime — DeepEval and the Critic Agent both consume the same golden
set, but on different cadences (periodic/offline vs. every query).
