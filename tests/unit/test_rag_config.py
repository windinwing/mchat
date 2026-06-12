"""RAG configuration resolution (isolated from env-specific .env values)."""

from app.core.config import settings
from app.knowledge.rag_config import EmbeddingConfig


def test_ollama_config_defaults(monkeypatch):
    monkeypatch.setattr(settings, "embedding_api_base", "")
    config = EmbeddingConfig(provider="ollama", model="nomic-embed-text")
    assert config.resolved_provider() == "ollama"
    assert config.resolved_model() == "nomic-embed-text"
    assert config.resolved_api_base() == "http://localhost:11434"


def test_openai_config():
    config = EmbeddingConfig(
        provider="openai",
        model="text-embedding-ada-002",
        api_base="https://api.openai.com/v1",
        dimension=1536,
    )
    assert config.resolved_provider() == "openai"
    assert config.resolved_dimension() == 1536


def test_config_fallback_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    config = EmbeddingConfig()
    assert config.resolved_provider() == "openai"
    assert config.resolved_model() == "text-embedding-3-small"
