# MChat Product Roadmap

This document describes **current capabilities** and **planned work** for the knowledge base, Widget, channels, public API docs, operations analytics, and permissions. Implementation status is authoritative in code and CHANGELOG.

---

## 1. Knowledge base & RAG

### Current (all P0 core complete)

| Area | Notes |
|------|-------|
| Import | txt / md / html / docx / pdf (pdfplumber) |
| Chunking | `fixed` / `paragraph` / `markdown` / `semantic` strategies, per-KB configurable size / overlap / min_chunk_size / semantic_threshold |
| Embeddings | Per-KB or global: OpenAI-compatible API / local HuggingFace zip upload (`sentence-transformers`) / Ollama local models |
| Retrieval | `vector` / `keyword` / `hybrid` modes; BM25 pure-Python keyword index + Milvus vector; RRF fusion |
| Rerank | `lexical` (built-in lightweight) / `cohere` / `bge` / `cross-encoder` providers, configurable top_n |
| Query rewriting | LLM-based multi-perspective query variants to improve recall (configurable on/off + count) |
| Parent-child retrieval | Semantic chunking auto-generates parent context; child hits enriched with parent content for completeness |
| Chunk storage | `document_chunks` table (with `parent_content` field) + Milvus vectors |
| Agent binding | Only explicitly selected knowledge bases are searched |
| Reindex | Full re-embed on model change via `POST .../reindex`; `reindex_status` tracks progress |
| Embedding fingerprint | `indexed_embedding_key` records last index config (provider|model|dim|base) to detect changes |

Code: `chunking.py`, `embedder.py`, `local_embedder.py`, `model_storage.py`, `rag.py`, `rag_config.py`, `chunk_store.py`, `importer.py`, `bm25.py`, `rerank.py`, `query_rewriter.py`, `query_rewrite_chat.py`, `embedding_fingerprint.py`.

### Per-KB full configuration

```yaml
# Chunking
chunk:
  strategy: fixed | paragraph | markdown | semantic
  size: 500
  overlap: 50
  min_chunk_size: 80
  semantic_threshold: 0.7
  parent_enabled: true

# Embedding
embedding:
  provider: openai | local | ollama
  model: text-embedding-3-small
  api_base: https://api.openai.com/v1
  dimension: 1536

# Retrieval
retrieval:
  mode: vector | keyword | hybrid
  top_k: 5
  candidate_k: 20
  rerank:
    enabled: true
    provider: lexical | cohere | bge | cross-encoder
    model: null  # cohere or cross-encoder model name
    top_n: 5
  bm25:
    enabled: true
    k1: 1.5
    b: 0.75
  query_rewrite:
    enabled: false
    count: 3
```

Admin UI exposes all above settings per knowledge base, with presets (FAQ / manual / crawled pages).

### Planned: retrieval observability & evaluation

| Area | Notes |
|------|-------|
| Retrieval logs | Per-search raw/fusion/rerank scores, hit chunk IDs |
| Zero-result queries | Track queries that return nothing, aid tuning |
| Eval dataset | Annotated Q&A pairs for Recall@k / MRR |
| A/B comparison | Compare strategies/models on the same query |

---

## 2. Web Widget

### Current

Lightweight `widget-loader.js` + iframe embed, branding (primary color, welcome text, bot name), SSE streaming, visitor token, domain allowlist, drag-to-resize, fullscreen mode.

### Planned: Intercom / Chatwoot–class experience

Pre-chat forms, business hours, offline mode, read receipts, typing indicators, file upload, CSAT, proactive messages, `postMessage` API, lazy load and size budget (&lt; 50KB core loader).

---

## 3. Channels

### Current

| Channel | Status |
|---------|--------|
| Web Widget | ✅ |
| WeChat Official Account | ✅ `wechat_adapter.py` |
| REST / WebSocket | ✅ |
| DingTalk / WhatsApp / Telegram / Slack / LINE | 🟡 UI reserved, adapters TBD |
| Custom webhook | 🟡 fields reserved |

Channel types defined in `src/frontend/src/i18n/channelTypes.ts`.

### Planned

Unified `ChannelAdapter`: normalize inbound → engine → format outbound per channel limits. Per-channel agent binding, idempotency, retry queues, auto-reply rules.

---

## 4. Public API documentation

### Current

Swagger at `http://localhost:3001/docs`; repo [api.zh.md](api.zh.md) for developers.

### Planned

Developer docs on the marketing site (e.g. [mchat.9235.net](https://mchat.9235.net)): auth patterns (JWT, API Key, Visitor Token), core REST/WS, examples (curl/Python/Node), rate limits, error codes, API changelog. Deliver via static site (VitePress/Docusaurus) + OpenAPI/Redoc to avoid drift.

---

## 5. Operations & reporting

### Current

Basic dashboard stats (`/api/dashboard/stats`), conversation list, message history, agent config.

### Planned

FRT/ART, resolution rate, human handoff rate, per-agent metrics, KB hit/zero-result rates, channel breakdown, CSV export, optional alerts.

---

## 6. RBAC (Role → Permission)

### Current

Roles: `admin` / `agent`; coarse middleware checks (`require_admin`, `require_agent_or_admin`).

### Planned

`Permission(resource, action)` e.g. `knowledge:write`, `conversation:export`; role templates in admin UI; API dependency checks; tenant-scoped admins.

---

## 7. Beyond customer support

Embedded multi-tenant chat + RAG + Skills also fits internal KB assistants, docs copilots, sales playbooks, ticket drafts, vertical agents via Skills, IoT help, and community bots (Telegram/Slack).

---

## Suggested priorities

| Priority | Item | Status |
|----------|------|--------|
| ~~P0~~ | ~~Configurable chunking, multi-embedding~~ | ✅ Done |
| ~~P0~~ | ~~Hybrid retrieval + rerank~~ | ✅ Done (incl. query rewriting, parent-child) |
| P1 | Retrieval observability (logs, eval, comparison) | Tuning & debugging |
| P1 | Channel adapters (DingTalk, Telegram, WhatsApp) | UI reserved, user demand |
| P1 | Public API docs | Lower integration barrier |
| P1 | Widget UX (pre-chat forms, CSAT, unread badge) | Product polish |
| P1 | Workflow run replay & observability | Beta → production hardening |
| P2 | Analytics depth | Enterprise procurement |
| P2 | Fine-grained RBAC | Team scale requirement |
| P3 | Use-case templates & tour content | Acquisition & differentiation |

Discuss on [GitHub Issues](https://github.com/windinwing/mchat/issues).

---

## 8. Workflow orchestration (Beta)

### Current

| Capability | Notes |
|------------|-------|
| Linear flows | Ordered Skill steps, payload templates, step logs |
| Graph DAG | React Flow editor + executor (condition / parallel / approval / merge) |
| Triggers | Manual run, skill schedules, channel message rules |
| Operations | Rule preview, import/export, hit stats, approval queue |
| Templates | Patent multi-dimension report (zh/en), skill_name auto-bind |
| Alerts | Failure/rejection webhook (`WORKFLOW_ALERT_WEBHOOK_URL`) |

See [workflow-orchestrator.en.md](workflow-orchestrator.en.md) for DSL and template details ([中文](workflow-orchestrator.zh.md)).

### Planned

| Area | Notes |
|------|-------|
| Run replay | Highlight node status on the canvas during/after runs |
| Node library | Search, categories, ComfyUI-style canvas tools (pointer/pan) |
| Versioning | Publish/rollback, change audit |
| Observability | Run metrics, slow-node analysis |
