"""
Google Gemini provider implementation.

Uses the official ``google-genai`` SDK (google-genai >= 0.8).

Key design decisions
--------------------
- Manual function calling (``AutomaticFunctionCallingConfig(disable=True)``) is
  used so that the application — not the SDK — controls which functions run and
  validates their arguments before execution.
- Retries use ``tenacity`` with exponential back-off, bounded to transient HTTP
  errors (429 rate-limit, 503 service unavailable).  Other errors are not
  retried.
- The API key is read from config and never logged or returned to callers.
- Token usage is extracted when available for observability.

Selection
---------
This provider is activated when ``ai_provider = "gemini"`` in app config.
If the key is absent at that point, ``ProviderConfigError`` is raised at
instantiation time so the problem is surfaced immediately on startup rather
than on the first user request.
"""
from __future__ import annotations

import logging
from typing import Any

import tenacity

from app.providers.base import (
    EmbeddingProvider,
    EmbeddingResult,
    FunctionCall,
    LLMProvider,
    LLMResponse,
    ProviderConfigError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)


def _is_transient(exc: BaseException) -> bool:
    """Return True for errors that are safe to retry."""
    if isinstance(exc, ProviderRateLimitError):
        return True
    try:
        # google-genai raises google.genai.errors.APIError with a status code
        from google.genai import errors as genai_errors  # type: ignore[import]
        if isinstance(exc, genai_errors.APIError):
            return exc.code in (429, 503, 500)
    except ImportError:
        pass
    return False


def _retry_decorator(max_attempts: int, wait_min: float = 0.05, wait_max: float = 30.0):
    """Build a tenacity retry decorator for transient provider errors."""
    return tenacity.retry(
        retry=tenacity.retry_if_exception(_is_transient),
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential(multiplier=0.05, min=wait_min, max=wait_max),
        reraise=True,
    )


