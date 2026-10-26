"""
Deterministic mock providers for automated tests and offline development.

These providers produce predictable, hardcoded outputs so that tests never
need a live API key.  They must not masquerade as real AI — every response
clearly identifies itself as mock output.

Usage
-----
These are selected automatically when ``ai_provider = "mock"`` in config, which
is the default.  Tests should never need to set ``GEMINI_API_KEY``.
"""
from __future__ import annotations

import json
from typing import Any

from app.providers.base import (
    EmbeddingProvider,
    EmbeddingResult,
    FunctionCall,
    LLMProvider,
    LLMResponse,
)


class MockLLMProvider(LLMProvider):
    """
    Deterministic mock LLM.

    Behaviour
    ---------
    - If ``tools`` are declared, the first call returns a function_call for the
      first tool with empty args.  The second call (with tool_results) returns
      a text summary.
    - Without tools, always returns a canned text reply.
    - ``_forced_responses`` lets individual tests inject specific reply sequences
      for more targeted assertions.
    """

    PROVIDER_NAME = "mock"

    def __init__(self, forced_responses: list[LLMResponse] | None = None) -> None:
        """
        Parameters
        ----------
        forced_responses:
            Optional sequence of responses to return in order.  When exhausted,
            falls back to default behaviour.  Useful for unit-testing specific
            tool-call sequences.
        """
        self._forced_responses = list(forced_responses or [])
        self._call_count = 0

    # ── LLMProvider interface ─────────────────────────────────────────────────

    def generate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        # Return forced responses if available
        if self._forced_responses:
            resp = self._forced_responses.pop(0)
            self._call_count += 1
            return resp

        self._call_count += 1

        has_tool_results = bool(tool_results) or any(
            "tool_results" in t or t.get("role") == "tool"
            for t in (conversation_history or [])
        )

        # Default: simulate one tool-call round if tools are provided and no results yet
        if tools and not has_tool_results:
            # Pick the first declared tool and call it with empty args
            first_tool_name = tools[0].get("name", "unknown_tool")
            return LLMResponse(
                function_calls=[FunctionCall(name=first_tool_name, args={})],
                model_used=self.PROVIDER_NAME,
            )

        # After tool results (or no tools): return a generic text answer
        summary_query = user_message
        if not summary_query and conversation_history:
            for t in reversed(conversation_history):
                if t.get("role") == "user" and t.get("content"):
                    summary_query = t["content"]
                    break

        return LLMResponse(
            text=(
                "[MOCK RESPONSE] This is a deterministic test reply. "
                "No live API was called. "
                f"Query: '{summary_query[:80]}'"
            ),
            input_tokens=10,
            output_tokens=20,
            model_used=self.PROVIDER_NAME,
        )

    def provider_name(self) -> str:
        return self.PROVIDER_NAME


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic mock embedding provider.

    Produces zero vectors of the configured dimensionality.  This is sufficient
    for integration tests that exercise the storage and retrieval plumbing
    without needing real semantic similarity.
    """

    PROVIDER_NAME = "mock-embedding"

    def __init__(self, dims: int = 768) -> None:
        self._dims = dims

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        return [
            EmbeddingResult(
                vector=[0.0] * self._dims,
                model_used=self.PROVIDER_NAME,
                dimensions=self._dims,
            )
            for _ in texts
        ]

    def embed_query(self, query: str) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[0.0] * self._dims,
            model_used=self.PROVIDER_NAME,
            dimensions=self._dims,
        )

    def dimensions(self) -> int:
        return self._dims

    def model_name(self) -> str:
        return self.PROVIDER_NAME
