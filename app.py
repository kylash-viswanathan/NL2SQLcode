"""Chainlit entrypoint for the TrustQuery AI MVP prototype. Run locally with:

    chainlit run app.py
"""
import asyncio
import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

import chainlit as cl
import yaml

from agents.runner import (
    STAGE_ORDER,
    get_current_state,
    stream_resume_with_decision,
    stream_start_question,
)

REPO_ROOT = Path(__file__).resolve().parent
SCHEMA_METADATA_PATH = REPO_ROOT / "ingestion" / "schema_metadata.json"
GOLDEN_SET_PATH = REPO_ROOT / "evaluation" / "golden_set.yaml"

# Single-word phase label shown alongside the progress %.
STAGE_PHASE_WORD = {
    "planner": "Planning",
    "schema_linking": "Retrieving",
    "sql_generation": "Generating",
    "hitl_gate": "Reviewing",
    "execution": "Executing",
    "governance": "Masking",
    "response": "Responding",
}

STAGE_LABELS = {
    "planner": "Planner — routing the question",
    "schema_linking": "Schema-Linking — retrieving relevant schema",
    "sql_generation": "SQL Generation — writing the query",
    "hitl_gate": "HITL Gate — checking for sensitive data",
    "execution": "Execution — running the query",
    "governance": "Governance — masking sensitive columns",
    "response": "Response — composing the answer",
}


def _load_schema_markdown() -> str:
    if not SCHEMA_METADATA_PATH.exists():
        return (
            "_Schema metadata not found — run `python -m ingestion.schema_crawler` "
            "to generate it._"
        )
    metadata = json.loads(SCHEMA_METADATA_PATH.read_text(encoding="utf-8"))
    lines = ["## Sample database schema\n_Wealth & portfolio management_"]
    for table in metadata["tables"]:
        lines.append(f"\n**`{table['name']}`**\n")
        lines.append("| Column | Type | Sensitivity |")
        lines.append("|---|---|---|")
        for col in table["columns"]:
            name = f"{col['name']} 🔑" if col["primary_key"] else col["name"]
            flag = f"`{col['sensitivity']}`" if col["sensitivity"] != "public" else ""
            lines.append(f"| {name} | {col['type']} | {flag} |")
    return "\n".join(lines)


def _load_sample_queries() -> list[str]:
    if not GOLDEN_SET_PATH.exists():
        return []
    golden_set = yaml.safe_load(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return [item["question"] for item in golden_set]


def _load_reference_panel_markdown() -> str:
    """Combined schema + sample-question list shown in the collapsible side panel,
    so it's available for reference without cluttering the main chat."""
    sections = [_load_schema_markdown()]
    queries = _load_sample_queries()
    if queries:
        sections.append("\n## Sample questions\n" + "\n".join(f"- {q}" for q in queries))
    return "\n".join(sections)


def _progress_bar(pct: int, stage: str | None) -> str:
    filled = max(0, min(10, round(pct / 10)))
    bar = "🟩" * filled + "⬜" * (10 - filled)
    phase = f" ({STAGE_PHASE_WORD.get(stage, 'Starting')})" if stage else ""
    return f"{bar}  **{pct}%**{phase}"


async def _run_with_progress(
    stream_factory: Callable[[], Iterator[dict[str, Any]]], thread_id: str
) -> dict:
    """Runs a sync LangGraph stream generator (from stream_factory()) in a background
    thread, updating a TaskList + progress bar as each node completes. Returns either
    {"__interrupt__": <interrupt payload dict>} or the final accumulated state."""
    task_list = cl.TaskList()
    task_list.status = "Running..."
    tasks = {}
    for stage in STAGE_ORDER:
        task = cl.Task(title=STAGE_LABELS[stage], status=cl.TaskStatus.READY)
        tasks[stage] = task
        await task_list.add_task(task)
    await task_list.send()

    progress_msg = cl.Message(content=_progress_bar(0, None))
    await progress_msg.send()

    work_queue: queue.Queue = queue.Queue()

    def _worker() -> None:
        try:
            for chunk in stream_factory():
                work_queue.put(("chunk", chunk))
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
            work_queue.put(("error", str(exc)))
        finally:
            work_queue.put(("done", None))

    threading.Thread(target=_worker, daemon=True).start()

    completed: set[str] = set()
    interrupt_payload = None

    while True:
        kind, payload = await asyncio.to_thread(work_queue.get)

        if kind == "error":
            task_list.status = "Failed"
            await task_list.send()
            raise RuntimeError(payload)

        if kind == "done":
            break

        node_name = next(iter(payload))
        if node_name == "__interrupt__":
            interrupt_payload = payload["__interrupt__"][0].value
            continue

        if node_name in tasks:
            tasks[node_name].status = cl.TaskStatus.DONE
            completed.add(node_name)
            pct = round(len(completed) / len(STAGE_ORDER) * 100)
            progress_msg.content = _progress_bar(pct, node_name)
            await progress_msg.update()
            await task_list.send()

    task_list.status = "Done"
    progress_msg.content = _progress_bar(100, "response")
    await progress_msg.update()
    await task_list.send()

    if interrupt_payload is not None:
        return {"__interrupt__": interrupt_payload}
    return get_current_state(thread_id)


async def _finalize_and_show(state: dict) -> None:
    response = state.get("response", "(no response generated)")
    content = response

    sql = state.get("sql")
    if sql:
        content += f"\n\n**Generated SQL:**\n```sql\n{sql}\n```"

    columns = state.get("masked_columns")
    rows = state.get("masked_rows")
    if columns and rows:
        header = " | ".join(columns)
        sep = " | ".join(["---"] * len(columns))
        body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
        content += f"\n\n**Result:**\n\n{header}\n{sep}\n{body}"

    await cl.Message(content=content).send()


async def _handle_result(result: dict, thread_id: str) -> None:
    if "__interrupt__" in result:
        payload = result["__interrupt__"]
        await cl.Message(
            content=(
                f"**Human review required**\n\n{payload['reason']}\n\n"
                f"**Question:** {payload['question']}\n\n"
                f"**Proposed SQL:**\n```sql\n{payload['sql']}\n```\n\n"
                "Approve or reject this query before it runs."
            ),
            actions=[
                cl.Action(name="approve", payload={"thread_id": thread_id}, label="Approve"),
                cl.Action(name="reject", payload={"thread_id": thread_id}, label="Reject"),
            ],
        ).send()
        return

    await _finalize_and_show(result)


async def _process_query(question: str, thread_id: str) -> None:
    result = await _run_with_progress(
        lambda: stream_start_question(question, thread_id), thread_id
    )
    await _handle_result(result, thread_id)


@cl.on_chat_start
async def on_chat_start():
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)

    await cl.Message(
        content=(
            "Ask me anything about clients, portfolios, holdings, trades, or assets "
            "in the wealth management sample database. Open the **Sample Schema** "
            "panel on the right for the full table/column list and example questions."
        ),
        elements=[
            cl.Text(
                name="Sample Schema",
                content=_load_reference_panel_markdown(),
                display="side",
            )
        ],
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    await _process_query(message.content, thread_id)


@cl.action_callback("approve")
async def on_approve(action: cl.Action):
    thread_id = action.payload["thread_id"]
    result = await _run_with_progress(
        lambda: stream_resume_with_decision(thread_id, True), thread_id
    )
    await _handle_result(result, thread_id)


@cl.action_callback("reject")
async def on_reject(action: cl.Action):
    thread_id = action.payload["thread_id"]
    result = await _run_with_progress(
        lambda: stream_resume_with_decision(thread_id, False), thread_id
    )
    await _handle_result(result, thread_id)
