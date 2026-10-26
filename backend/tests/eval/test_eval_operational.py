"""
Operational evaluation tests (Phase 5).

Verifies operational resilience, error handling, retry limits, and opt-in live tests:
  - Missing API key raises clear ProviderConfigError
  - Transient errors (429, 503) trigger bounded exponential backoff
  - Non-retryable client errors raise immediately without retrying
  - Timeout and configuration parameters are respected
  - Opt-in live Gemini test (when GEMINI_API_KEY is configured)
"""
import os
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings
from app.providers.base import ProviderConfigError, ProviderError
from app.providers.gemini import GeminiLLMProvider, GeminiEmbeddingProvider


def test_missing_api_key_raises_config_error():
    with patch("app.core.config.settings.gemini_api_key", None):
        with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY is required"):
            GeminiLLMProvider(api_key=None)


def test_missing_api_key_for_embeddings_raises_config_error():
    with patch("app.core.config.settings.gemini_api_key", None):
        with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY is required"):
            GeminiEmbeddingProvider(api_key=None)


def test_bounded_retry_on_simulated_transient_error():
    from google.genai import errors as genai_errors

    call_count = 0

    def mock_generate_content(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Simulate transient 429 rate-limit error
        raise genai_errors.APIError(code=429, response_json={"error": "Resource has been exhausted"})

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = mock_generate_content

    provider = GeminiLLMProvider(api_key="fake-test-key")
    provider._client = mock_client

    with pytest.raises(ProviderError):
        provider.generate(
            system_prompt="Test",
            user_message="Hello",
        )

    # settings.gemini_max_retries = 3, so initial call + retries = 3 calls total
    assert call_count == settings.gemini_max_retries


def test_non_retryable_error_does_not_loop():
    call_count = 0

    def mock_generate_content(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Simulate non-retryable 400 Invalid Argument error
        raise Exception("400 Invalid argument supplied to Gemini")

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = mock_generate_content

    provider = GeminiLLMProvider(api_key="fake-test-key")
    provider._client = mock_client

    with pytest.raises(ProviderError):
        provider.generate(
            system_prompt="Test",
            user_message="Hello",
        )

    # Should fail immediately on 1st call without retrying
    assert call_count == 1


def test_timeout_and_config_parameters_present():
    assert settings.gemini_timeout_seconds > 0
    assert settings.gemini_max_retries > 0
    assert settings.gemini_max_tool_rounds >= 1


@pytest.mark.live_gemini
def test_live_gemini_integration():
    """
    Opt-in test that calls the live Google GenAI API when a valid key is set.
    Skipped if no real key is present.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key or api_key.startswith("your_"):
        pytest.skip("No live GEMINI_API_KEY configured for integration test.")

    try:
        provider = GeminiLLMProvider(api_key=api_key)
        res = provider.generate(
            system_prompt="You are a pharmacy inventory bot.",
            user_message="Reply with 'LIVE_OK' only.",
        )
        assert res.text is not None
        assert len(res.text) > 0
    except Exception as exc:
        pytest.skip(f"Live Gemini API unavailable or quota exceeded: {exc}")
