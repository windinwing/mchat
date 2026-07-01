"""Embedding service - API, Ollama, and locally uploaded models."""

from __future__ import annotations

import asyncio
import hashlib

import httpx
from loguru import logger
from openai import AsyncOpenAI

from app.core.config import settings
from app.knowledge.rag_config import EmbeddingConfig


_EMBED_TIMEOUT_SEC = 8.0
_OLLAMA_EMBED_TIMEOUT_SEC = 15.0
_OLLAMA_FALLBACK_MODEL = "nomic-embed-text"
_OLLAMA_FALLBACK_DIM = 768


class EmbeddingService:
    """Generates embeddings using configured provider."""

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self._config = config or EmbeddingConfig()
        self.provider = self._config.resolved_provider()
        self.model = self._config.resolved_model()
        self.api_base = self._config.resolved_api_base()
        self.dimension = self._config.resolved_dimension()
        self._client: AsyncOpenAI | None = None

    def is_configured(self) -> bool:
        """True when an API key is available for remote embedding providers."""
        if self.provider in ("local", "ollama"):
            return True  # local / Ollama do not need cloud API keys
        key = (
            settings.embedding_api_key
            or settings.openai_api_key
            or ""
        ).strip()
        return bool(key) and key not in ("not-needed", "sk-xxx")

    def _cache_key(self, text: str) -> str:
        raw = f"{self.provider}:{self.model}:{self.api_base}:{text}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def _get_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client

        provider = self.provider
        if provider in ("openai", "openai-compatible", "compatible"):
            api_key = (
                settings.embedding_api_key
                or settings.openai_api_key
                or ""
            ).strip()
            kwargs: dict = {"api_key": api_key or "not-needed"}
            base = self.api_base or settings.embedding_api_base or None
            if base:
                kwargs["base_url"] = base.rstrip("/")
            self._client = AsyncOpenAI(**kwargs)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

        return self._client

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed(text)

    #: Cap concurrent embedding requests per document so a large upload does
    #: not fan out hundreds of simultaneous calls to the embedding backend.
    _CONCURRENCY = 8

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.provider == "local":
            from app.knowledge.local_embedder import embed_texts

            return await embed_texts(self.model, texts)

        # Ollama / OpenAI-compatible backends embed one text per request. Issue
        # them concurrently (bounded) instead of serially so a document with
        # many chunks does not take N round-trips back to back.
        semaphore = asyncio.Semaphore(self._CONCURRENCY)

        async def _one(text: str) -> list[float]:
            async with semaphore:
                if self.provider == "ollama":
                    return await self._embed_ollama(text)
                return await self._embed(text)

        return await asyncio.gather(*[_one(t) for t in texts])

    async def _embed(self, text: str) -> list[float]:
        if self.provider == "local":
            from app.knowledge.local_embedder import embed_text

            return await embed_text(self.model, text)
        if self.provider == "ollama":
            return await self._embed_ollama(text)

        if not self.is_configured():
            fallback = await self._try_ollama_fallback(text)
            if fallback is not None:
                return fallback
            return [0.0] * self.dimension

        cache_key = self._cache_key(text)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            client = await self._get_client()
            response = await asyncio.wait_for(
                client.embeddings.create(
                    input=text.replace("\n", " "),
                    model=self.model,
                ),
                timeout=_EMBED_TIMEOUT_SEC,
            )
            embedding = list(response.data[0].embedding)
            self._set_cache(cache_key, embedding)
            return embedding
        except asyncio.TimeoutError:
            logger.warning(
                f"Embedding timed out after {_EMBED_TIMEOUT_SEC}s "
                f"({self.provider}/{self.model})"
            )
            return [0.0] * self.dimension
        except Exception as e:
            logger.error(f"Embedding failed ({self.provider}/{self.model}): {e}")
            return [0.0] * self.dimension

    async def _try_ollama_fallback(self, text: str) -> list[float] | None:
        """When OpenAI-compatible embedding is not configured, try local Ollama."""
        if self.provider in ("local", "ollama"):
            return None
        model = _OLLAMA_FALLBACK_MODEL
        base = (settings.embedding_api_base or "http://localhost:11434").rstrip("/")
        url = f"{base}/api/embeddings"
        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_EMBED_TIMEOUT_SEC) as client:
                response = await client.post(
                    url,
                    json={"model": model, "prompt": text.replace("\n", " ")},
                )
                response.raise_for_status()
                data = response.json()
                embedding = list(data.get("embedding") or [])
                if embedding:
                    logger.debug(f"Embedding via Ollama fallback ({model})")
                    return embedding
        except Exception as e:
            logger.debug(f"Ollama embedding fallback unavailable: {e}")
        return None

    async def _embed_ollama(self, text: str) -> list[float]:
        base = (self.api_base or settings.embedding_api_base or "http://localhost:11434").rstrip("/")
        url = f"{base}/api/embeddings"
        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_EMBED_TIMEOUT_SEC) as client:
                response = await client.post(
                    url,
                    json={"model": self.model, "prompt": text.replace("\n", " ")},
                )
                response.raise_for_status()
                data = response.json()
                embedding = list(data.get("embedding") or [])
                if embedding:
                    return embedding
        except Exception as e:
            logger.warning(f"Ollama embedding failed ({self.model}): {e}")
            raise RuntimeError(
                f"Ollama embedding failed ({self.model} @ {base}): {e}"
            ) from e

    _cache: dict[str, list[float]] = {}

    def _get_cached(self, key: str) -> list[float] | None:
        return self._cache.get(key)

    def _set_cache(self, key: str, value: list[float]) -> None:
        if len(self._cache) > 1000:
            self._cache.clear()
        self._cache[key] = value


def embedder_for_config(config: EmbeddingConfig | None = None) -> EmbeddingService:
    return EmbeddingService(config)


embedder = EmbeddingService()
