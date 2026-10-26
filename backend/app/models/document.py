"""
SQLAlchemy models for uploaded documents and their text chunks.

The ``content_tsv`` column is a PostgreSQL-generated TSVECTOR used for full-text
(lexical) search.  The ``embedding`` column is a pgvector VECTOR(768) used for
semantic search.  Both are populated during the ingestion pipeline.

For SQLite test databases the pgvector column type falls back gracefully — tests
that exercise the RAG plumbing can run against SQLite if they use mock embeddings
and skip the cosine-similarity query (see retrieval.py for the guard).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import]
    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False
    Vector = None  # type: ignore[assignment,misc]


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(sa.String(500))
    doc_type: Mapped[str | None] = mapped_column(
        sa.String(100),
        comment="e.g. supplier_policy, sop, medicine_ref",
    )
    # SHA-256 hex digest of raw file bytes — used for deduplication
    file_hash: Mapped[str | None] = mapped_column(sa.String(64), unique=True)
    file_path: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(50),
        default="pending",
        server_default="pending",
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    embedding_model: Mapped[str | None] = mapped_column(sa.String(100))
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status!r}>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(sa.Integer)
    section_heading: Mapped[str | None] = mapped_column(sa.String(500))
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(sa.String(100))
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    # pgvector column — only registered when the extension is available
    if _HAS_PGVECTOR and Vector is not None:
        embedding: Mapped[list[float] | None] = mapped_column(
            Vector(768), nullable=True
        )
    else:
        # Fallback for environments without pgvector (e.g. SQLite CI tests)
        embedding: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="chunks"
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id} doc={self.document_id} "
            f"idx={self.chunk_index}>"
        )
