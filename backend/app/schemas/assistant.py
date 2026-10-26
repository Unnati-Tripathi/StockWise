"""
Enriched assistant schemas for Phase 2 function-calling upgrade.

The response now includes structured fields showing which tools fired,
what evidence was gathered, and which sources were consulted — making
the assistant fully auditable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class AssistantRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_history: Optional[List[ChatMessage]] = []


# ── Evidence / traceability ────────────────────────────────────────────────────

class EvidenceData(BaseModel):
    """Raw tool result data included for UI display and auditability."""
    tool_name: str
    data: Any


class ToolCall(BaseModel):
    """Record of a single tool invocation during assistant reasoning."""
    tool_name: str
    arguments: dict[str, Any] = {}
    result_count: int = 0          # number of records returned
    result_summary: str = ""       # short human-readable summary


class SourceReference(BaseModel):
    """Provenance of a piece of information used in the reply."""
    source_type: Literal["database", "document", "model"]
    reference: str                 # e.g. "inventory.batches", "supplier_sop.pdf"


# ── Response ──────────────────────────────────────────────────────────────────

class AssistantResponse(BaseModel):
    """
    Full response from the assistant, including the reply text and all
    traceability metadata so the UI can show users where data came from.
    """
    reply: str
    # Legacy field — kept for backwards compatibility with existing tests
    evidence: Optional[EvidenceData] = None
    # New Phase-2 fields
    tools_used: List[ToolCall] = []
    sources: List[SourceReference] = []
    data_freshness: Optional[datetime] = None
    warnings: List[str] = []
    provider: str = "mock"         # "mock" | "gemini/gemini-3.5-flash-lite" etc.

    model_config = ConfigDict(from_attributes=True)
