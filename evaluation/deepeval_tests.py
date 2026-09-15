"""DeepEval test suite scoring the agent's responses against the golden set
(evaluation/golden_set.yaml). Run with:

    pytest evaluation/deepeval_tests.py -v

Each run is traced through LangGraph into Langfuse (if configured); scores computed
here can be attached back to those traces via observability.langfuse_setup.score_trace.
"""
import uuid
from pathlib import Path

import pytest
import yaml
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from agents.runner import run_question_auto_approve
from config.settings import settings
from governance.masking import MASK_VALUE
from ingestion.db import get_client

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
    final_state = run_question_auto_approve(item["question"], thread_id)
    actual_output = final_state.get("response", "")
    expected_context = _reference_result(item["reference_sql"])

    test_case = LLMTestCase(
        input=item["question"],
        actual_output=actual_output,
        context=[expected_context],
    )
    assert_test(test_case, [correctness_metric])


@pytest.mark.parametrize("item", SENSITIVE_ITEMS, ids=[i["question"] for i in SENSITIVE_ITEMS])
def test_sensitive_query_triggers_hitl_and_masking(item):
    thread_id = str(uuid.uuid4())
    interrupted_state = run_question_auto_approve(item["question"], thread_id)
    # run_question_auto_approve resumes automatically; re-derive whether the gate
    # actually fired by checking the final masked output for the mask marker.
    response = interrupted_state.get("response", "")
    masked_rows = interrupted_state.get("masked_rows", [])

    assert MASK_VALUE in response or any(
        MASK_VALUE in str(cell) for row in masked_rows for cell in row
    ), "Expected PII columns to be masked in the response for a sensitive query."
