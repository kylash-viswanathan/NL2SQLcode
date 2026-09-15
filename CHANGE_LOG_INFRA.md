# Change Log — Infrastructure & Troubleshooting

Environment setup, dependency/version issues, external-service (Turso/Langfuse/OpenAI)
connectivity problems, and local run/deploy troubleshooting for the TrustQuery AI MVP
prototype, in chronological order. For product/architecture/feature/prompt changes,
see `CHANGE_LOG_FEATURES.md`.

## 2026-09-15 — Turso connectivity & auth

- **`libsql-client` package unreliable**: the package's WebSocket path failed the Hrana handshake against Turso's edge (`400 Invalid response status`), and its HTTP path raised `KeyError: 'result'` on Turso's current response shape for DDL/DML statements. Replaced it entirely: `ingestion/db.py` now talks directly to Turso's documented `v2/pipeline` HTTP API via `requests`. Dropped `libsql-client` from `requirements.txt`, added `requests`.
- **Turso auth token confusion**: user had pasted a Turso *platform API* token (management-API scopes: `db:create`, `db:delete`, `group:configure`, …) instead of a *database* token (used to authenticate queries) — different signing keys, causing `401 invalid JWT token: can't be decoded with any of the existing keys`. Diagnosed by decoding the JWT payload (no secret needed) to inspect its `scopes` claim. Resolved by regenerating a proper database token with read/write access.

## 2026-09-15 — Langfuse & DeepEval SDK version drift

- **Langfuse v4 SDK**: pip resolved `langfuse==4.15.2` (OTel-based), not the v2-era API the code was originally written against. Updated `observability/langfuse_setup.py`:
  - `langfuse.callback.CallbackHandler` → `langfuse.langchain.CallbackHandler` (also requires plain `langchain` installed, not just `langchain-core`/`langchain-openai` — added `langchain` to `requirements.txt`).
  - `Langfuse.score(...)` → `Langfuse.create_score(...)`.
  - Session id is now passed via LangChain run config metadata (`{"metadata": {"langfuse_session_id": thread_id}}`) rather than the handler constructor; updated `agents/runner.py` accordingly.
  - Bumped `langfuse>=2.50.0` → `langfuse>=3.0.0` in `requirements.txt` to reflect the v3+ API surface actually in use.
- **DeepEval default judge model unavailable**: DeepEval's default GEval judge model (`gpt-5.4`) isn't available on this OpenAI project (`403 model_not_found`). Pinned the judge to `settings.generation_model` (`gpt-4.1-mini`) in `evaluation/deepeval_tests.py`.

## 2026-09-15 — Local Chainlit run attempts (Python 3.14)

- **Port 8000 already in use**: a leftover `python.exe` process from an earlier headless smoke test (started by the assistant to verify Chainlit) was still bound to port 8000 and hadn't released a locked `.files` directory. Killed the process (PID 11780) and removed the stale `.files` directory.
- **Python 3.14 incompatibility**: `chainlit run app.py` starts and reports the app is available, but every request throws `anyio._core._exceptions.NoEventLoopError: Not currently running on any asynchronous event loop`. Root cause: Chainlit patches the event loop via `nest_asyncio`, and that patch appears incompatible with `anyio`'s event-loop detection on Python 3.14 (Python 3.14 is very new and this dependency chain isn't adapted for it yet). This is an upstream library incompatibility, not something fixable in application code.
  - Confirmed only Python 3.14 was installed on this machine (`py -0p`); no 3.11/3.12 available at the time.

## 2026-09-15 — Python 3.12 project-local virtual environment

