"""add pgvector and document tables

Revision ID: c1d2e3f4a5b6
Revises: def314ee3e0d
Create Date: 2024-01-15 10:00:00.000000

Creates:
  - pgvector extension (idempotent)
  - documents table
  - document_chunks table with GIN index for FTS and HNSW index for vectors
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'def314ee3e0d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent — safe to run multiple times)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("doc_type", sa.String(100), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_heading", sa.String(500), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Add vector column separately so it can use the pgvector type
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN embedding vector(768)"
    )

    # Full-text search index (GIN on content)
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts "
        "ON document_chunks USING GIN(to_tsvector('english', content))"
    )

    # Vector similarity index (HNSW for approximate nearest-neighbour)
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw(embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")
    # Do NOT drop the vector extension — it may be shared
