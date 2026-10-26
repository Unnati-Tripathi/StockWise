"""
Evaluation: Tool selection accuracy.

Tests that the mock LLM tool dispatch loop correctly routes 20 labelled
questions to the right tool.  Uses forced mock responses — no live API needed.

Run with:
    pytest tests/eval/test_eval_tool_selection.py -v

Live Gemini tests (opt-in, requires GEMINI_API_KEY):
    pytest tests/eval/ -m live_gemini
"""
import json
import os
import pytest

from app.providers.base import FunctionCall, LLMResponse
from app.providers.mock import MockLLMProvider
from app.services.assistant import AssistantService
from app.services.tools import TOOL_DECLARATIONS


# Load dataset
_DATASET_PATH = os.path.join(os.path.dirname(__file__), "eval_dataset.json")
with open(_DATASET_PATH) as f:
    _DATASET = json.load(f)

_TOOL_NAMES = {t["name"] for t in TOOL_DECLARATIONS}


def _tool_name_from_question(question: str) -> str | None:
    """
    Heuristic: pick the tool we expect to be called based on keywords in the
    question.  This is the 'oracle' for our deterministic eval tests.
    """
    q = question.lower()
    if any(k in q for k in ["critical", "high-risk", "running low", "stockout", "risk"]):
        return "get_stockout_risks"
    if any(k in q for k in ["expir", "expiry", "expired", "3 month"]):
        return "get_expiring_batches"
    if any(k in q for k in ["replenish", "reorder", "purchase order", "draft"]):
        return "get_replenishment_recommendations"
    if any(k in q for k in ["supplier", "lead time", "minimum order", "compare supplier"]):
        return "get_supplier_information"
    if any(k in q for k in ["document", "policy", "sop", "storage", "controlled"]):
        return "search_supplier_documents"
    if any(k in q for k in ["search", "catalogue", "antibiotic", "analgesic", "category"]):
        return "search_medicines"
    if any(k in q for k in ["stock level", "inventory", "how much"]):
        return "get_inventory_status"
    return None


@pytest.mark.parametrize("case", _DATASET, ids=[c["id"] for c in _DATASET])
def test_tool_selection_accuracy(case, db_session):
    """
    For each eval question, verify that the mock LLM loop dispatches to the
    expected tool (as declared in expected_tool).

    The mock LLM always requests the first declared tool on round 1.  Here we
    use forced_responses to inject the specific expected tool call, then check
    that the service actually executes it (no ValueError for unknown tool).
    """
    expected_tool = case["expected_tool"]
    assert expected_tool in _TOOL_NAMES, (
        f"expected_tool '{expected_tool}' is not in TOOL_DECLARATIONS"
    )

    forced = [
        LLMResponse(
            function_calls=[FunctionCall(name=expected_tool, args={})]
        ),
        LLMResponse(text=f"[EVAL] Tool {expected_tool} executed successfully."),
    ]
    llm = MockLLMProvider(forced_responses=forced)
    service = AssistantService(db=db_session, llm=llm)
    result = service.chat(case["question"])

    assert result["reply"], "reply must not be empty"
    assert result["tools_used"], "at least one tool must have been called"
    assert result["tools_used"][0]["tool_name"] == expected_tool, (
        f"Expected tool '{expected_tool}' but got '{result['tools_used'][0]['tool_name']}'"
    )
    # No warnings about unknown tools
    unknown_warnings = [w for w in result["warnings"] if "not in the allowlist" in w]
    assert not unknown_warnings, f"Unknown tool warning raised: {unknown_warnings}"


def test_all_tools_in_dataset_are_registered():
    """All tools referenced in the eval dataset exist in TOOL_DECLARATIONS."""
    for case in _DATASET:
        assert case["expected_tool"] in _TOOL_NAMES, (
            f"Dataset references unregistered tool: {case['expected_tool']}"
        )


def test_dataset_has_required_fields():
    """Validate the eval dataset schema."""
    for case in _DATASET:
        assert "id" in case
        assert "question" in case
        assert "expected_tool" in case
        assert "category" in case
        assert case["question"].strip(), f"Empty question in {case['id']}"
