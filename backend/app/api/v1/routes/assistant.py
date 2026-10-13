from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.assistant import AssistantRequest, AssistantResponse, EvidenceData
from app.services.assistant import AssistantService

router = APIRouter()

@router.post("/chat", response_model=AssistantResponse)
def chat_with_assistant(request: AssistantRequest, db: Session = Depends(get_db)):
    service = AssistantService(db)
    result = service.chat(request.query)
    
    evidence = None
    if result.get("evidence"):
        evidence = EvidenceData(
            tool_name=result["evidence"]["tool_name"],
            data=result["evidence"]["data"]
        )
        
    return AssistantResponse(
        reply=result["reply"],
        evidence=evidence
    )
