# MChat API 文档

基础 URL: `http://localhost:3001/api`

## 认证

所有管理接口需 Bearer Token（Header: `Authorization: Bearer <token>`）。Widget 公开接口无需认证。

### POST /auth/login

登录获取 JWT Token。

**请求体:**
```json
{
  "username": "admin",
  "password": "your_password"
}
```

**响应:**
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "admin",
    "role": "admin",
    "display_name": "管理员",
    "avatar_url": null,
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

### POST /auth/register

注册新用户（Agent 角色）。

**请求体:**
```json
{
  "username": "agent_001",
  "password": "password123",
  "display_name": "客服小王",
  "avatar_url": null
}
```

### GET /auth/me

获取当前用户信息。需要 Bearer Token。

### GET /auth/bootstrap

获取默认管理员凭据提示（开发环境可显示密码）。

**响应:**
```json
{
  "username": "admin",
  "password": "admin123",
  "show_credentials": true
}
```

### POST /auth/change-password

修改当前用户密码。

**请求体:**
```json
{
  "current_password": "old_pass",
  "new_password": "new_pass_123"
}
```

### 用户管理（Admin 权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/users` | 获取所有用户列表 |
| POST | `/auth/users` | 创建用户 |
| PATCH | `/auth/users/{user_id}` | 更新用户（角色、显示名、密码） |
| DELETE | `/auth/users/{user_id}` | 删除用户 |

**CreateUserRequest:**
```json
{
  "username": "agent_002",
  "password": "pass123456",
  "role": "agent",
  "display_name": "客服小李"
}
```

---

## 聊天

### POST /chat/send

发送消息（非流式）。支持 SSE 流式响应的端点见 Widget 部分 `/widget/{customer_id}/chat/stream`。

**请求头:** `Authorization: Bearer <token>`

**请求体:**
```json
{
  "conversation_id": "uuid",
  "content": "你好",
  "role": "user",
  "extra_data": {}
}
```

### POST /chat/upload

上传附件并发送消息（multipart form）。

### GET /chat/conversations

获取对话列表（分页）。

**参数:** `?skip=0&limit=20&status=active&search=关键词`

### GET /chat/conversations/stats

获取对话统计（total, active, closed）。

### POST /chat/conversations

创建新对话（Admin）。

**请求体:**
```json
{
  "title": "新对话",
  "ai_config_id": "uuid",
  "visitor_id": null
}
```

### GET /chat/conversations/{id}

获取对话详情（含消息列表）。

### POST /chat/conversations/{id}/close

关闭对话。

### POST /chat/conversations/init

初始化访客对话（无需认证）。

**请求体:**
```json
{
  "visitor_id": "optional visitor ID",
  "title": "可选标题",
  "ai_config_id": "uuid (客户配置ID)",
  "contact_info": "可选联系方式"
}
```

---

## Agent 管理

### AI 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agents/ai-configs` | 创建 AI 配置 |
| GET | `/agents/ai-configs` | 获取配置列表 |
| GET | `/agents/ai-configs/{id}` | 获取配置详情 |
| PUT | `/agents/ai-configs/{id}` | 更新配置 |
| DELETE | `/agents/ai-configs/{id}` | 删除配置 |
| POST | `/agents/ai-configs/models` | 拉取模型列表 |
| POST | `/agents/ai-configs/test` | 测试 API 连接 |

**AIConfig 对象:**
```json
{
  "name": "GPT-4 客服",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "api_key": "sk-...",
  "api_base": "https://api.openai.com/v1",
  "system_prompt": "你是一个专业的客服助手...",
  "temperature": 0.7,
  "max_tokens": 2048,
  "is_default": true
}
```

