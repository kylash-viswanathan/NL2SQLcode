"""DeepEval test suite scoring the agent's responses against the golden set
(evaluation/golden_set.yaml). Run with:

    pytest evaluation/deepeval_tests.py -v

Each run is traced through LangGraph into Langfuse (if configured), and the
DeepEval score computed here is attached back to that same trace via
observability.langfuse_setup.score_trace — so a reviewer can see the
correctness score directly next to the trace that produced it, not in a
separate pytest report.
"""
import uuid
from pathlib import Path

import pytest
import yaml
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from langfuse import propagate_attributes

from agents.runner import run_question_auto_approve
from config.settings import settings
from governance.masking import MASK_VALUE
from ingestion.db import get_client
from observability.langfuse_setup import flush as flush_langfuse
from observability.langfuse_setup import get_langfuse_client, score_trace

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.yaml"
GOLDEN_SET = yaml.safe_load(GOLDEN_SET_PATH.read_text(encoding="utf-8"))

NON_SENSITIVE_ITEMS = [item for item in GOLDEN_SET if not item.get("expect_hitl")]
SENSITIVE_ITEMS = [item for item in GOLDEN_SET if item.get("expect_hitl")]

correctness_metric = GEval(
    name="SQL Answer Correctness",
    criteria=(
        "Determine whether the actual output correctly and completely answers the "
        "question, given the expected query result provided as context. Minor "
        "phrasing differences are fine; factual/numeric mismatches are not."
    ),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.CONTEXT,
    ],
    threshold=0.7,
    model=settings.generation_model,
)


@pytest.fixture(scope="session", autouse=True)
def _flush_langfuse_traces():
    """pytest is a short-lived process — without an explicit flush, buffered spans
    and scores can be lost if the process exits before the SDK's own batching
    interval fires."""
    yield
    flush_langfuse()


def _run_scored(question: str, thread_id: str, span_name: str) -> tuple[dict, str | None]:
    """Runs the agent graph inside a Langfuse trace whose ID is known upfront (via
    create_trace_id()), so a DeepEval score can be attached to it afterward —
    ordinarily the trace closes before this function returns and its ID is no
    longer discoverable. Tags the run "golden-set-eval" to distinguish it from
    live Chainlit traffic. Returns (final_state, trace_id); trace_id is None when
    Langfuse isn't configured, in which case scoring is skipped."""
    client = get_langfuse_client()
    if client is None:
        return run_question_auto_approve(question, thread_id), None

    trace_id = client.create_trace_id()
    with client.start_as_current_observation(
        as_type="evaluator", name=span_name, trace_context={"trace_id": trace_id}
    ):
        with propagate_attributes(tags=["golden-set-eval"]):
            final_state = run_question_auto_approve(question, thread_id)
    return final_state, trace_id


def _reference_result(reference_sql: str) -> str:
    client = get_client()
    try:
        result = client.execute(reference_sql)
        return f"columns={list(result.columns)}, rows={[list(r) for r in result.rows]}"
    finally:
        client.close()


@pytest.mark.parametrize("item", NON_SENSITIVE_ITEMS, ids=[i["question"] for i in NON_SENSITIVE_ITEMS])
def test_golden_question(item):
    thread_id = str(uuid.uuid4())
    final_state, trace_id = _run_scored(item["question"], thread_id, "deepeval-golden-question")
    actual_output = final_state.get("response", "")
    expected_context = _reference_result(item["reference_sql"])

    test_case = LLMTestCase(
        input=item["question"],
        actual_output=actual_output,
        context=[expected_context],
    )
    correctness_metric.measure(test_case)

    if trace_id:
        score_trace(
            trace_id,
            "deepeval-correctness",
            correctness_metric.score,
            correctness_metric.reason,
        )

    assert correctness_metric.is_successful(), (
        f"SQL Answer Correctness score {correctness_metric.score} is below threshold "
        f"{correctness_metric.threshold}: {correctness_metric.reason}"
    )


@pytest.mark.parametrize("item", SENSITIVE_ITEMS, ids=[i["question"] for i in SENSITIVE_ITEMS])
def test_sensitive_query_triggers_hitl_and_masking(item):
    thread_id = str(uuid.uuid4())
    interrupted_state, trace_id = _run_scored(
        item["question"], thread_id, "deepeval-sensitive-question"
    )
    # run_question_auto_approve resumes automatically; re-derive whether the gate
    # actually fired by checking the final masked output for the mask marker.
    response = interrupted_state.get("response", "")
    masked_rows = interrupted_state.get("masked_rows", [])

    passed = MASK_VALUE in response or any(
        MASK_VALUE in str(cell) for row in masked_rows for cell in row
    )

    if trace_id:
        score_trace(
            trace_id,
            "deepeval-hitl-masking",
            1.0 if passed else 0.0,
            "PII columns masked in response" if passed else "PII columns NOT masked in response",
        )

    assert passed, "Expected PII columns to be masked in the response for a sensitive query."
