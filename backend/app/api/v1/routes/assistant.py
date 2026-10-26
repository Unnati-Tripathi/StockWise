import logging
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

logger = logging.getLogger("app.api.assistant")

from app.db.session import get_db
from app.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
    EvidenceData,
    ToolCall,
    SourceReference,
)
from app.services.assistant import AssistantService

router = APIRouter()


@router.post("/chat", response_model=AssistantResponse)
def chat_with_assistant(request: AssistantRequest, db: Session = Depends(get_db)):
    service = AssistantService(db)
    session_history = (
        [{"role": m.role, "content": m.content} for m in request.session_history]
        if request.session_history
        else None
    )
    try:
        result = service.chat(request.query, session_history=session_history)
    except Exception as exc:
        logger.error("Assistant chat execution error: %s", exc, exc_info=True)
        return AssistantResponse(
            reply=f"AI service error: {exc}",
            tools_used=[],
            sources=[],
            warnings=[str(exc)],
            provider="error",
        )

    # Build legacy evidence object for backwards compat
    evidence = None
    if result.get("evidence"):
        evidence = EvidenceData(
            tool_name=result["evidence"]["tool_name"],
            data=result["evidence"]["data"],
        )

    # Build enriched tool call records
    tools_used = [
        ToolCall(
            tool_name=tc["tool_name"],
            arguments=tc.get("arguments", {}),
            result_count=tc.get("result_count", 0),
            result_summary=tc.get("result_summary", ""),
        )
        for tc in result.get("tools_used", [])
    ]

    # Build source references
    sources = [
        SourceReference(
            source_type=s["source_type"],
            reference=s["reference"],
        )
        for s in result.get("sources", [])
    ]

    # Parse freshness timestamp
    freshness = result.get("data_freshness")
    if isinstance(freshness, str):
        try:
            freshness = datetime.fromisoformat(freshness)
        except ValueError:
            freshness = None

    return AssistantResponse(
        reply=result["reply"],
        evidence=evidence,
        tools_used=tools_used,
        sources=sources,
        data_freshness=freshness,
        warnings=result.get("warnings", []),
        provider=result.get("provider", "mock"),
    )
