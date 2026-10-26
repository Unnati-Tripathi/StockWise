"""
Provider factory functions.

Call ``get_llm_provider()`` and ``get_embedding_provider()`` from application
code.  Provider instances are cached as module-level singletons so the
Gemini client is initialised once per process.

Configuration is read from ``app.core.config.settings`` on first access.
"""
from __future__ import annotations

import logging

from app.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfigError,
)

logger = logging.getLogger(__name__)

# Module-level singletons (None = not yet initialised)
_llm_provider: LLMProvider | None = None
_embedding_provider: EmbeddingProvider | None = None


def get_llm_provider() -> LLMProvider:
    """
    Return the configured LLM provider singleton.

    Raises
    ------
    ProviderConfigError
        If ``ai_provider = "gemini"`` but ``GEMINI_API_KEY`` is not set.
    ValueError
        If ``ai_provider`` has an unrecognised value.
    """
    global _llm_provider
    if _llm_provider is not None:
        return _llm_provider

    from app.core.config import settings

    provider_name = settings.ai_provider.lower()

    if provider_name == "mock":
        from app.providers.mock import MockLLMProvider
        _llm_provider = MockLLMProvider()
        logger.info("LLM provider: mock (no API calls will be made)")

    elif provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ProviderConfigError(
                "ai_provider is set to 'gemini' but GEMINI_API_KEY is not configured. "
                "Add it to backend/.env — do not commit it to Git."
            )
        from app.providers.gemini import GeminiLLMProvider
        _llm_provider = GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_retries=settings.gemini_max_retries,
        )
        logger.info("LLM provider: gemini  model=%s", settings.gemini_model)

    else:
        raise ValueError(
            f"Unknown ai_provider value: '{provider_name}'. "
            "Supported values: 'mock', 'gemini'."
        )

    return _llm_provider


def get_embedding_provider() -> EmbeddingProvider:
    """
    Return the configured embedding provider singleton.

    In mock mode, returns a zero-vector mock.
    In gemini mode, returns GeminiEmbeddingProvider.

    Raises
    ------
    ProviderConfigError
        If ``ai_provider = "gemini"`` but ``GEMINI_API_KEY`` is not set.
    """
    global _embedding_provider
    if _embedding_provider is not None:
        return _embedding_provider

    from app.core.config import settings

    provider_name = settings.ai_provider.lower()

    if provider_name == "mock":
        from app.providers.mock import MockEmbeddingProvider
        _embedding_provider = MockEmbeddingProvider(
            dims=settings.gemini_embedding_dimensions
        )
        logger.info("Embedding provider: mock")

    elif provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ProviderConfigError(
                "ai_provider is set to 'gemini' but GEMINI_API_KEY is not configured."
            )
        from app.providers.gemini import GeminiEmbeddingProvider
        _embedding_provider = GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
            dimensions=settings.gemini_embedding_dimensions,
            max_retries=settings.gemini_max_retries,
        )
        logger.info(
            "Embedding provider: gemini  model=%s  dims=%d",
            settings.gemini_embedding_model,
            settings.gemini_embedding_dimensions,
        )

    else:
        raise ValueError(f"Unknown ai_provider: '{provider_name}'")

    return _embedding_provider


def reset_providers() -> None:
    """
    Reset cached provider singletons.

    Call this in tests that need to swap providers mid-run, or after changing
    config in a test fixture.
    """
    global _llm_provider, _embedding_provider
    _llm_provider = None
    _embedding_provider = None
