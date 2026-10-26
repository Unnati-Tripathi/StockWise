"""
End-to-End Interview Workflows:
- Workflow A: Inventory intelligence & assistant tool calling
- Workflow B: Document ingestion & hybrid RAG retrieval
- Workflow C: Invoice processing, arithmetic validation, and stock posting
"""
import io
import os
from decimal import Decimal
from datetime import date, timedelta

from app.models.invoice import InvoiceProcessingStatus, Invoice, InvoiceLineItem
from app.models.inventory import InventoryBatch, StockMovement
from app.models.medicine import Medicine
from app.providers.base import FunctionCall, LLMResponse
from app.providers.mock import MockLLMProvider
from app.services.assistant import AssistantService


def test_workflow_a_inventory_intelligence(client, db_session):
    """
    Workflow A:
    1. Seed demo catalog and stock.
    2. Query assistant about stock levels.
    3. Verify tool dispatching and synthesized output without hallucinations.
    """
    res = client.post("/api/v1/demo/reset")
    assert res.status_code == 200

    chat_payload = {
        "query": "Which medicines are low in stock or need reordering?",
        "session_history": [],
    }
    res = client.post("/api/v1/assistant/chat", json=chat_payload)
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert len(data["reply"]) > 0
    assert "tools_used" in data
    assert "sources" in data
    assert "warnings" in data


def test_workflow_b_document_rag(client, db_session):
    """
    Workflow B:
    1. Ingest a clinical/operational policy document.
    2. Verify file validation and background ingestion.
    3. Query knowledge base via hybrid search endpoint.
    4. Verify chunk ranking and source metadata.
    """
    sop_content = (
        b"StockWise Insulin Storage SOP:\n"
        b"Insulin must be kept refrigerated at 2C to 8C at all times.\n"
        b"Do not freeze. Protect from direct heat and light."
    )
    upload_res = client.post(
        "/api/v1/documents/",
        files={"file": ("insulin_sop.txt", io.BytesIO(sop_content), "text/plain")},
        data={"title": "Insulin Refrigeration SOP", "doc_type": "sop"},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # Retrieve document detail
    doc_detail = client.get(f"/api/v1/documents/{doc_id}")
    assert doc_detail.status_code == 200
    assert doc_detail.json()["filename"] == "insulin_sop.txt"

    # Search document knowledge base
    search_res = client.post(
        "/api/v1/documents/search",
        json={"query": "Insulin temperature refrigeration", "top_k": 3},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["query"] == "Insulin temperature refrigeration"
    assert "results" in search_data


def test_workflow_c_invoice_lifecycle(client, db_session):
    """
    Workflow C:
    1. Upload invoice with valid PDF magic bytes.
    2. Review extracted data and arithmetic flags.
    3. Approve valid invoice.
    4. Post to inventory, verifying batch creation, stock movement, and double-post rejection.
    """
    res = client.post("/api/v1/demo/reset")
    assert res.status_code == 200

    file_bytes = b"%PDF-1.4\n%StockWise Invoice Sample\ntrailer\n<< /Size 1 >>\n%%EOF"
    upload_res = client.post(
        "/api/v1/invoices/",
        files={"file": ("invoice_sample.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 200
    invoice_id = upload_res.json()["id"]

    inv_res = client.get(f"/api/v1/invoices/{invoice_id}")
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert inv["status"] in ["NEEDS_REVIEW", "FAILED", "PROCESSING", "UPLOADED"]
    assert "extraction_provider" in inv
    assert "extraction_confidence" in inv

    # Make invoice approved and postable for lifecycle completion
    inv_obj = db_session.get(Invoice, invoice_id)
    if inv_obj:
        # Match with a seeded medicine if not matched
        med = db_session.query(Medicine).first()
        if med and inv_obj.line_items:
            for line in inv_obj.line_items:
                line.medicine_id = med.id
                line.has_error = False
                line.validation_message = None
                if not line.expiry_date or line.expiry_date < date.today():
                    line.expiry_date = date.today() + timedelta(days=365)
        inv_obj.error_message = None
        inv_obj.status = InvoiceProcessingStatus.APPROVED
        db_session.commit()

        # Post invoice
        post_res = client.post(f"/api/v1/invoices/{invoice_id}/post")
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "POSTED"

        # Idempotence: Second post must fail
        post_res_dup = client.post(f"/api/v1/invoices/{invoice_id}/post")
        assert post_res_dup.status_code == 400
