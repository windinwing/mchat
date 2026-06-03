# MChat API Documentation

Base URL: `http://localhost:3001/api`

## Authentication

All admin endpoints require Bearer Token (`Authorization: Bearer <token>`). Widget public endpoints do not need authentication.

### POST /auth/login

Login to obtain JWT token.

**Request Body:**
```json
{
  "username": "admin",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "admin",
    "role": "admin",
    "display_name": "Admin",
    "avatar_url": null,
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

### POST /auth/register

Register a new user (Agent role).

**Request Body:**
```json
{
  "username": "agent_001",
  "password": "password123",
  "display_name": "Agent Wang",
  "avatar_url": null
}
```

### GET /auth/me

Get current user info. Requires Bearer Token.

### GET /auth/bootstrap

Get default admin credentials hint (password shown in dev mode when enabled).

**Response:**
```json
{
  "username": "admin",
  "password": "admin123",
  "show_credentials": true
}
```

### POST /auth/change-password

Change password for the current user.

**Request Body:**
```json
{
  "current_password": "old_pass",
  "new_password": "new_pass_123"
}
```

### User Management (Admin only)

| Method | Path | Description |
|------|------|------|
| GET | `/auth/users` | List all users |
| POST | `/auth/users` | Create a new user |
| PATCH | `/auth/users/{user_id}` | Update user (role, display name, password) |
| DELETE | `/auth/users/{user_id}` | Delete a user |

**CreateUserRequest:**
```json
{
  "username": "agent_002",
  "password": "pass123456",
  "role": "agent",
  "display_name": "Agent Li"
}
```

---

## Chat

### POST /chat/send

Send a message (non-streaming). See Widget section for SSE streaming.

**Request Header:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "conversation_id": "uuid",
  "content": "Hello",
  "role": "user",
  "extra_data": {}
}
```

### POST /chat/upload

Upload an attachment and send as message (multipart form).

### GET /chat/conversations

List conversations (paginated).

**Params:** `?skip=0&limit=20&status=active&search=keyword`

### GET /chat/conversations/stats

Get conversation stats (total, active, closed).

### POST /chat/conversations

Create a new conversation (Admin).

**Request Body:**
```json
{
  "title": "New conversation",
  "ai_config_id": "uuid",
  "visitor_id": null
}
```

### GET /chat/conversations/{id}

Get conversation details including messages.

### POST /chat/conversations/{id}/close

Close a conversation.

### POST /chat/conversations/init

Initialize a visitor conversation (no auth required).

**Request Body:**
```json
{
  "visitor_id": "optional visitor ID",
  "title": "Optional title",
  "ai_config_id": "uuid (customer config ID)",
  "contact_info": "Optional contact info"
}
```

---

## Agent Management

### AI Configuration

| Method | Path | Description |
|------|------|------|
| POST | `/agents/ai-configs` | Create AI config |
| GET | `/agents/ai-configs` | List AI configs |
| GET | `/agents/ai-configs/{id}` | Get AI config details |
| PUT | `/agents/ai-configs/{id}` | Update AI config |
| DELETE | `/agents/ai-configs/{id}` | Delete AI config |
| POST | `/agents/ai-configs/models` | Fetch model catalog from provider |
| POST | `/agents/ai-configs/test` | Test API connection |

**AIConfig object:**
```json
{
  "name": "GPT-4 Support",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "api_key": "sk-...",
  "api_base": "https://api.openai.com/v1",
  "system_prompt": "You are a professional customer service assistant...",
  "temperature": 0.7,
  "max_tokens": 2048,
  "is_default": true
}
```

### Customer Configuration

| Method | Path | Description |
|------|------|------|
| POST | `/agents/customer-configs` | Create customer config |
| GET | `/agents/customer-configs` | List customer configs |
| GET | `/agents/customer-configs/{id}` | Get customer config details |
| PUT | `/agents/customer-configs/{id}` | Update customer config |
| POST | `/agents/customer-configs/upload-asset` | Upload auto-reply asset |

