"""
Health check endpoint with database connectivity probe.

Returns:
  {"status": "ok", "db": "ok", "ai_provider": "mock|gemini/..."}

Never exposes API keys or internal configuration values.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_db

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    db: str
    ai_provider: str


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """
    Liveness + readiness probe.

    - ``status`` is "ok" when the process is running.
    - ``db`` is "ok" when a SELECT 1 succeeds, "error" otherwise.
    - ``ai_provider`` reports the configured provider name (no key material).
    """
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    return HealthResponse(
        status="ok",
        service="stockwise-api",
        version=settings.app_version,
        db=db_status,
        ai_provider=settings.ai_provider,
    )
