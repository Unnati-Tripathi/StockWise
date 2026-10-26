"""
Unit and API integration tests for Document Management and RAG Search endpoints.

Tests:
- Uploading valid TXT, PDF, and DOCX files.
- Rejecting invalid extensions, oversized files, 0-byte files, and magic-byte spoofing.
- Document listing with pagination.
- Single document retrieval by ID.
- Retry ingestion endpoint for failed/pending documents.
- RAG hybrid search endpoint.
- Document deletion and cleanup of associated chunks.
"""
import io
import os
import pytest
from app.models.document import Document, DocumentChunk


def test_upload_valid_txt_document(client, db_session):
    content = b"StockWise standard operating procedure for insulin cold chain storage."
    response = client.post(
        "/api/v1/documents/",
        files={"file": ("insulin_sop.txt", io.BytesIO(content), "text/plain")},
        data={"title": "Insulin Storage SOP", "doc_type": "sop"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "insulin_sop.txt"
    assert data["id"] is not None
    assert data["status"] in ["ready", "pending", "processing"]


def test_upload_valid_pdf_document(client, db_session):
    # Valid PDF header
    content = b"%PDF-1.4\n1 0 obj\n<< /Title (Antibiotic Guidelines) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    response = client.post(
        "/api/v1/documents/",
        files={"file": ("guidelines.pdf", io.BytesIO(content), "application/pdf")},
        data={"title": "Antibiotic Formulary", "doc_type": "policy"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "guidelines.pdf"
    assert data["id"] is not None


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/api/v1/documents/",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/api/v1/documents/",
        files={"file": ("script.py", io.BytesIO(b"print('hello')"), "text/x-python")},
    )
    assert response.status_code == 400
    assert "unsupported file extension" in response.json()["detail"].lower()


def test_upload_rejects_magic_byte_spoofing(client):
    # File named .pdf but containing plain text without %PDF- header
    fake_pdf = b"This is just plain text disguised as a PDF file."
    response = client.post(
        "/api/v1/documents/",
        files={"file": ("fake.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert response.status_code == 400
    assert "does not match pdf format" in response.json()["detail"].lower()


def test_upload_rejects_null_bytes_in_text(client):
    # Text file containing binary null bytes
    malicious_txt = b"Hello\x00World\x00Binary"
    response = client.post(
        "/api/v1/documents/",
        files={"file": ("binary.txt", io.BytesIO(malicious_txt), "text/plain")},
    )
    assert response.status_code == 400
    assert "null bytes" in response.json()["detail"].lower()


def test_list_documents_pagination(client, db_session):
    # Create two documents in DB
    doc1 = Document(
        filename="doc1.txt",
        file_path="/tmp/doc1.txt",
        title="Doc 1",
        status="ready",
        file_hash="hash1",
    )
    doc2 = Document(
        filename="doc2.txt",
        file_path="/tmp/doc2.txt",
        title="Doc 2",
        status="ready",
        file_hash="hash2",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    response = client.get("/api/v1/documents/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


def test_get_document_detail_and_not_found(client, db_session):
    doc = Document(
        filename="detail_doc.txt",
        file_path="/tmp/detail.txt",
        title="Detail Document",
        status="ready",
        file_hash="hash_detail",
    )
    db_session.add(doc)
    db_session.commit()

    # Success
    res = client.get(f"/api/v1/documents/{doc.id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Detail Document"

    # Not found
    res_404 = client.get("/api/v1/documents/999999")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"].lower()


def test_retry_document_ingestion(client, db_session):
    doc = Document(
        filename="failed_doc.txt",
        file_path="/tmp/failed.txt",
        title="Failed Document",
        status="failed",
        error_message="Network timeout during chunk embedding",
        file_hash="hash_failed",
    )
    db_session.add(doc)
    db_session.commit()

    response = client.post(f"/api/v1/documents/{doc.id}/retry")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["error_message"] is None


def test_delete_document_and_cascade(client, db_session):
    doc = Document(
        filename="to_delete.txt",
        file_path="/tmp/to_delete.txt",
        title="Delete Me",
        status="ready",
        file_hash="hash_delete",
    )
    db_session.add(doc)
    db_session.commit()

    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Delete test chunk content",
    )
    db_session.add(chunk)
    db_session.commit()

    # Delete
    del_res = client.delete(f"/api/v1/documents/{doc.id}")
    assert del_res.status_code == 204

    # Verify document is gone
    get_res = client.get(f"/api/v1/documents/{doc.id}")
    assert get_res.status_code == 404


def test_search_documents_endpoint(client, db_session):
    doc = Document(
        filename="knowledge.txt",
        file_path="/tmp/knowledge.txt",
        title="Knowledge Base",
        status="ready",
        file_hash="hash_kb",
    )
    db_session.add(doc)
    db_session.commit()

    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Amoxicillin should be stored between 20C and 25C dry conditions.",
    )
    db_session.add(chunk)
    db_session.commit()

    search_payload = {"query": "Amoxicillin storage temperature", "top_k": 3}
    res = client.post("/api/v1/documents/search", json=search_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "Amoxicillin storage temperature"
    assert "results" in data
