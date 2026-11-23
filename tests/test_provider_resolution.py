"""Test provider resolution functionality."""

import pytest
import sys
import os

# Add parent directory to path to import chess_llm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chess_llm import (
    PROVIDER_PRESETS,
    _resolve_provider,
)


class TestProviderPresets:
    """Test the PROVIDER_PRESETS dictionary."""

    def test_all_presets_exist(self):
        """Test that all expected provider presets exist."""
        expected_prefixes = [
            "opencode-go",
            "opencode-zen",
            "openrouter",
            "openai",
            "ollama",
            "docker",
            "bigpickle",
            "llama-cpp",
        ]
        
        for prefix in expected_prefixes:
            assert prefix in PROVIDER_PRESETS, f"Missing preset: {prefix}"

    def test_opencode_go_preset(self):
        """Test opencode-go preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["opencode-go"]
        assert base_url == "https://opencode.ai/zen/go/v1"
        assert key_env == "OPENCODE_GO_API_KEY"

    def test_opencode_zen_preset(self):
        """Test opencode-zen preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["opencode-zen"]
        assert base_url == "https://opencode.ai/zen/v1"
        assert key_env == "OPENCODE_ZEN_API_KEY"

    def test_openrouter_preset(self):
        """Test openrouter preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["openrouter"]
        assert base_url == "https://openrouter.ai/api/v1"
        assert key_env == "OPENROUTER_API_KEY"

    def test_openai_preset(self):
        """Test openai preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["openai"]
        assert base_url == "https://api.openai.com/v1"
        assert key_env == "OPENAI_API_KEY"

    def test_ollama_preset(self):
        """Test ollama preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["ollama"]
        assert base_url == "http://localhost:11434/v1"
        assert key_env is None  # No API key needed

    def test_docker_preset(self):
        """Test docker preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["docker"]
        assert base_url == "http://localhost:12434/engines/v1"
        assert key_env is None  # No API key needed

    def test_bigpickle_preset(self):
        """Test bigpickle preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["bigpickle"]
        assert base_url == "http://localhost:8000/v1"
        assert key_env is None  # No API key needed

    def test_llama_cpp_preset(self):
        """Test llama-cpp preset configuration."""
        base_url, key_env = PROVIDER_PRESETS["llama-cpp"]
        assert base_url == "http://localhost:8080/v1"
        assert key_env is None  # No API key needed


class TestResolveProvider:
    """Test the _resolve_provider() function."""

    def test_opencode_go_model(self, monkeypatch):
        """Test resolving opencode-go model."""
        # Clear any existing environment variables
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        
        model_str = "opencode-go/deepseek-v4-pro"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/deepseek-v4-pro"
        assert api_base == "https://opencode.ai/zen/go/v1"
        # API key should be None since env var is not set
        assert api_key is None

    def test_opencode_zen_model(self, monkeypatch):
        """Test resolving opencode-zen model."""
        monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
        
        model_str = "opencode-zen/deepseek-v4-pro"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/deepseek-v4-pro"
        assert api_base == "https://opencode.ai/zen/v1"
        assert api_key is None

    def test_openrouter_model(self, monkeypatch):
        """Test resolving openrouter model."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        
        model_str = "openrouter/anthropic/claude-sonnet-4"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        # openrouter prefix is preserved
        assert litellm_model == "openrouter/anthropic/claude-sonnet-4"
        assert api_base == "https://openrouter.ai/api/v1"
        assert api_key is None

    def test_openai_model(self, monkeypatch):
        """Test resolving openai model."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        model_str = "openai/gpt-4o"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/gpt-4o"
        assert api_base == "https://api.openai.com/v1"
        assert api_key is None

    def test_ollama_model(self, monkeypatch):
        """Test resolving ollama model."""
        model_str = "ollama/llama3"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/llama3"
        assert api_base == "http://localhost:11434/v1"
        # Ollama uses dummy API key
        assert api_key == "ollama"

    def test_docker_model(self, monkeypatch):
        """Test resolving docker model."""
        model_str = "docker/ai/ministral3:3B-Q4_K_M"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/ai/ministral3:3B-Q4_K_M"
        assert api_base == "http://localhost:12434/engines/v1"
        # Docker uses dummy API key
        assert api_key == "not-needed"

    def test_bigpickle_model(self, monkeypatch):
        """Test resolving bigpickle model."""
        model_str = "bigpickle/big-pickle"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/big-pickle"
        assert api_base == "http://localhost:8000/v1"
        # Big Pickle uses dummy API key
        assert api_key == "not-needed"

    def test_llama_cpp_model(self, monkeypatch):
        """Test resolving llama-cpp model."""
        model_str = "llama-cpp/model"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/model"
        assert api_base == "http://localhost:8080/v1"
        # llama-cpp uses dummy API key
        assert api_key == "not-needed"

    def test_unknown_prefix_passthrough(self):
        """Test that unknown prefixes pass through unchanged."""
        model_str = "anthropic/claude-sonnet-4"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        # Should pass through unchanged
        assert litellm_model == "anthropic/claude-sonnet-4"
        assert api_base is None
        assert api_key is None

    def test_groq_model(self):
        """Test resolving groq model (unknown prefix)."""
        model_str = "groq/llama-3.3-70b"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        # Should pass through unchanged
        assert litellm_model == "groq/llama-3.3-70b"
        assert api_base is None
        assert api_key is None

    def test_plain_model_name(self):
        """Test resolving plain model name without prefix."""
        model_str = "gpt-4"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        # Should pass through unchanged
        assert litellm_model == "gpt-4"
        assert api_base is None
        assert api_key is None

    def test_opencode_go_with_env_var(self, monkeypatch):
        """Test opencode-go model with environment variable set."""
        monkeypatch.setenv("OPENCODE_GO_API_KEY", "test-key-123")
        
        model_str = "opencode-go/deepseek-v4-pro"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/deepseek-v4-pro"
        assert api_base == "https://opencode.ai/zen/go/v1"
        assert api_key == "test-key-123"

    def test_openai_with_env_var(self, monkeypatch):
        """Test openai model with environment variable set."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        
        model_str = "openai/gpt-4o"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/gpt-4o"
        assert api_base == "https://api.openai.com/v1"
        assert api_key == "test-openai-key"

    def test_ollama_env_var_ignored(self, monkeypatch):
        """Test that ollama ignores environment variable and uses dummy key."""
        monkeypatch.setenv("SOME_OLLAMA_KEY", "should-be-ignored")
        
        model_str = "ollama/llama3"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/llama3"
        assert api_base == "http://localhost:11434/v1"
        # Should use dummy key, not env var
        assert api_key == "ollama"

    def test_openrouter_prefix_preserved(self, monkeypatch):
        """Test that openrouter prefix is preserved in litellm_model."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        
        model_str = "openrouter/model-name"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        # openrouter prefix should be preserved
        assert litellm_model == "openrouter/model-name"
        assert api_base == "https://openrouter.ai/api/v1"

    def test_model_with_underscores(self, monkeypatch):
        """Test model names with underscores."""
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        
        model_str = "opencode-go/my_model_v2"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/my_model_v2"
        assert api_base == "https://opencode.ai/zen/go/v1"

    def test_model_with_dashes(self, monkeypatch):
        """Test model names with dashes."""
        monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
        
        model_str = "opencode-zen/my-model-v2"
        litellm_model, api_base, api_key = _resolve_provider(model_str)
        
        assert litellm_model == "openai/my-model-v2"
        assert api_base == "https://opencode.ai/zen/v1"
