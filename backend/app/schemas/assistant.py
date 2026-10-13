from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any

class ChatMessage(BaseModel):
    role: str
    content: str
    
class AssistantRequest(BaseModel):
    query: str
    session_history: Optional[List[ChatMessage]] = []

class EvidenceData(BaseModel):
    tool_name: str
    data: Any

class AssistantResponse(BaseModel):
    reply: str
    evidence: Optional[EvidenceData] = None
    
    model_config = ConfigDict(from_attributes=True)
