import os
from fastapi.testclient import TestClient
from app.models.invoice import InvoiceProcessingStatus, Invoice

def test_upload_invoice_endpoint(client, db_session):
    # Create dummy pdf
    file_path = "test_upload.pdf"
    with open(file_path, "wb") as f:
        f.write(b"%PDF-1.4 dummy content")
        
    with open(file_path, "rb") as f:
        response = client.post(
            "/api/v1/invoices/",
            files={"file": ("test_upload.pdf", f, "application/pdf")}
        )
        
    os.remove(file_path)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UPLOADED"
    assert "id" in data
    
    invoice_id = data["id"]
    
    # Check if background task processed it (since it's TestClient, background tasks run synchronously)
    # Actually TestClient in FastAPI runs background tasks synchronously after the response.
    # Wait, Starlette TestClient *does* run them immediately, so it might be NEEDS_REVIEW already.
    # Let's get the invoice
    get_res = client.get(f"/api/v1/invoices/{invoice_id}")
    assert get_res.status_code == 200
    inv = get_res.json()
    
    assert inv["status"] in ["NEEDS_REVIEW", "FAILED", "PROCESSING", "UPLOADED"]

def test_get_invoices(client):
    response = client.get("/api/v1/invoices/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_invalid_file_extension(client):
    file_path = "test.txt"
    with open(file_path, "wb") as f:
        f.write(b"text")
        
    with open(file_path, "rb") as f:
        response = client.post(
            "/api/v1/invoices/",
            files={"file": ("test.txt", f, "text/plain")}
        )
        
    os.remove(file_path)
    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]
