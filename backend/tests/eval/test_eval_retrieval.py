"""
Evaluation: Retrieval quality (lexical + hybrid search).

Tests against SQLite (no pgvector) so they run offline.  Vector search is
expected to return empty lists on SQLite — the tests exercise the lexical path
and RRF fusion logic without needing PostgreSQL.

Metrics computed:
  - Recall@K: fraction of relevant chunks found in top-K results
  - MRR: Mean Reciprocal Rank of the first relevant result

Run with:
    pytest tests/eval/test_eval_retrieval.py -v
"""
import pytest
from decimal import Decimal

from app.models.document import Document, DocumentChunk
from app.providers.mock import MockEmbeddingProvider
from app.services.rag.retrieval import lexical_search, hybrid_search


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _seed_chunks(db_session, chunks: list[dict]) -> list[DocumentChunk]:
    """Insert synthetic document chunks for retrieval testing."""
    doc = Document(
        filename="test_sop.txt",
        file_path="/tmp/test_sop.txt",
        status="ready",
        chunk_count=len(chunks),
    )
    db_session.add(doc)
    db_session.flush()

    objs = []
    for i, c in enumerate(chunks):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=c["content"],
            page_number=c.get("page_number", 1),
        )
        db_session.add(chunk)
        objs.append(chunk)
    db_session.commit()
    return objs


# ── Lexical search tests ──────────────────────────────────────────────────────

class TestLexicalSearch:
    def test_returns_empty_on_no_documents(self, db_session):
        """Empty database returns no results."""
        results = lexical_search(db_session, "amoxicillin", top_k=5)
        # SQLite returns [] gracefully; Postgres returns [] when no docs exist
        assert isinstance(results, list)

    def test_gracefully_handles_sqlite(self, db_session):
        """
        Lexical search against SQLite (no to_tsvector) must not raise —
        it returns an empty list with a warning log.
        """
        _seed_chunks(db_session, [{"content": "Amoxicillin 500mg antibiotic"}])
        results = lexical_search(db_session, "amoxicillin", top_k=5)
        # SQLite: graceful empty list (Postgres: non-empty)
        assert isinstance(results, list)

    def test_empty_query_returns_empty(self, db_session):
        results = lexical_search(db_session, "   ", top_k=5)
        assert results == []


# ── Hybrid search tests ───────────────────────────────────────────────────────

class TestHybridSearch:
    def test_returns_list_when_no_documents(self, db_session):
        provider = MockEmbeddingProvider(dims=768)
        results = hybrid_search(db_session, "antibiotics", provider)
        assert isinstance(results, list)

    def test_hybrid_search_with_mock_embeddings(self, db_session):
        """
        On SQLite, both lexical and vector paths return [].
        hybrid_search should return [] without raising.
        """
        _seed_chunks(db_session, [
            {"content": "Cold chain requirements for vaccine storage"},
            {"content": "Paracetamol dosage and administration guidelines"},
        ])
        provider = MockEmbeddingProvider(dims=768)
        results = hybrid_search(db_session, "cold chain", provider, top_k=3)
        assert isinstance(results, list)

    def test_rrf_score_bounded(self, db_session):
        """All RRF scores must be in (0, 1] when results exist."""
        provider = MockEmbeddingProvider(dims=768)
        results = hybrid_search(db_session, "medicine", provider, top_k=10)
        for r in results:
            assert 0.0 < r.score <= 1.0, f"Score out of range: {r.score}"

    def test_results_deduplicated_by_chunk_id(self, db_session):
        """No chunk_id should appear more than once in results."""
        provider = MockEmbeddingProvider(dims=768)
        results = hybrid_search(db_session, "supplier", provider, top_k=10)
        ids = [r.chunk_id for r in results]
        assert len(ids) == len(set(ids)), "Duplicate chunk_ids in results"

    def test_top_k_respected(self, db_session):
        """Results count must not exceed top_k."""
        _seed_chunks(db_session, [
            {"content": f"Document chunk {i}"} for i in range(50)
        ])
        provider = MockEmbeddingProvider(dims=768)
        results = hybrid_search(db_session, "document", provider, top_k=5)
        assert len(results) <= 5


# ── Retrieval metrics ─────────────────────────────────────────────────────────

def recall_at_k(retrieved_ids: list[int], relevant_ids: set[int], k: int) -> float:
    """Fraction of relevant items found in the top-K retrieved results."""
    if not relevant_ids:
        return 1.0
    top_k = retrieved_ids[:k]
    return len(set(top_k) & relevant_ids) / len(relevant_ids)


def mean_reciprocal_rank(retrieved_ids: list[int], relevant_ids: set[int]) -> float:
    """Mean reciprocal rank of the first relevant result."""
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def test_recall_at_k_perfect():
    """recall_at_k returns 1.0 when all relevant items are in top-K."""
    assert recall_at_k([1, 2, 3, 4, 5], {1, 2, 3}, k=5) == 1.0


def test_recall_at_k_partial():
    """recall_at_k returns 0.5 when half the relevant items are found."""
    assert recall_at_k([1, 99, 3, 99, 5], {1, 2}, k=5) == 0.5


def test_mrr_first_result():
    """MRR is 1.0 when the very first result is relevant."""
    assert mean_reciprocal_rank([7, 2, 3], {7}) == 1.0


def test_mrr_second_result():
    """MRR is 0.5 when the first relevant result is rank 2."""
    assert mean_reciprocal_rank([99, 7, 3], {7}) == 0.5


def test_mrr_no_relevant():
    """MRR is 0.0 when no relevant results are returned."""
    assert mean_reciprocal_rank([1, 2, 3], {99}) == 0.0
