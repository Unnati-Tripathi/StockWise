from fastapi.testclient import TestClient
from app.models.invoice import InvoiceProcessingStatus
import os

def test_e2e_invoice_workflow_and_assistant(client, db_session):
    # 1. Init demo data
    res = client.post("/api/v1/demo/reset")
    assert res.status_code == 200
    
    # 2. Upload dummy invoice
    file_path = "e2e_upload.pdf"
    with open(file_path, "wb") as f: f.write(b"dummy")
    with open(file_path, "rb") as f:
        res = client.post("/api/v1/invoices/", files={"file": ("e2e_upload.pdf", f, "application/pdf")})
    os.remove(file_path)
    
    assert res.status_code == 200
    invoice_id = res.json()["id"]
    
    # 3. Get invoice (should be NEEDS_REVIEW because we use a test mock provider)
    res = client.get(f"/api/v1/invoices/{invoice_id}")
    inv = res.json()
    assert inv["status"] in ["NEEDS_REVIEW", "FAILED", "PROCESSING", "UPLOADED"]
    
    # 4. Check assistant API
    res = client.post("/api/v1/assistant/chat", json={"query": "Which medicines are at critical risk?"})
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "evidence" in data
    assert data["evidence"] is not None, data["reply"]
    assert data["evidence"]["tool_name"] == "get_recommendations"
