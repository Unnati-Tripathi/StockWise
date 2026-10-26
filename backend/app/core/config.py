from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Application
    app_name: str = "StockWise API"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Database
    database_url: str = "postgresql+psycopg://stockwise_user:stockwise_pass@localhost/stockwise"

    # ── AI Provider ───────────────────────────────────────────────────────────
    # Set ai_provider="gemini" for real API calls; keep "mock" for offline dev
    # and automated tests.  The application will raise a clear error at startup
    # if ai_provider="gemini" but GEMINI_API_KEY is absent.
    ai_provider: str = "mock"  # "mock" | "gemini"

    # Gemini credentials & model selection
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.5-flash-lite"  # default: ultra-fast, capable, low-latency

    # Gemini embedding model
    gemini_embedding_model: str = "text-embedding-004"
    gemini_embedding_dimensions: int = 768

    # Gemini call behaviour
    gemini_timeout_seconds: int = 30
    gemini_max_retries: int = 3       # transient errors only (429, 503)
    gemini_max_tool_rounds: int = 3   # maximum function-calling iterations per chat turn

    # ── Invoice extraction ────────────────────────────────────────────────────
    # "mock" uses hardcoded demo data; "gemini" uses real document extraction.
    invoice_extraction_provider: str = "mock"  # "mock" | "gemini"
    # Configurable confidence threshold heuristic below which invoices require manual review
    invoice_confidence_threshold: float = 0.70

    # ── RAG / retrieval ───────────────────────────────────────────────────────
    rag_top_k: int = 5               # final chunks returned to the model
    rag_candidate_k: int = 20        # candidates fetched before RRF re-ranking
    rag_min_score: float = 0.0       # minimum RRF score; 0 = keep all candidates

    # CORS (restrict in production; "*" is fine for local dev)
    cors_allowed_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
