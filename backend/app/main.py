# pyrefly: ignore [missing-import]
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.routes import router as api_v1_router

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: recover any stuck documents from prior server restarts
    try:
        from app.db.session import SessionLocal
        from app.services.rag.document_store import recover_stuck_documents
        with SessionLocal() as db:
            recovered = recover_stuck_documents(db)
            if recovered:
                logger.info("Recovered %d stuck documents during startup", recovered)
    except Exception as exc:
        logger.warning("Could not run document recovery on startup: %s", exc)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Parse CORS allowed origins
cors_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]
if not cors_origins or "*" in cors_origins:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


app.include_router(api_v1_router, prefix="/api/v1")