- Installed **Python 3.12.10** via `winget install --id Python.Python.3.12 -e --scope user`, side-by-side with the existing Python 3.14. Confirmed the machine's global default (`python`, `py -0p`'s `*` entry) is still 3.14 — 3.12 is only reachable via `py -3.12` or by using this project's venv.
- Created a project-local virtual environment: `py -3.12 -m venv .venv` in the repo root (`.venv` already gitignored).
- Installed `requirements.txt` (+ `langchain`, needed by Langfuse's `CallbackHandler`) into `.venv`. First install attempt silently produced broken packages (`pydantic_core`, then `uuid_utils` missing their compiled native modules, both raising `ModuleNotFoundError` on import) due to a corrupted pip cache (`WARNING: Cache entry deserialization failed, entry ignored`). Fixed by `pip cache purge` followed by a full `--no-cache-dir --force-reinstall` of everything into `.venv`.
- Note: this pulled much newer major versions than originally pinned — `langchain` 1.4.0, `langgraph` 1.2.11, `openai` 3.14.0 (vs. the 0.3.x/0.2.x/1.x originally assumed) — but the existing agent code (`agents/runner.py`, `agents/graph.py`, `agents/hitl_gate.py`'s `interrupt()`/`Command` usage) worked against these without changes.
- Verified: agent-graph smoke test (`agents.runner.start_question`) answered correctly from `.venv`'s Python. Chainlit (`.venv\Scripts\python.exe -m chainlit run app.py --headless`) started cleanly and served `HTTP 200` — **no `NoEventLoopError`** — confirming Python 3.12 resolves the Chainlit/`nest_asyncio`/`anyio` incompatibility seen on 3.14. (First health-check attempt after starting the process showed "connection refused" at 8s — this venv's Chainlit/ChromaDB cold start took closer to 15-20s; a longer wait confirmed the server was fine, just slower to bind on first run.)
- Updated `CLAUDE.md`'s "Running the MVP" section to document the Python 3.12 / `.venv` requirement and the corresponding `.venv\Scripts\python.exe`-prefixed commands.

## 2026-09-15 — Git Bash (VS Code) couldn't resolve the venv's `chainlit`

- User could run `chainlit run app.py` successfully from a Windows Command Prompt with the venv active, but the same command in a VS Code Git Bash terminal either wasn't found or (after activating) still resolved to the **global Python 3.14** install's `chainlit.exe`/site-packages, reproducing the same `NoEventLoopError` traceback the 3.12 venv was supposed to fix.
- Diagnosed in stages:
  1. Confirmed Git Bash's bare `python`/`chainlit` (before activating) resolve to unrelated global installs, not the project venv — expected, since a venv must be activated per-shell.
  2. After the user activated in the *same* terminal where `chainlit` had already been run once, the traceback still showed `Python314\Lib\site-packages\...` — consistent with Bash's command-path hash cache (`hash -r` needed after activation, or a fresh shell) rather than an actual PATH problem.
  3. User opened a **new** terminal, re-activated, and `which chainlit` still printed the Python 3.14 path. Inspected `.venv/Scripts/activate`: on MSYS/MinGW it uses `cygpath`/`uname` to convert the Windows venv path to a POSIX path before prepending it to `$PATH`. If either of those doesn't behave as expected in that specific Git Bash install, the prepended PATH entry silently fails to resolve, and `chainlit` falls back to whatever the inherited Windows PATH already contains (Python 3.14's Scripts dir).
- **Workaround (adopted)**: bypass PATH/activation resolution entirely and invoke the venv's interpreter directly by relative path:
  ```bash
  cd "/c/Users/vkyla/OneDrive/Documents/IKStart/Agentic AI/Capstone/NL2SQL capstone project/NL2SQLcode"
  ./.venv/Scripts/python.exe -m chainlit run app.py
  ```
  Confirmed `./.venv/Scripts/python.exe` correctly reports Python 3.12.10 from the project venv regardless of the activate-script PATH issue.
- **Not yet root-caused**: why `cygpath`/`uname`-based path conversion fails in this user's specific Git Bash instance. Not pursued further since the direct-invocation workaround is reliable; worth revisiting if it recurs elsewhere (e.g. before Hugging Face Spaces deployment, which uses Linux and won't hit this Windows/MSYS-specific issue at all).

### Verification performed

- `python data/seed.py` → schema created + sample data loaded into Turso.
- `python -m ingestion.schema_crawler` → 5 tables crawled.
- `python -m knowledge.build_index` → 38 schema entries, 12 exemplars, 8 glossary terms indexed into ChromaDB.
- Chainlit (`chainlit run app.py --headless`) started cleanly and served `HTTP 200` on `localhost:8000` (from the 3.12 venv).
