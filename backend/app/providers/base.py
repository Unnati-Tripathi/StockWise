"""
Abstract base classes for LLM and embedding providers.

All provider-specific code must live outside this file.
Business logic must depend only on these interfaces.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


# ── Shared data types ────────────────────────────────────────────────────────

@dataclass
class FunctionCall:
    """A model-requested function invocation."""
    name: str
    args: dict[str, Any]


@dataclass
class LLMResponse:
    """
    Normalised response from any LLM provider.

    Exactly one of `text` or `function_calls` will be populated on any given
    response.  When the model returns a final answer, `text` is set and
    `function_calls` is empty.  When the model wants to invoke tools,
    `function_calls` is non-empty and `text` is None.
    """
    text: str | None = None
    function_calls: list[FunctionCall] = field(default_factory=list)
    # Diagnostics — None when unavailable (mock, old SDK versions, etc.)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None
    raw_content: Any = None


@dataclass
class EmbeddingResult:
    """Embedding vector for a single text chunk."""
    vector: list[float]
    model_used: str
    dimensions: int


# ── Abstract interfaces ──────────────────────────────────────────────────────

class LLMProvider(abc.ABC):
    """
    Contract that all LLM providers must satisfy.

    Implementations must:
    - Be stateless (safe to call from multiple threads/requests).
    - Never expose secrets in return values or log messages.
    - Raise `ProviderError` for unrecoverable failures.
    - Raise `ProviderConfigError` if required configuration is absent.
    """

    @abc.abstractmethod
    def generate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """
        Generate a response from the model.

        Parameters
        ----------
        system_prompt:
            Concise system instructions.  Kept separate from user content to
            resist prompt injection.
        user_message:
            The user's question or the current turn's content.
        tools:
            Optional list of tool declarations in the format expected by the
            provider (passed through from the assistant service).
        tool_results:
            Results from previously executed tool calls to feed back to the
            model in a multi-turn loop.
        conversation_history:
            Previous turns for multi-turn conversations.

        Returns
        -------
        LLMResponse
            Either a final text answer or a list of requested function calls.
        """
        ...

    @abc.abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable provider identifier (never includes secrets)."""
        ...


class EmbeddingProvider(abc.ABC):
    """Contract that all embedding providers must satisfy."""

    @abc.abstractmethod
    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """
        Generate embeddings for a batch of texts.

        Parameters
        ----------
        texts:
            Non-empty list of text chunks.  Maximum batch size is provider-
            dependent; callers should chunk large lists appropriately.

        Returns
        -------
        list[EmbeddingResult]
            One result per input text, in the same order.
        """
        ...

    @abc.abstractmethod
    def embed_query(self, query: str) -> EmbeddingResult:
        """Generate an embedding for a single search query."""
        ...

    @abc.abstractmethod
    def dimensions(self) -> int:
        """Return the vector dimensionality produced by this provider."""
        ...

    @abc.abstractmethod
    def model_name(self) -> str:
        """Return the embedding model identifier (for storage alongside vectors)."""
        ...


# ── Custom exceptions ────────────────────────────────────────────────────────

class ProviderError(RuntimeError):
    """Unrecoverable provider failure (bad response, parse error, etc.)."""


class ProviderConfigError(ProviderError):
    """Required configuration is missing or invalid."""


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded after all retries."""


class ProviderTimeoutError(ProviderError):
    """Provider did not respond within the configured timeout."""
