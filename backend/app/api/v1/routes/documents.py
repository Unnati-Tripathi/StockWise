"""
Document management and RAG search endpoints.

POST   /documents/             — Upload a document and trigger ingestion
GET    /documents/             — List all documents with status
GET    /documents/{id}         — Get a single document
POST   /documents/{id}/retry   — Retry ingestion for failed document
DELETE /documents/{id}         — Delete document and its chunks
POST   /documents/search       — Query the RAG index
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.security import validate_uploaded_file
from app.db.session import get_db
from app.providers.factory import get_embedding_provider
from app.schemas.document import (
    ChunkResult,
    DocumentListResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentUploadResponse,
)
from app.services.rag.document_store import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    save_upload,
)
from app.services.rag.ingestion import ingest_document
from app.services.rag.retrieval import hybrid_search

router = APIRouter()

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


@router.post("/", response_model=DocumentUploadResponse, status_code=200)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    doc_type: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Upload a PDF, DOCX, or TXT document and trigger background ingestion."""
    content = await file.read()
    try:
        validate_uploaded_file(file.filename or "", content, _ALLOWED_EXTENSIONS, 20 * 1024 * 1024)
    except ValueError as exc:
        status_code = 413 if "exceeds" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc))

    file_path = save_upload(file.filename or "uploaded_doc", content)
    doc = create_document(
        db,
        filename=file.filename or "uploaded_doc",
        file_path=file_path,
        title=title,
        doc_type=doc_type,
    )

    # Ingest in background task managed by FastAPI
    background_tasks.add_task(ingest_document, db, doc)

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        message="Document uploaded. Ingestion started in the background.",
    )


@router.get("/", response_model=DocumentListResponse)
def list_all_documents(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Return a paginated list of all documents and their ingestion status."""
    docs = list_documents(db, skip=skip, limit=limit)
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
        skip=skip,
        limit=limit,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document_detail(document_id: int, db: Session = Depends(get_db)):
    """Return details for a single document."""
    doc = get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentResponse.model_validate(doc)


@router.post("/{document_id}/retry", response_model=DocumentResponse)
def retry_document_ingestion(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Retry ingestion for a document in failed or pending state."""
    doc = get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc.status = "pending"
    doc.error_message = None
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(ingest_document, db, doc)
    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=204)
def remove_document(document_id: int, db: Session = Depends(get_db)):
    """Delete a document and all its chunks. Removes the file from disk."""
    doc = get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    delete_document(db, doc)


@router.post("/search", response_model=DocumentSearchResponse)
def search_documents(
    request: DocumentSearchRequest,
    db: Session = Depends(get_db),
):
    """Query the RAG index with hybrid lexical + semantic search."""
    embedding_provider = get_embedding_provider()
    chunks = hybrid_search(
        db,
        query=request.query,
        embedding_provider=embedding_provider,
        top_k=request.top_k,
    )
    results = [
        ChunkResult(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            document_filename=c.document_filename,
            page_number=c.page_number,
            section_heading=c.section_heading,
            content=c.content,
            score=c.score,
            match_type=c.match_type,
        )
        for c in chunks
    ]
    return DocumentSearchResponse(
        query=request.query,
        results=results,
        total=len(results),
    )
