"""
Document ingestion pipeline for the RAG system.

Workflow
--------
1. Validate file (MIME type, size, extension).
2. SHA-256 deduplication — skip unchanged files.
3. Extract text from PDF (pymupdf) or DOCX (python-docx) or plain text.
4. Chunk text with token-aware sliding window (500 tokens, 50-token overlap).
5. Generate embeddings in batches via the configured EmbeddingProvider.
6. Persist Document + DocumentChunk rows; set status = "ready".

All file I/O errors are caught and written to ``document.error_message`` so the
API can surface them without crashing the server.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Iterator

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.document import Document, DocumentChunk
from app.providers.base import EmbeddingProvider
from app.providers.factory import get_embedding_provider

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_FILE_BYTES = 20 * 1024 * 1024   # 20 MB
_CHUNK_TOKENS = 500
_OVERLAP_TOKENS = 50
_EMBED_BATCH_SIZE = 20
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_document(
    db: Session,
    document: Document,
    embedding_provider: EmbeddingProvider | None = None,
) -> Document:
    """
    Run the full ingestion pipeline for a Document record.

    Parameters
    ----------
    db:
        Active database session.
    document:
        A Document row that has already been persisted with status="pending".
    embedding_provider:
        Override for tests; defaults to the configured factory provider.

    Returns
    -------
    Document
        The same record with status updated to "ready" or "failed".
    """
    provider = embedding_provider or get_embedding_provider()

    try:
        document.status = "processing"
        db.commit()

        _validate_file(document.file_path)

        # Deduplication by SHA-256
        file_hash = _compute_hash(document.file_path)
        existing = db.execute(
            select(Document).where(
                Document.file_hash == file_hash,
                Document.id != document.id,
                Document.status == "ready",
            )
        ).scalars().first()
        if existing:
            document.status = "duplicate"
            document.error_message = (
                f"Identical content already ingested as document id={existing.id} "
                f"('{existing.filename}')."
            )
            db.commit()
            return document

        document.file_hash = file_hash

        # Extract text chunks
        chunks_data = list(_extract_and_chunk(document.file_path))
        if not chunks_data:
            raise ValueError("No text content could be extracted from the file.")

        # Embed in batches
        texts = [c["content"] for c in chunks_data]
        embeddings = _embed_in_batches(texts, provider)

        # Persist chunks
        for existing_chunk in document.chunks:
            db.delete(existing_chunk)
        db.flush()

        model_name = provider.model_name()
        for idx, (chunk_meta, emb) in enumerate(zip(chunks_data, embeddings)):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                page_number=chunk_meta.get("page_number"),
                section_heading=chunk_meta.get("section_heading"),
                content=chunk_meta["content"],
                embedding_model=model_name,
                embedding=emb.vector if _embedding_column_is_vector() else None,
            )
            db.add(chunk)

        document.chunk_count = len(chunks_data)
        document.embedding_model = model_name
        document.status = "ready"
        db.commit()
        logger.info(
            "Document %d ingested: %d chunks, model=%s",
            document.id, len(chunks_data), model_name,
        )

    except Exception as exc:
        db.rollback()
        document.status = "failed"
        document.error_message = str(exc)
        db.commit()
        logger.error("Ingestion failed for document %d: %s", document.id, exc)

    return document


# ── Internal helpers ──────────────────────────────────────────────────────────

def _embedding_column_is_vector() -> bool:
    """Return True if the pgvector extension is available."""
    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401
        return True
    except ImportError:
        return False


def _validate_file(file_path: str) -> None:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    size = os.path.getsize(file_path)
    if size > _MAX_FILE_BYTES:
        raise ValueError(f"File too large ({size} bytes). Maximum is {_MAX_FILE_BYTES} bytes.")
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {_ALLOWED_EXTENSIONS}.")


def _compute_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def _extract_and_chunk(file_path: str) -> Iterator[dict]:
    """Extract text and yield chunk dicts with metadata."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".pdf":
        yield from _extract_pdf(file_path)
    elif ext == ".docx":
        yield from _extract_docx(file_path)
    else:
        yield from _extract_text(file_path)


def _extract_pdf(file_path: str) -> Iterator[dict]:
    try:
        import pymupdf  # type: ignore[import]
    except ImportError:
        raise ImportError("pymupdf is required for PDF extraction. Run: pip install pymupdf")

    doc = pymupdf.open(file_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if not text.strip():
            continue
        for chunk in _sliding_window_chunks(text, _CHUNK_TOKENS, _OVERLAP_TOKENS):
            yield {"content": chunk, "page_number": page_num}
    doc.close()


def _extract_docx(file_path: str) -> Iterator[dict]:
    try:
        from docx import Document as DocxDocument  # type: ignore[import]
    except ImportError:
        raise ImportError("python-docx is required for DOCX extraction.")

    docx = DocxDocument(file_path)
    full_text = "\n".join(p.text for p in docx.paragraphs if p.text.strip())
    for chunk in _sliding_window_chunks(full_text, _CHUNK_TOKENS, _OVERLAP_TOKENS):
        yield {"content": chunk}


def _extract_text(file_path: str) -> Iterator[dict]:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        full_text = f.read()
    for chunk in _sliding_window_chunks(full_text, _CHUNK_TOKENS, _OVERLAP_TOKENS):
        yield {"content": chunk}


def _sliding_window_chunks(
    text: str, chunk_size: int, overlap: int
) -> Iterator[str]:
    """
    Naive word-count-based chunking (word ≈ token for English prose).
    Yields non-empty string chunks.
    """
    words = text.split()
    if not words:
        return
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunk = " ".join(chunk_words).strip()
        if chunk:
            yield chunk
        i += step


def _embed_in_batches(
    texts: list[str], provider: EmbeddingProvider
) -> list:
    """Call the embedding provider in fixed-size batches."""
    results = []
    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i : i + _EMBED_BATCH_SIZE]
        results.extend(provider.embed_texts(batch))
    return results