class GeminiLLMProvider(LLMProvider):
    """
    Production LLM provider backed by Google Gemini.

    Parameters
    ----------
    api_key:
        Gemini API key.  Must not be None when this provider is instantiated.
    model:
        Model identifier string, e.g. ``"gemini-3.5-flash-lite"``.
    timeout_seconds:
        Per-request timeout.
    max_retries:
        Maximum retry attempts for transient errors.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is required when ai_provider='gemini'. "
                "Set it in backend/.env and never commit it to Git."
            )
        try:
            from google import genai  # type: ignore[import]
            from google.genai import types  # type: ignore[import]
        except ImportError as exc:
            raise ProviderConfigError(
                "google-genai package is not installed. "
                "Run: pip install google-genai"
            ) from exc

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max_retries

        logger.info(
            "GeminiLLMProvider initialised — model=%s timeout=%ds max_retries=%d",
            model,
            timeout_seconds,
            max_retries,
        )

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
        """
        Send a request to Gemini and return a normalised response.

        The model is always called with ``AutomaticFunctionCallingConfig(disable=True)``
        so we control exactly when and how tools are executed.
        """
        types = self._types

        # Build contents list
        contents: list[Any] = []

        # Add conversation history turns (supports text, function calls, and tool responses)
        for turn in (conversation_history or []):
            role = turn.get("role", "user")
            if turn.get("raw_content") is not None:
                contents.append(turn["raw_content"])
            elif turn.get("function_calls"):
                parts = [
                    types.Part.from_function_call(name=fc["name"], args=fc.get("args", {}))
                    for fc in turn["function_calls"]
                ]
                contents.append(types.Content(role="model", parts=parts))
            elif turn.get("tool_results"):
                parts = [
                    types.Part.from_function_response(
                        name=tr["name"],
                        response={"result": tr.get("result")},
                    )
                    for tr in turn["tool_results"]
                ]
                contents.append(types.Content(role="user", parts=parts))
            elif turn.get("content"):
                mapped_role = "model" if role in ("model", "assistant") else "user"
                contents.append(
                    types.Content(
                        role=mapped_role,
                        parts=[types.Part.from_text(text=turn["content"])],
                    )
                )

        # Add current user message if provided
        if user_message:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_message)],
                )
            )

        # Add direct tool results if passed
        if tool_results:
            fn_responses = []
            for tr in tool_results:
                fn_responses.append(
                    types.Part.from_function_response(
                        name=tr["name"],
                        response={"result": tr.get("result")},
                    )
                )
            contents.append(types.Content(role="user", parts=fn_responses))

        # Build tool declarations from caller-supplied schema dicts
        gemini_tools = None
        if tools:
            gemini_tools = self._build_tool_declarations(tools)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            tools=gemini_tools,
        )

        raw_response = self._call_with_retry(contents=contents, config=config)
        return self._parse_response(raw_response)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _call_with_retry(self, *, contents: list[Any], config: Any) -> Any:
        """Call the Gemini API with exponential back-off on transient errors."""
        retry = _retry_decorator(self._max_retries)

        @retry
        def _inner():
            try:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                exc_type = type(exc).__name__
                # Map well-known error types to our custom exceptions
                try:
                    from google.genai import errors as genai_errors  # type: ignore[import]
                    if isinstance(exc, genai_errors.APIError):
                        if exc.code in (429, 503, 500):
                            logger.warning("Gemini transient error %d — %s", exc.code, exc)
                            raise  # Let tenacity retry
                        logger.error("Gemini API error %d — %s", exc.code, exc)
                        raise ProviderError(f"Gemini API error {exc.code}: {exc}") from exc
                except ImportError:
                    pass
                logger.error("Unexpected provider error (%s): %s", exc_type, exc)
                raise ProviderError(f"Provider call failed ({exc_type}): {exc}") from exc

        try:
            return _inner()
        except tenacity.RetryError as exc:
            raise ProviderRateLimitError(
                f"Gemini request failed after {self._max_retries} retries"
            ) from exc
        except Exception as exc:
            from google.genai import errors as genai_errors
            if isinstance(exc, genai_errors.APIError):
                if exc.code == 429:
                    raise ProviderRateLimitError(
                        f"Gemini rate limit exceeded after {self._max_retries} retries: {exc}"
                    ) from exc
                raise ProviderError(
                    f"Gemini API error {exc.code} after retries: {exc}"
                ) from exc
            raise

    def _build_tool_declarations(self, tools: list[dict[str, Any]]) -> list[Any]:
        """Convert our internal tool schema dicts to Gemini FunctionDeclaration objects."""
        types = self._types
        declarations = []
        for t in tools:
            # Our schema format: {name, description, parameters: {type, properties, required}}
            params = t.get("parameters", {})
            declarations.append(
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t["name"],
                            description=t.get("description", ""),
                            parameters=types.Schema(
                                type=types.Type.OBJECT,
                                properties={
                                    k: types.Schema(
                                        type=types.Type[v.get("type", "STRING").upper()],
                                        description=v.get("description", ""),
                                        enum=v.get("enum"),
                                    )
                                    for k, v in params.get("properties", {}).items()
                                },
                                required=params.get("required", []),
                            ),
                        )
                    ]
                )
            )
        return declarations

    def _parse_response(self, raw: Any) -> LLMResponse:
        """
        Parse a raw Gemini API response into a normalised LLMResponse.

        Raises ProviderError for malformed responses.
        """
        try:
            # Extract token usage when available
            usage = getattr(raw, "usage_metadata", None)
            input_tok = getattr(usage, "prompt_token_count", None) if usage else None
            output_tok = getattr(usage, "candidates_token_count", None) if usage else None

            raw_content = None
            if getattr(raw, "candidates", None) and len(raw.candidates) > 0:
                raw_content = raw.candidates[0].content

            # Check for function calls first
            if raw.function_calls:
                calls = [
                    FunctionCall(name=fc.name, args=dict(fc.args))
                    for fc in raw.function_calls
                ]
                return LLMResponse(
                    function_calls=calls,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    model_used=self._model,
                    raw_content=raw_content,
                )

            # Text response
            text = raw.text
            if text is None:
                raise ProviderError(
                    "Gemini returned an empty response with no text and no function calls. "
                    "The model may have refused the request or hit a safety filter."
                )

            return LLMResponse(
                text=text,
                input_tokens=input_tok,
                output_tokens=output_tok,
                model_used=self._model,
                raw_content=raw_content,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Failed to parse Gemini response: {exc}"
            ) from exc

    def provider_name(self) -> str:
        return f"gemini/{self._model}"


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using Gemini text-embedding-004.

    Embeddings are generated during document ingestion (offline) and at query
    time.  The model identifier is stored alongside each vector so that
    compatibility issues are detectable.
    """

    TASK_TYPE_DOCUMENT = "RETRIEVAL_DOCUMENT"
    TASK_TYPE_QUERY = "RETRIEVAL_QUERY"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-004",
        dimensions: int = 768,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is required for GeminiEmbeddingProvider."
            )
        try:
            from google import genai  # type: ignore[import]
        except ImportError as exc:
            raise ProviderConfigError(
                "google-genai package is not installed."
            ) from exc

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dims = dimensions
        self._max_retries = max_retries

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        if not texts:
            return []

        retry = _retry_decorator(self._max_retries)

        @retry
        def _call():
            from google import genai  # type: ignore[import]
            return self._client.models.embed_content(
                model=self._model,
                contents=texts,
                config={"task_type": self.TASK_TYPE_DOCUMENT},
            )

        try:
            response = _call()
        except tenacity.RetryError as exc:
            raise ProviderRateLimitError("Embedding request failed after retries") from exc

        results = []
        for emb in response.embeddings:
            values = list(emb.values)
            results.append(
                EmbeddingResult(
                    vector=values,
                    model_used=self._model,
                    dimensions=len(values),
                )
            )
        return results

    def embed_query(self, query: str) -> EmbeddingResult:
        retry = _retry_decorator(self._max_retries)

        @retry
        def _call():
            return self._client.models.embed_content(
                model=self._model,
                contents=[query],
                config={"task_type": self.TASK_TYPE_QUERY},
            )

        try:
            response = _call()
        except tenacity.RetryError as exc:
            raise ProviderRateLimitError("Query embedding failed after retries") from exc

        values = list(response.embeddings[0].values)
        return EmbeddingResult(
            vector=values,
            model_used=self._model,
            dimensions=len(values),
        )

    def dimensions(self) -> int:
        return self._dims

    def model_name(self) -> str:
        return self._model
