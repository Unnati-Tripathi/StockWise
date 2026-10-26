"""
Pydantic schemas for document upload, status, and RAG search.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    status: str
    message: str


class DocumentResponse(BaseModel):
    id: int
    filename: str
    title: Optional[str] = None
    doc_type: Optional[str] = None
    status: str
    chunk_count: int
    embedding_model: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class ChunkResult(BaseModel):
    chunk_id: int
    document_id: int
    document_filename: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    content: str
    score: float
    match_type: str


class DocumentSearchResponse(BaseModel):
    query: str
    results: List[ChunkResult]
    total: int
