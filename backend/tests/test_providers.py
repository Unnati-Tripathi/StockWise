"""
Tests for the provider layer (Phase 1).

All tests in this file run without any live API calls.  They verify:
  - Mock providers return deterministic output.
  - Factory selects the correct provider based on config.
  - Gemini provider raises ProviderConfigError when the key is absent.
  - Forced-response injection works correctly.
  - reset_providers() clears the cached singletons.

No Gemini API key or network access is required.
"""
import pytest

from app.providers.base import (
    FunctionCall,
    LLMResponse,
    ProviderConfigError,
)
from app.providers.mock import MockEmbeddingProvider, MockLLMProvider
from app.providers.factory import get_llm_provider, get_embedding_provider, reset_providers


# ── MockLLMProvider tests ─────────────────────────────────────────────────────

class TestMockLLMProvider:
    def setup_method(self):
        self.provider = MockLLMProvider()

    def test_returns_text_response_when_no_tools(self):
        resp = self.provider.generate(
            system_prompt="You are a helpful assistant.",
            user_message="Hello",
        )
        assert resp.text is not None
        assert "[MOCK RESPONSE]" in resp.text
        assert resp.function_calls == []
        assert resp.model_used == "mock"

    def test_returns_function_call_when_tools_declared(self):
        tools = [{"name": "get_inventory_status", "description": "Get stock levels"}]
        resp = self.provider.generate(
            system_prompt="You are an assistant.",
            user_message="What is the stock level?",
            tools=tools,
        )
        assert resp.function_calls != []
        assert resp.function_calls[0].name == "get_inventory_status"
        assert resp.text is None

    def test_returns_text_after_tool_results_provided(self):
        tool_results = [{"name": "get_inventory_status", "result": {"stock": 100}}]
        resp = self.provider.generate(
            system_prompt="You are an assistant.",
            user_message="What is the stock level?",
            tool_results=tool_results,
        )
        assert resp.text is not None
        assert resp.function_calls == []

    def test_forced_responses_consumed_in_order(self):
        forced = [
            LLMResponse(function_calls=[FunctionCall(name="tool_a", args={"x": 1})]),
            LLMResponse(text="Final answer from tool_a result"),
        ]
        provider = MockLLMProvider(forced_responses=forced)

        resp1 = provider.generate(system_prompt="s", user_message="q")
        assert resp1.function_calls[0].name == "tool_a"
        assert resp1.function_calls[0].args == {"x": 1}

        resp2 = provider.generate(system_prompt="s", user_message="q")
        assert resp2.text == "Final answer from tool_a result"

    def test_falls_back_to_default_after_forced_responses_exhausted(self):
        forced = [LLMResponse(text="only one")]
        provider = MockLLMProvider(forced_responses=forced)
        provider.generate(system_prompt="s", user_message="q")  # consumes forced

        # Second call falls back to default (no tools → text)
        resp = provider.generate(system_prompt="s", user_message="fallback")
        assert resp.text is not None

    def test_provider_name(self):
        assert self.provider.provider_name() == "mock"

    def test_unrecognised_query_returns_text(self):
        resp = self.provider.generate(
            system_prompt="s",
            user_message="What is the meaning of life?",
        )
        assert resp.text is not None


# ── MockEmbeddingProvider tests ───────────────────────────────────────────────

class TestMockEmbeddingProvider:
    def setup_method(self):
        self.provider = MockEmbeddingProvider(dims=768)

    def test_embed_texts_returns_correct_count(self):
        results = self.provider.embed_texts(["chunk one", "chunk two", "chunk three"])
        assert len(results) == 3

    def test_embed_texts_vector_dimensions(self):
        results = self.provider.embed_texts(["hello"])
        assert len(results[0].vector) == 768
        assert results[0].dimensions == 768

    def test_embed_texts_zero_vectors(self):
        results = self.provider.embed_texts(["hello"])
        assert all(v == 0.0 for v in results[0].vector)

    def test_embed_query_returns_single_result(self):
        result = self.provider.embed_query("search term")
        assert len(result.vector) == 768
        assert result.dimensions == 768
        assert result.model_used == "mock-embedding"

    def test_embed_empty_list_returns_empty(self):
        results = self.provider.embed_texts([])
        assert results == []

    def test_dimensions_method(self):
        assert self.provider.dimensions() == 768

    def test_model_name(self):
        assert self.provider.model_name() == "mock-embedding"

    def test_custom_dimensions(self):
        p = MockEmbeddingProvider(dims=256)
        result = p.embed_query("q")
        assert len(result.vector) == 256
        assert p.dimensions() == 256


# ── Factory tests ─────────────────────────────────────────────────────────────

class TestProviderFactory:
    def setup_method(self):
        # Always start from a clean slate
        reset_providers()

    def teardown_method(self):
        reset_providers()

    def test_mock_provider_returned_by_default(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "mock")
        provider = get_llm_provider()
        assert provider.provider_name() == "mock"

    def test_same_instance_returned_on_repeated_calls(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "mock")
        p1 = get_llm_provider()
        p2 = get_llm_provider()
        assert p1 is p2

    def test_reset_clears_singleton(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "mock")
        p1 = get_llm_provider()
        reset_providers()
        p2 = get_llm_provider()
        assert p1 is not p2

    def test_gemini_provider_raises_config_error_when_key_missing(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "gemini")
        monkeypatch.setattr("app.core.config.settings.gemini_api_key", None)
        with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY"):
            get_llm_provider()

    def test_unknown_provider_raises_value_error(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "openai")
        with pytest.raises(ValueError, match="Unknown ai_provider"):
            get_llm_provider()

    def test_mock_embedding_provider_returned(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "mock")
        monkeypatch.setattr("app.core.config.settings.gemini_embedding_dimensions", 768)
        provider = get_embedding_provider()
        assert provider.dimensions() == 768

    def test_gemini_embedding_raises_config_error_when_key_missing(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.ai_provider", "gemini")
        monkeypatch.setattr("app.core.config.settings.gemini_api_key", None)
        with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY"):
            get_embedding_provider()