**CustomerConfig object:**
```json
{
  "name": "Main Site Support",
  "short_code": "main",
  "ai_config_id": "uuid",
  "skill_ids": ["skill-uuid"],
  "knowledge_base_ids": ["kb-uuid"],
  "auto_reply_rules": [
    {
      "name": "Welcome",
      "enabled": true,
      "trigger_text": "Hello",
      "keywords": ["hello", "hi"],
      "channels": ["widget", "wechat"],
      "reply_text": "Hello! How can I help you?",
      "threshold": 0.78,
      "asset": null
    }
  ],
  "welcome_message": "Hello! How can I help you?",
  "offline_message": "We are currently offline. Please leave a message.",
  "theme": {
    "primaryColor": "#3b82f6",
    "botName": "Smart Support",
    "widgetTitle": "Online Support",
    "launcherIcon": "chat",
    "launcherText": ""
  },
  "domains": "example.com,www.example.com",
  "position": "right",
  "enabled": true,
  "widget_session_ttl_hours": 24
}
```

---

## Knowledge Base

### Knowledge Base CRUD

| Method | Path | Description |
|------|------|------|
| POST | `/knowledge/bases` | Create knowledge base |
| GET | `/knowledge/bases` | List knowledge bases |
| GET | `/knowledge/bases/{id}` | Get knowledge base details |
| PATCH | `/knowledge/bases/{id}` | Update knowledge base (including RAG settings) |
| DELETE | `/knowledge/bases/{id}` | Delete knowledge base |
| POST | `/knowledge/bases/{id}/reindex` | Re-chunk and re-embed all documents |

**KnowledgeBase RAG settings (PATCH body, partial update):**
```json
{
  "name": "Product Knowledge Base",
  "chunk_strategy": "fixed | paragraph | markdown | semantic",
  "chunk_size": 500,
  "chunk_overlap": 50,
  "chunk_min_size": 80,
  "chunk_semantic_threshold": 0.7,
  "chunk_parent_enabled": true,
  "embedding_provider": "openai | local | ollama",
  "embedding_model": "text-embedding-3-small",
  "embedding_api_base": "https://api.openai.com/v1",
  "embedding_dimension": 1536,
  "retrieval_mode": "vector | keyword | hybrid",
  "retrieval_top_k": 5,
  "retrieval_candidate_k": 20,
  "rerank_enabled": true,
  "rerank_top_n": 5,
  "rerank_provider": "lexical | cohere | bge | cross-encoder",
  "rerank_model": null,
  "retrieval_bm25_enabled": true,
  "retrieval_bm25_k1": 1.5,
  "retrieval_bm25_b": 0.75,
  "retrieval_query_rewrite_enabled": false,
  "retrieval_query_rewrite_count": 3
}
```

### Documents

| Method | Path | Description |
|------|------|------|
| GET | `/knowledge/bases/{kb_id}/documents` | List documents in a knowledge base |
| POST | `/knowledge/bases/{kb_id}/documents` | Create a document |
| DELETE | `/knowledge/documents/{doc_id}` | Delete a document |
| POST | `/knowledge/bases/{kb_id}/import-file` | Import file (multipart upload) |
| POST | `/knowledge/bases/{kb_id}/import-url` | Import from URL |
| POST | `/knowledge/search` | Search knowledge bases |

**DocumentCreate:**
```json
{
  "title": "Refund Policy",
  "content": "Refunds can be requested within 7 days of delivery...",
  "source": "Help Center",
  "source_url": "https://example.com/refund"
}
```

### Search Request & Response

**Request:**
```json
{
  "query": "How to refund",
  "knowledge_base_id": "uuid",
  "top_k": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "document_id": "uuid",
      "title": "Refund Policy",
      "content": "Refunds can be requested within 7 days of delivery...",
      "score": 0.8732,
      "knowledge_base_id": "uuid",
      "chunk_index": 2,
      "retrieval_mode": "hybrid"
    }
  ],
  "total": 5
}
```

### Reindex

**POST /knowledge/bases/{id}/reindex**

**Request Body (optional):**
```json
{
  "rechunk": true
}
```

**Response:**
```json
{
  "knowledge_base_id": "uuid",
  "total": 10,
  "succeeded": 9,
  "failed": 1,
  "rechunk": true,
  "milvus_enabled": true,
  "indexed_embedding_key": "openai:text-embedding-3-small:ab12",
  "documents": [
    {"document_id": "uuid", "title": "Refund Policy", "status": "ok", "chunk_count": 5},
    {"document_id": "uuid", "title": "Shipping Info", "status": "failed", "error": "..."}
  ]
}
```

