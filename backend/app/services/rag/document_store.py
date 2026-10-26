"""
Document CRUD and storage helpers for the RAG system.

Provides simple wrappers over the Document model so routes and ingestion
code don't need to write raw SQLAlchemy queries.
"""
from __future__ import annotations

import os
import shutil
import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document

DOCUMENT_STORAGE_DIR = "storage/documents"


def ensure_storage_dir() -> None:
    os.makedirs(DOCUMENT_STORAGE_DIR, exist_ok=True)


def save_upload(filename: str, file_bytes: bytes) -> str:
    """
    Write uploaded bytes to a safe path and return the absolute path.

    The filename is sanitised — a UUID prefix prevents collisions and
    path-traversal attacks.
    """
    ensure_storage_dir()
    _, ext = os.path.splitext(filename)
    safe_name = f"{uuid.uuid4().hex}{ext.lower()}"
    dest = os.path.join(DOCUMENT_STORAGE_DIR, safe_name)
    with open(dest, "wb") as f:
        f.write(file_bytes)
    return dest


def create_document(
    db: Session,
    *,
    filename: str,
    file_path: str,
    title: str | None = None,
    doc_type: str | None = None,
) -> Document:
    """Create and persist a new Document record with status='pending'."""
    doc = Document(
        filename=filename,
        file_path=file_path,
        title=title or filename,
        doc_type=doc_type,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_document(db: Session, document_id: int) -> Document | None:
    return db.execute(
        select(Document).where(Document.id == document_id)
    ).scalars().first()


def list_documents(db: Session, skip: int = 0, limit: int = 50) -> List[Document]:
    return (
        db.execute(
            select(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit)
        )
        .scalars()
        .all()
    )


def delete_document(db: Session, document: Document) -> None:
    """Delete the document record and its file from disk."""
    file_path = document.file_path
    db.delete(document)
    db.commit()
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Could not delete file %s: %s", file_path, exc
            )


def recover_stuck_documents(db: Session) -> int:
    """
    Recover any documents left in 'processing' or 'pending' state across restarts.

    Marks them as 'failed' with a recovery message so they are not locked forever.
    """
    stuck = db.execute(
        select(Document).where(Document.status.in_(["processing", "pending"]))
    ).scalars().all()

    for doc in stuck:
        doc.status = "failed"
        doc.error_message = "Server restarted while document was processing. Please retry ingestion."
    if stuck:
        db.commit()
    return len(stuck)
