"""Runtime Elasticsearch settings (env defaults + DB overrides)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class ElasticsearchRuntimeConfig:
    enabled: bool
    url: str


_runtime = ElasticsearchRuntimeConfig(
    enabled=settings.elasticsearch_enabled,
    url=(settings.elasticsearch_url or "").strip(),
)


def get_elasticsearch_runtime() -> ElasticsearchRuntimeConfig:
    return _runtime


def apply_elasticsearch_runtime(*, enabled: bool, url: str) -> None:
    global _runtime
    _runtime = ElasticsearchRuntimeConfig(
        enabled=enabled,
        url=(url or settings.elasticsearch_url or "").strip(),
    )
