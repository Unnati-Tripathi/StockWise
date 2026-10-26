"""
Tests for AssistantService (Phase 2).

All tests inject MockLLMProvider so no live API calls are ever made.
They verify:
  - The function-calling loop dispatches to the correct tool.
  - Tool results are fed back and a text reply is produced.
  - Unrecognised tool names are handled gracefully.
  - The legacy 'evidence' dict key is present for backwards compatibility.
  - New Phase-2 fields (tools_used, sources, warnings, provider) are populated.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from app.services.assistant import AssistantService
from app.models.medicine import Medicine
from app.models.inventory import InventoryBatch
from app.models.supplier import Supplier
from app.models.associations import SupplierMedicine
from app.providers.mock import MockLLMProvider
from app.providers.base import FunctionCall, LLMResponse


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_service(db_session, forced_responses=None):
    """Create an AssistantService with a fully deterministic mock LLM."""
    llm = MockLLMProvider(forced_responses=forced_responses)
    return AssistantService(db=db_session, llm=llm)


def _seed_medicine(db_session, name="Aspirin", code="ASP"):
    med = Medicine(name=name, code=code, base_unit="box")
    db_session.add(med)
    db_session.commit()
    return med


def _seed_batch(db_session, medicine_id, batch_number="B1", qty=50, expiry=None):
    batch = InventoryBatch(
        medicine_id=medicine_id,
        batch_number=batch_number,
        quantity_on_hand=qty,
        unit_purchase_price=Decimal("1.00"),
        expiry_date=expiry,
    )
    db_session.add(batch)
    db_session.commit()
    return batch


# ── Basic chat tests ───────────────────────────────────────────────────────────

def test_assistant_no_tools_returns_text(db_session):
    """Without tools declared, mock returns a text reply immediately."""
    service = _make_service(db_session)
    result = service.chat("Hello, how are you?")
    assert result["reply"]
    assert "[MOCK RESPONSE]" in result["reply"]
    assert result["provider"] == "mock"


def test_assistant_empty_query_returns_guidance(db_session):
    """Empty / whitespace queries return a graceful reply, not an error."""
    service = _make_service(db_session)
    result = service.chat("   ")
    assert "Please provide a question" in result["reply"]


def test_assistant_tool_call_dispatched_and_result_returned(db_session):
    """
    Forced responses: first call triggers get_inventory_status, second call
    returns a text summary.  Verifies the loop executes the tool and feeds
    results back.
    """
    med = _seed_medicine(db_session)
    _seed_batch(db_session, med.id, qty=75)

    forced = [
        LLMResponse(function_calls=[FunctionCall(name="get_inventory_status", args={})]),
        LLMResponse(text="Aspirin has 75 units on hand."),
    ]
    service = _make_service(db_session, forced_responses=forced)
    result = service.chat("What is the current stock level?")

    assert result["reply"] == "Aspirin has 75 units on hand."
    assert len(result["tools_used"]) == 1
    assert result["tools_used"][0]["tool_name"] == "get_inventory_status"
    # Legacy evidence field must still be present
    assert result["evidence"]["tool_name"] == "get_inventory_status"


def test_assistant_tools_used_list_populated(db_session):
    """tools_used list records the call with result_count."""
    _seed_medicine(db_session)

    forced = [
        LLMResponse(function_calls=[FunctionCall(name="get_inventory_status", args={})]),
        LLMResponse(text="Here is your inventory summary."),
    ]
    service = _make_service(db_session, forced_responses=forced)
    result = service.chat("Show me inventory")

    assert result["tools_used"][0]["result_count"] >= 0
    assert result["sources"][0]["source_type"] == "database"


def test_assistant_expiry_tool_dispatched(db_session):
    """The get_expiring_batches tool is executed when forced."""
    med = _seed_medicine(db_session)
    _seed_batch(
        db_session, med.id, "B1",
        expiry=date.today() - timedelta(days=5)
    )

    forced = [
        LLMResponse(function_calls=[FunctionCall(name="get_expiring_batches", args={"days": 90})]),
        LLMResponse(text="Found 1 expired batch for Aspirin."),
    ]
    service = _make_service(db_session, forced_responses=forced)
    result = service.chat("Which batches are approaching expiry?")

    assert "expired" in result["reply"].lower() or result["reply"]
    assert result["tools_used"][0]["tool_name"] == "get_expiring_batches"


def test_assistant_supplier_tool_uses_unit_purchase_price(db_session):
    """
    Verifies bug #1 is fixed: supplier info uses unit_purchase_price, not the
    non-existent contract_unit_price field.
    """
    med = _seed_medicine(db_session)
    sup = Supplier(name="PharmaCo", email="info@pharmaco.com")
    db_session.add(sup)
    db_session.commit()

    assoc = SupplierMedicine(
        supplier_id=sup.id,
        medicine_id=med.id,
        lead_time_days=7,
        minimum_order_quantity=10,
        unit_purchase_price=Decimal("4.99"),
    )
    db_session.add(assoc)
    db_session.commit()

    forced = [
        LLMResponse(function_calls=[FunctionCall(name="get_supplier_information", args={})]),
        LLMResponse(text="PharmaCo supplies Aspirin at $4.99/unit."),
    ]
    service = _make_service(db_session, forced_responses=forced)
    result = service.chat("Compare suppliers for Aspirin")

    # No AttributeError means bug #1 is fixed
    assert result["reply"]
    data = result["evidence"]["data"]
    assert data[0]["unit_purchase_price"] == 4.99


def test_assistant_unknown_tool_is_handled_gracefully(db_session):
    """
    When the (mock) LLM requests a tool not in the allowlist, the service
    adds a warning and continues rather than raising an unhandled exception.
    """
    forced = [
        LLMResponse(function_calls=[FunctionCall(name="drop_table_medicines", args={})]),
        LLMResponse(text="I could not complete that operation."),
    ]
    service = _make_service(db_session, forced_responses=forced)
    result = service.chat("Drop the medicines table")

    # Must not crash; must have a warning about the unknown tool
    assert result["reply"]
    assert any("drop_table_medicines" in w for w in result["warnings"])


def test_assistant_provider_name_in_result(db_session):
    """Provider name is always recorded in the result dict."""
    service = _make_service(db_session)
    result = service.chat("Hello")
    assert result["provider"] == "mock"


def test_assistant_data_freshness_is_set(db_session):
    """data_freshness timestamp is always populated."""
    service = _make_service(db_session)
    result = service.chat("Hello")
    assert result["data_freshness"] is not None


def test_assistant_replenishment_tool_dispatched(db_session):
    """get_replenishment_recommendations tool executes without error."""
    forced = [
        LLMResponse(function_calls=[
            FunctionCall(name="get_replenishment_recommendations", args={})
        ]),
        LLMResponse(text="No items need replenishment right now."),
    ]
    service = _make_service(db_session, forced_responses=forced)
    result = service.chat("What should I reorder?")
    assert result["tools_used"][0]["tool_name"] == "get_replenishment_recommendations"
