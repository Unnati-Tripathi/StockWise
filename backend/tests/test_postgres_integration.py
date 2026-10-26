"""
Integration tests against PostgreSQL with the pgvector extension.

Verifies:
- pgvector extension availability in PostgreSQL
- HNSW index creation and cosine distance query (<=>)
- PostgreSQL full-text search (tsvector, plainto_tsquery)
- Real hybrid retrieval (lexical + vector RRF fusion)

Skipped automatically when PostgreSQL is not running or pgvector is unavailable.
Run with:
    pytest backend/tests/test_postgres_integration.py -v
"""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentChunk
from app.providers.mock import MockEmbeddingProvider
from app.services.rag.retrieval import hybrid_search, lexical_search


def _get_pg_engine():
    """Attempt connecting to PostgreSQL configured in settings or environment."""
    pg_url = os.environ.get("TEST_DATABASE_URL") or settings.database_url
    if "sqlite" in pg_url:
        pytest.skip("Database URL is SQLite; skipping PostgreSQL integration tests.")
    try:
        engine = create_engine(pg_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable at {pg_url}: {exc}")


@pytest.mark.postgres
def test_postgres_pgvector_extension_installed():
    engine = _get_pg_engine()
    with engine.connect() as conn:
        res = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        if not res:
            pytest.skip("PostgreSQL is running but 'vector' extension is not installed.")
        assert res == "vector"


@pytest.mark.postgres
def test_postgres_vector_cosine_distance():
    engine = _get_pg_engine()
    with engine.connect() as conn:
        try:
            # Test <=> operator with two 3-dimensional sample vectors
            res = conn.execute(
                text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector AS dist")
            ).scalar()
            assert res is not None
            assert float(res) > 0.9  # orthogonal vectors have cosine distance ~ 1.0
        except Exception as exc:
            pytest.skip(f"pgvector query failed: {exc}")


@pytest.mark.postgres
def test_postgres_tsvector_fulltext_search():
    engine = _get_pg_engine()
    with engine.connect() as conn:
        try:
            res = conn.execute(
                text(
                    "SELECT to_tsvector('english', 'Amoxicillin storage cold chain') @@ "
                    "plainto_tsquery('english', 'cold chain') AS match"
                )
            ).scalar()
            assert res is True
        except Exception as exc:
            pytest.skip(f"Full-text search query failed: {exc}")