### 客户配置

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agents/customer-configs` | 创建客户配置 |
| GET | `/agents/customer-configs` | 获取配置列表 |
| GET | `/agents/customer-configs/{id}` | 获取配置详情 |
| PUT | `/agents/customer-configs/{id}` | 更新配置 |
| POST | `/agents/customer-configs/upload-asset` | 上传自动回复素材 |

**CustomerConfig 对象:**
```json
{
  "name": "主站客服",
  "short_code": "main",
  "ai_config_id": "uuid",
  "skill_ids": ["skill-uuid"],
  "knowledge_base_ids": ["kb-uuid"],
  "auto_reply_rules": [
    {
      "name": "欢迎语",
      "enabled": true,
      "trigger_text": "你好",
      "keywords": ["hello", "hi"],
      "channels": ["widget", "wechat"],
      "reply_text": "你好！有什么可以帮你的？",
      "threshold": 0.78,
      "asset": null
    }
  ],
  "welcome_message": "你好！有什么可以帮你的？",
  "offline_message": "当前不在线，请留言",
  "theme": {
    "primaryColor": "#3b82f6",
    "botName": "智能客服",
    "widgetTitle": "在线客服",
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

## 知识库

### 知识库 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge/bases` | 创建知识库 |
| GET | `/knowledge/bases` | 获取知识库列表 |
| GET | `/knowledge/bases/{id}` | 获取知识库详情 |
| PATCH | `/knowledge/bases/{id}` | 更新知识库（含 RAG 设置） |
| DELETE | `/knowledge/bases/{id}` | 删除知识库 |
| POST | `/knowledge/bases/{id}/reindex` | 重新分块+嵌入 |

**KnowledgeBase RAG 设置（PATCH body 可部分更新）:**
```json
{
  "name": "产品知识库",
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

### 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/bases/{kb_id}/documents` | 获取文档列表 |
| POST | `/knowledge/bases/{kb_id}/documents` | 创建文档 |
| DELETE | `/knowledge/documents/{doc_id}` | 删除文档 |
| POST | `/knowledge/bases/{kb_id}/import-file` | 上传文件导入 (multipart) |
| POST | `/knowledge/bases/{kb_id}/import-url` | URL 导入 |
| POST | `/knowledge/search` | 知识库检索 |

**DocumentCreate:**
```json
{
  "title": "退款政策",
  "content": "签收 7 天内可申请退款...",
  "source": "帮助中心",
  "source_url": "https://example.com/refund"
}
```

### 搜索请求与响应

**请求:**
```json
{
  "query": "如何退款",
  "knowledge_base_id": "uuid",
  "top_k": 5
}
```

**响应:**
```json
{
  "results": [
    {
      "document_id": "uuid",
      "title": "退款政策",
      "content": "签收 7 天内可申请退款...",
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

**请求体（可选）:**
```json
{
  "rechunk": true
}
```

**响应:**
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
    {"document_id": "uuid", "title": "退款政策", "status": "ok", "chunk_count": 5},
    {"document_id": "uuid", "title": "物流说明", "status": "failed", "error": "..."}
  ]
}
```

### Embedding 模型（本地上传）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/embedding-models` | 获取已上传模型列表 |
| POST | `/knowledge/embedding-models/upload` | 上传模型 zip（multipart，可选 name 字段） |
| DELETE | `/knowledge/embedding-models/{id}` | 删除模型 |

---

## 技能

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/skills` | 获取技能列表 |
| PATCH | `/skills/{id}` | 启用/禁用技能、更新配置 |
| DELETE | `/skills/{id}` | 删除技能 |
| POST | `/skills/reload` | 从文件系统重新加载技能 |
| POST | `/skills/upload` | 上传技能包 (zip) |
| POST | `/skills/install-url` | 从 URL 或 ClawHub 名称安装技能 |
| GET | `/skills/catalog` | 浏览 ClawHub 技能目录（可选 `?query=&limit=24`） |

**POST /skills/install-url 请求体:**
```json
{
  "url": "https://example.com/skill.zip 或 patent-search",
  "name": "可选技能名"
}
```

---

## 工作流（Beta）

> 编排多个 Skill 为流程，支持线性步骤与 `graph_json` 图 DAG。详见 [workflow-orchestrator.zh.md](./workflow-orchestrator.zh.md)。

权限：`skills:read` / `skills:write`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workflows/templates` | 内置 + 我的模板列表（可选 `?locale=zh\|en`） |
| GET | `/workflows/showcase-config` | 专利 Workflow 展示配置（skill 名、是否已安装/就绪） |
| POST | `/workflows/{workflow_id}/save-as-template` | 将工作流图形保存为我的模板 |
| DELETE | `/workflows/templates/{template_id}` | 删除我的模板 |
| POST | `/workflows/from-template/{template_id}` | 从模板创建工作流（自动解析 skill_name） |
| GET | `/workflows` | 工作流列表 |
| POST | `/workflows` | 创建工作流 |
| PATCH | `/workflows/{workflow_id}` | 更新（含 `graph_json`） |
| DELETE | `/workflows/{workflow_id}` | 删除 |
| GET | `/workflows/{workflow_id}/steps` | 线性步骤列表 |
| PUT | `/workflows/{workflow_id}/steps` | 替换线性步骤 |
| POST | `/workflows/{workflow_id}/run-once` | 手动执行一次 |
| GET | `/workflows/runs/list` | 运行记录（可选 `?workflow_id=`） |
| GET | `/workflows/runs/{run_id}` | 运行详情（含 `step_runs` / `node_runs`） |
| POST | `/workflows/runs/{run_id}/resume` | 审批通过后续跑 |
| GET | `/workflows/approvals/pending` | 待审批列表 |
| POST | `/workflows/approvals/{approval_id}/approve` | 批准 |
| POST | `/workflows/approvals/{approval_id}/reject` | 拒绝 |

**POST /workflows/{workflow_id}/run-once 请求体:**
```json
{
  "payload": { "query": "示例输入" }
}
```

运行状态：`running` / `success` / `failed` / `paused`（等待审批）。

**频道工作流规则**（绑定、预览、模板、统计）见渠道 API 扩展路径 `/channels/{channel_id}/workflows/*` 与 `/channels/templates/workflow`。

**定时触发**见 `/skill-schedules`（可指定 `workflow_id`）。

---

## 渠道管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/channels` | 获取渠道列表 |
| POST | `/channels` | 创建渠道 |
| GET | `/channels/{id}` | 获取渠道详情 |
| PUT | `/channels/{id}` | 更新渠道 |
| DELETE | `/channels/{id}` | 删除渠道 |
| GET | `/channels/{id}/webhook-info` | 获取渠道 webhook 回调 URL |
| POST | `/channels/test` | 测试渠道连接 |
| GET | `/channels/webhook/wechat/{id}` | 微信公众号服务器验证 |
| POST | `/channels/webhook/wechat/{id}` | 接收微信公众号消息 |

**ChannelCreate:**
```json
{
  "name": "微信公众号",
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

支持渠道类型: `web_widget`, `wechat`, `dingtalk`, `whatsapp`, `telegram`, `slack`, `line`, `custom`

---

## Widget 公开 API（无需认证）

### GET /widget/config/{customer_id}

获取 Widget 嵌入配置。

### GET /widget/config/{customer_id}/full

获取完整 Widget 配置（含主题、欢迎语等）。

### GET /widget/config/{customer_id}/showcase

获取技能展示配置（多技能聊天面板）。

### GET /widget/showcases

列出所有已启用且有展示技能的客户配置。

### POST /widget/conversation

创建访客对话。

### POST /widget/{customer_id}/chat

Widget 消息发送（非流式）。

**请求体:**
```json
{
  "message": "你好",
  "conversationId": "uuid or null",
  "visitorToken": "optional token",
  "skillId": "optional skill id"
}
```

### POST /widget/{customer_id}/chat/stream

Widget 流式消息（SSE）。

**SSE 事件:**
```raw
data: {"type": "token", "content": "你"}
data: {"type": "token", "content": "好"}
data: {"type": "done", "content": "你好！...", "conversationId": "uuid", "messageId": "uuid"}
data: {"type": "error", "message": "..."}
```

### POST /widget/{customer_id}/upload

Widget 上传附件（multipart form，字段: file, conversationId, visitorToken, skillId, content）。

### GET /widget/{customer_id}/conversation/{conversation_id}

获取 Widget 对话历史。

### GET /widget/{customer_id}/speech/config

Widget 语音识别配置。

### POST /widget/{customer_id}/speech/transcribe

Widget 语音转文字（multipart file）。

### GET /widget/online-agents

获取在线客服列表。

---

## 语音识别

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/speech/config` | 获取语音识别配置 |
| POST | `/speech/transcribe` | 上传音频文件转文字（multipart file） |

---

## 系统设置（Admin 权限）

### GET /settings

获取系统设置。

### PUT /settings

更新系统设置。

**AppSettingsUpdate:**
```json
{
  "site_name": "MChat",
  "language": "zh-CN",
  "timezone": "Asia/Shanghai",
  "enable_streaming": true,
  "milvus_enabled": true,
  "storage_backend": "local",
  "max_upload_size_mb": 50
}
```

### POST /settings/milvus/test

测试 Milvus 连接。

**请求体:**
```json
{
  "milvus_enabled": true,
  "milvus_host": "localhost",
  "milvus_port": 19530
}
```

### GET /settings/logs

获取后端日志尾部。

**参数:** `?source=app|error&lines=200`

### GET /settings/widget

获取当前用户的第一个 Widget（客户）配置。

### PUT /settings/widget

创建或更新当前用户的 Widget 配置（body 同 CustomerConfigCreate）。

---

## 仪表盘

### GET /dashboard/stats

获取仪表盘统计数据。

**响应:**
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

获取最近活动列表。

---

## 健康检查

### GET /health

```json
{
  "status": "healthy",
  "database": "connected",
  "milvus": "connected"
}
```

milvus 可能的值: `"connected"`, `"disconnected"`, `"disabled"`

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

连接: `ws://localhost:3001/ws?token=<jwt_token>&conversation_id=<uuid>`

**发送消息:**
```json
{"type": "message", "content": "你好"}
```

**接收消息:**
```json
{"type": "message", "content": "你好！有什么可以帮你的？", "role": "assistant"}
{"type": "token", "content": "你"}
{"type": "typing", "status": "start"}
{"type": "typing", "status": "stop"}
```

---

## 错误响应

```json
{
  "detail": "错误描述信息"
}
```

HTTP 状态码:
- 200: 成功
- 201: 创建成功
- 204: 删除成功（无内容）
- 400: 请求参数错误
- 401: 未认证
- 403: 无权限
- 404: 资源不存在
- 422: 参数校验失败
- 500: 服务器错误
- 503: 服务不可用
