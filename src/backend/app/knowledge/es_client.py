"""Optional Elasticsearch backend for knowledge keyword / hybrid retrieval."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.core.config import settings
from app.knowledge.es_runtime import get_elasticsearch_runtime
from app.knowledge.tokenize import TokenizeConfig, tokenize_for_search

_INDEX_NAME = "mchat_document_chunks"


class ElasticsearchKnowledgeClient:
    """Thin ES wrapper; disabled when ELASTICSEARCH_ENABLED=false or package missing."""

    def __init__(self) -> None:
        self._client: Any = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def is_configured(self) -> bool:
        cfg = get_elasticsearch_runtime()
        return bool(cfg.enabled and cfg.url)

    async def connect(self) -> bool:
        cfg = get_elasticsearch_runtime()
        if not cfg.enabled or not cfg.url:
            self._connected = False
            return False
        try:
            from elasticsearch import Elasticsearch
        except ImportError:
            logger.warning(
                "elasticsearch package not installed; keyword ES backend unavailable"
            )
            self._connected = False
            return False

        try:
            client = Elasticsearch(
                cfg.url,
                request_timeout=30,
            )

            def _ping() -> bool:
                return bool(client.ping())

            ok = await asyncio.to_thread(_ping)
            if not ok:
                logger.warning("Elasticsearch ping failed")
                self._connected = False
                return False
            self._client = client
            self._connected = True
            await self.ensure_index()
            logger.info("Connected to Elasticsearch for knowledge retrieval")
            return True
        except Exception as exc:
            logger.warning(f"Elasticsearch connect failed: {exc}")
            self._connected = False
            return False

    async def close(self) -> None:
        self._client = None
        self._connected = False

    async def reconnect(self) -> bool:
        """Disconnect and reconnect using current runtime settings."""
        await self.close()
        return await self.connect()

    async def ensure_index(self) -> None:
        if not self._client:
            return

        def _ensure() -> None:
            if self._client.indices.exists(index=_INDEX_NAME):
                return
            self._client.indices.create(
                index=_INDEX_NAME,
                settings={
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                },
                mappings={
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "document_id": {"type": "keyword"},
                        "knowledge_base_id": {"type": "keyword"},
                        "chunk_index": {"type": "integer"},
                        "title": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}},
                        },
                        "content": {"type": "text"},
                    }
                },
            )

        await asyncio.to_thread(_ensure)

    async def sync_document(
        self,
        *,
        knowledge_base_id: str,
        document_id: str,
        title: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        if not self._connected or not self._client:
            return
        if not chunks:
            await self.delete_document(document_id=document_id)
            return

        def _sync() -> None:
            self._client.delete_by_query(
                index=_INDEX_NAME,
                query={"term": {"document_id": document_id}},
                refresh=True,
                conflicts="proceed",
            )
            bulk_lines: list[dict[str, Any]] = []
            for row in chunks:
                bulk_lines.append(
                    {
                        "chunk_id": row["chunk_id"],
                        "document_id": document_id,
                        "knowledge_base_id": knowledge_base_id,
                        "chunk_index": int(row["chunk_index"]),
                        "title": title,
                        "content": row["content"],
                    }
                )
            from elasticsearch.helpers import bulk

            actions = [
                {
                    "_op_type": "index",
                    "_index": _INDEX_NAME,
                    "_id": row["chunk_id"],
                    **row,
                }
                for row in bulk_lines
            ]
            bulk(self._client, actions, refresh=True)

        await asyncio.to_thread(_sync)

    async def delete_document(self, *, document_id: str) -> None:
        if not self._connected or not self._client:
            return

        def _delete() -> None:
            self._client.delete_by_query(
                index=_INDEX_NAME,
                query={"term": {"document_id": document_id}},
                refresh=True,
                conflicts="proceed",
            )

        await asyncio.to_thread(_delete)

    async def search(
        self,
        *,
        query: str,
        knowledge_base_id: str,
        top_k: int,
        tokenize_config: TokenizeConfig | None = None,
    ) -> list[tuple[float, str]]:
        if not self._connected or not self._client:
            return []

        terms = sorted(
            tokenize_for_search(query, tokenize_config),
            key=len,
            reverse=True,
        )
        if not terms:
            return []

        should: list[dict[str, Any]] = []
        for term in terms:
            should.append({"match_phrase": {"content": term}})
            should.append({"match": {"content": term}})
            if len(term) <= 32:
                should.append({"term": {"title.keyword": term}})

        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "filter": [{"term": {"knowledge_base_id": knowledge_base_id}}],
                    "should": should,
                    "minimum_should_match": 1,
                }
            },
        }

        def _search() -> list[tuple[float, str]]:
            resp = self._client.search(index=_INDEX_NAME, body=body)
            hits = resp.get("hits", {}).get("hits", [])
            scored: list[tuple[float, str]] = []
            for hit in hits:
                source = hit.get("_source") or {}
                chunk_id = str(source.get("chunk_id") or hit.get("_id") or "")
                if not chunk_id:
                    continue
                scored.append((float(hit.get("_score") or 0.0), chunk_id))
            return scored

        return await asyncio.to_thread(_search)


es_knowledge_client = ElasticsearchKnowledgeClient()
