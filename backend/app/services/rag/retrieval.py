"""
Hybrid retrieval pipeline for the RAG system.

Search strategies
-----------------
- Lexical search: PostgreSQL ``ts_rank`` on a ``to_tsvector`` index over chunk content.
  Falls back gracefully when running against SQLite (returns empty list with a warning).
- Vector search: Cosine similarity via pgvector operator ``<=>```.
  Falls back gracefully when pgvector is unavailable.
- Hybrid search: Reciprocal Rank Fusion (RRF) of lexical + vector results,
  de-duplicated by chunk id and filtered by ``min_score``.

All public functions are read-only and safe for concurrent callers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentChunk
from app.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)

# RRF constant — standard value from the literature
_RRF_K = 60


@dataclass
class RetrievedChunk:
    """A single retrieved text chunk with provenance metadata."""
    chunk_id: int
    document_id: int
    document_filename: str
    chunk_index: int
    page_number: int | None
    section_heading: str | None
    content: str
    score: float
    match_type: str   # "lexical" | "vector" | "hybrid"


def lexical_search(
    db: Session,
    query: str,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """
    Full-text lexical search using PostgreSQL ``ts_rank``.

    Returns an empty list when running against SQLite (no ``to_tsvector`` support).
    """
    query = query.strip()
    if not query:
        return []

    try:
        sql = text("""
            SELECT
                dc.id              AS chunk_id,
                dc.document_id,
                d.filename         AS document_filename,
                dc.chunk_index,
                dc.page_number,
                dc.section_heading,
                dc.content,
                ts_rank(
                    to_tsvector('english', dc.content),
                    plainto_tsquery('english', :query)
                ) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.status = 'ready'
              AND to_tsvector('english', dc.content) @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :top_k
        """)
        rows = db.execute(sql, {"query": query, "top_k": top_k}).mappings().all()
    except Exception as exc:
        logger.warning("Lexical search unavailable (likely SQLite): %s", exc)
        return []

    return [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            document_filename=r["document_filename"],
            chunk_index=r["chunk_index"],
            page_number=r["page_number"],
            section_heading=r["section_heading"],
            content=r["content"],
            score=float(r["score"]),
            match_type="lexical",
        )
        for r in rows
    ]


def vector_search(
    db: Session,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """
    Semantic vector search using pgvector cosine distance.

    Returns an empty list when pgvector is not installed.
    """
    try:
        vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        sql = text("""
            SELECT
                dc.id              AS chunk_id,
                dc.document_id,
                d.filename         AS document_filename,
                dc.chunk_index,
                dc.page_number,
                dc.section_heading,
                dc.content,
                1 - (dc.embedding <=> :vec::vector) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.status = 'ready'
              AND dc.embedding IS NOT NULL
            ORDER BY dc.embedding <=> :vec::vector
            LIMIT :top_k
        """)
        rows = db.execute(sql, {"vec": vector_str, "top_k": top_k}).mappings().all()
    except Exception as exc:
        logger.warning("Vector search unavailable (pgvector not installed?): %s", exc)
        return []

    return [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            document_filename=r["document_filename"],
            chunk_index=r["chunk_index"],
            page_number=r["page_number"],
            section_heading=r["section_heading"],
            content=r["content"],
            score=max(0.0, float(r["score"])),
            match_type="vector",
        )
        for r in rows
    ]


def hybrid_search(
    db: Session,
    query: str,
    embedding_provider: EmbeddingProvider,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """
    Hybrid search combining lexical and vector results via Reciprocal Rank Fusion.

    Parameters
    ----------
    db:
        Database session.
    query:
        Natural language search query.
    embedding_provider:
        Provider used to embed the query.
    top_k:
        Number of final results (defaults to ``settings.rag_top_k``).
    min_score:
        Minimum RRF score threshold (defaults to ``settings.rag_min_score``).

    Returns
    -------
    list[RetrievedChunk]
        Fused, de-duplicated results ordered by RRF score descending.
    """
    _top_k = top_k if top_k is not None else settings.rag_top_k
    _min_score = min_score if min_score is not None else settings.rag_min_score
    candidate_k = settings.rag_candidate_k

    # Embed the query
    query_emb = embedding_provider.embed_query(query)

    # Run both searches in parallel (synchronous in this sync context)
    lex_results = lexical_search(db, query, top_k=candidate_k)
    vec_results = vector_search(db, query_emb.vector, top_k=candidate_k)

    if not lex_results and not vec_results:
        return []

    # Reciprocal Rank Fusion
    rrf_scores: dict[int, float] = {}
    best_chunk: dict[int, RetrievedChunk] = {}

    for rank, chunk in enumerate(lex_results, start=1):
        rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
        best_chunk[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(vec_results, start=1):
        rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
        if chunk.chunk_id not in best_chunk:
            best_chunk[chunk.chunk_id] = chunk

    # Sort by RRF score, apply min_score filter, take top_k
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for chunk_id, score in ranked:
        if score < _min_score:
            continue
        chunk = best_chunk[chunk_id]
        results.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_filename=chunk.document_filename,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section_heading=chunk.section_heading,
                content=chunk.content,
                score=score,
                match_type="hybrid",
            )
        )
        if len(results) >= _top_k:
            break

    logger.info(
        "hybrid_search: query=%r  lex=%d  vec=%d  fused=%d  returned=%d",
        query[:60], len(lex_results), len(vec_results),
        len(rrf_scores), len(results),
    )
    return results