### Embedding Models (local upload)

| Method | Path | Description |
|------|------|------|
| GET | `/knowledge/embedding-models` | List uploaded models |
| POST | `/knowledge/embedding-models/upload` | Upload model zip (multipart, optional `name` field) |
| DELETE | `/knowledge/embedding-models/{id}` | Delete a model |

---

## Skills

| Method | Path | Description |
|------|------|------|
| GET | `/skills` | List skills |
| PATCH | `/skills/{id}` | Enable/disable skill, update config |
| DELETE | `/skills/{id}` | Delete skill |
| POST | `/skills/reload` | Reload skills from filesystem |
| POST | `/skills/upload` | Upload skill package (zip) |
| POST | `/skills/install-url` | Install skill from URL or ClawHub name |
| GET | `/skills/catalog` | Browse ClawHub skill catalog (`?query=&limit=24`) |

**POST /skills/install-url Request Body:**
```json
{
  "url": "https://example.com/skill.zip or patent-search",
  "name": "Optional skill name"
}
```

---

## Workflows (Beta)

> Chain multiple Skills into flows with linear steps or a `graph_json` DAG. See [workflow-orchestrator.en.md](./workflow-orchestrator.en.md).

Permissions: `skills:read` / `skills:write`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/workflows/templates` | Built-in + my templates (`?locale=en\|zh`) |
| GET | `/workflows/showcase-config` | Patent workflow showcase config (skill names, install status) |
| POST | `/workflows/{workflow_id}/save-as-template` | Save workflow graph as my template |
| DELETE | `/workflows/templates/{template_id}` | Delete my template |
| POST | `/workflows/from-template/{template_id}` | Create workflow from template (auto-resolve `skill_name`) |
| GET | `/workflows` | List workflows |
| POST | `/workflows` | Create workflow |
| PATCH | `/workflows/{workflow_id}` | Update (including `graph_json`) |
| DELETE | `/workflows/{workflow_id}` | Delete |
| GET | `/workflows/{workflow_id}/steps` | List linear steps |
| PUT | `/workflows/{workflow_id}/steps` | Replace linear steps |
| POST | `/workflows/{workflow_id}/run-once` | Manual run |
| GET | `/workflows/runs/list` | Run history (`?workflow_id=` optional) |
| GET | `/workflows/runs/{run_id}` | Run detail (`step_runs` / `node_runs`) |
| POST | `/workflows/runs/{run_id}/resume` | Resume after approval |
| GET | `/workflows/approvals/pending` | Pending approvals |
| POST | `/workflows/approvals/{approval_id}/approve` | Approve |
| POST | `/workflows/approvals/{approval_id}/reject` | Reject |

**POST /workflows/{workflow_id}/run-once request body:**
```json
{
  "payload": { "query": "example input" }
}
```

**Channel workflow rules** (bindings, preview, templates, stats): `/channels/{channel_id}/workflows/*` and `/channels/templates/workflow`.

**Schedule triggers**: `/skill-schedules` (optional `workflow_id`).

---

## Channel Management

| Method | Path | Description |
|------|------|------|
| GET | `/channels` | List channels |
| POST | `/channels` | Create channel |
| GET | `/channels/{id}` | Get channel details |
| PUT | `/channels/{id}` | Update channel |
| DELETE | `/channels/{id}` | Delete channel |
| GET | `/channels/{id}/webhook-info` | Get webhook callback URL |
| POST | `/channels/test` | Test channel connection |
| GET | `/channels/webhook/wechat/{id}` | WeChat server URL verification |
| POST | `/channels/webhook/wechat/{id}` | Receive WeChat messages |

**ChannelCreate:**
```json
{
  "name": "WeChat Official Account",
  "channel_type": "wechat",
  "config": {
    "app_id": "wx...",
    "app_secret": "...",
    "token": "...",
    "aes_key": "..."
  },
  "enabled": true
}
```

Supported channel types: `web_widget`, `wechat`, `dingtalk`, `whatsapp`, `telegram`, `slack`, `line`, `custom`

---

## Widget Public API (No Auth)

### GET /widget/config/{customer_id}

Get widget embed configuration.

### GET /widget/config/{customer_id}/full

Get full widget config (theme, welcome message, etc.).

### GET /widget/config/{customer_id}/showcase

Get skill showcase config for multi-skill chat panels.

### GET /widget/showcases

List all enabled customer agents with showcase skills.

### POST /widget/conversation

Create a visitor conversation.

### POST /widget/{customer_id}/chat

Send message from widget (non-streaming).

**Request Body:**
```json
{
  "message": "Hello",
  "conversationId": "uuid or null",
  "visitorToken": "optional token",
  "skillId": "optional skill id"
}
```

### POST /widget/{customer_id}/chat/stream

Stream AI reply as Server-Sent Events.

**SSE Events:**
```raw
data: {"type": "token", "content": "Hel"}
data: {"type": "token", "content": "lo"}
data: {"type": "done", "content": "Hello!...", "conversationId": "uuid", "messageId": "uuid"}
data: {"type": "error", "message": "..."}
```

### POST /widget/{customer_id}/upload

Upload attachment from widget (multipart form: file, conversationId, visitorToken, skillId, content).

### GET /widget/{customer_id}/conversation/{conversation_id}

Get widget conversation history.

### GET /widget/{customer_id}/speech/config

Widget STT configuration.

### POST /widget/{customer_id}/speech/transcribe

Widget speech-to-text (multipart file).

### GET /widget/online-agents

List currently online agents.

---

## Speech

| Method | Path | Description |
|------|------|------|
| GET | `/speech/config` | Get STT configuration |
| POST | `/speech/transcribe` | Upload audio and get transcribed text (multipart file) |

---

## System Settings (Admin only)

### GET /settings

Get system settings.

### PUT /settings

Update system settings.

**AppSettingsUpdate:**
```json
{
  "site_name": "MChat",
  "language": "en-US",
  "timezone": "UTC",
  "enable_streaming": true,
  "milvus_enabled": true,
  "storage_backend": "local",
  "max_upload_size_mb": 50
}
```

### POST /settings/milvus/test

Test Milvus connection.

**Request Body:**
```json
{
  "milvus_enabled": true,
  "milvus_host": "localhost",
  "milvus_port": 19530
}
```

### GET /settings/logs

Get backend log tail.

**Params:** `?source=app|error&lines=200`

### GET /settings/widget

Get the first widget (customer) config for the current user.

### PUT /settings/widget

Create or update widget config for the current user (body same as CustomerConfigCreate).

---

## Dashboard

### GET /dashboard/stats

Get dashboard statistics.

**Response:**
```json
{
  "total_conversations": 1280,
  "active_conversations": 12,
  "total_agents": 5,
  "total_documents": 340,
  "total_skills": 8,
  "messages_today": 256,
  "avg_response_time": 0,
  "satisfaction_rate": 0,
  "trends": {
    "conversations": 0,
    "messages": 0,
    "documents": 0
  }
}
```

### GET /dashboard/activities

Get recent activity feed.

---

## Health Check

### GET /health

```json
{
  "status": "healthy",
  "database": "connected",
  "milvus": "connected"
}
```

milvus values: `"connected"`, `"disconnected"`, `"disabled"`

### GET /health/metrics

```json
{
  "uptime": 1717000000.0,
  "python_version": "3.12.0",
  "platform": "darwin"
}
```

---

## WebSocket

Connection: `ws://localhost:3001/ws?token=<jwt_token>&conversation_id=<uuid>`

**Send Message:**
```json
{"type": "message", "content": "Hello"}
```

**Receive Message:**
```json
{"type": "message", "content": "Hello! How can I help you?", "role": "assistant"}
{"type": "token", "content": "Hel"}
{"type": "typing", "status": "start"}
{"type": "typing", "status": "stop"}
```

---

## Error Responses

```json
{
  "detail": "Error description"
}
```

HTTP Status Codes:
- 200: Success
- 201: Created
- 204: Deleted (no content)
- 400: Bad request
- 401: Unauthorized
- 403: Forbidden
- 404: Not found
- 422: Validation error
- 500: Server error
- 503: Service unavailable
