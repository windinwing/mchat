# MChat 产品路线图

本文档记录 MChat 在知识库、Widget、渠道、API、运营能力与权限等方面的**当前状态**与**规划方向**，便于贡献者与集成方对齐预期。实现进度以代码与 CHANGELOG 为准。

---

## 1. 知识库与 RAG

### 当前状态（P0 核心已全部实现）

| 能力 | 说明 |
|------|------|
| 文档导入 | txt / md / html / docx / pdf（需 pdfplumber）等 |
| 可配置分块 | `fixed` / `paragraph` / `markdown` / `semantic` 四种策略，知识库级可配 size / overlap / min_chunk_size / semantic_threshold |
| 多 Embedding 模型 | 全局或知识库级：OpenAI 兼容 API / 本地上传 HuggingFace zip（`sentence-transformers` 加载）/ Ollama 本机模型 |
| 混合检索 | `vector` / `keyword` / `hybrid` 三种模式，BM25 纯 Python 关键词索引 + Milvus 向量，RRF 融合 |
| Rerank 精排 | `lexical`（内置轻量）/ `cohere` / `bge` / `cross-encoder` 四种 provider，可配置 top_n |
| Query Rewriting | LLM 改写用户问题生成多视角查询，提升召回率（可配置开关与改写条数） |
| Parent-Child 检索 | semantic 策略下自动生成父块上下文，检索命中子块后替换为父块内容提升完整度 |
| Chunk 存储 | `document_chunks` 表（含 `parent_content` 字段）+ Milvus 向量 |
| Agent 绑定 | 显式勾选知识库才参与检索 |
| 重嵌入 | 切换模型后 `POST .../reindex` 全量重嵌入，`reindex_status` 追踪进度 |
| Embedding 指纹 | `indexed_embedding_key` 记录上次索引所用配置（provider|model|dim|base），检测变更 |

相关实现：`chunking.py`、`embedder.py`、`local_embedder.py`、`model_storage.py`、`rag.py`、`rag_config.py`、`chunk_store.py`、`importer.py`、`bm25.py`、`rerank.py`、`query_rewriter.py`、`query_rewrite_chat.py`、`embedding_fingerprint.py`。

### 知识库级完整配置

```yaml
# 分块
chunk:
  strategy: fixed | paragraph | markdown | semantic
  size: 500
  overlap: 50
  min_chunk_size: 80
  semantic_threshold: 0.7
  parent_enabled: true

# 嵌入
embedding:
  provider: openai | local | ollama
  model: text-embedding-3-small
  api_base: https://api.openai.com/v1
  dimension: 1536

# 检索
retrieval:
  mode: vector | keyword | hybrid
  top_k: 5
  candidate_k: 20
  rerank:
    enabled: true
    provider: lexical | cohere | bge | cross-encoder
    model: null  # cohere 或 cross-encoder 模型名
    top_n: 5
  bm25:
    enabled: true
    k1: 1.5
    b: 0.75
  query_rewrite:
    enabled: false
    count: 3
```

管理后台为每个知识库提供上述配置项，并提供 FAQ / 手册 / 网页抓取等预设模板。

### 规划：检索可观测性与评估

| 方向 | 说明 |
|------|------|
| 检索日志 | 记录每次检索的原始分、融合分、rerank 分、命中 chunk id |
| 零结果查询 | 统计未命中查询，辅助调优 |
| 评估集 | 支持标注 Q&A 对，计算 Recall@k / MRR |
| 检索对比 | 同一查询对比不同策略/模型的效果 |

---

## 2. Web Widget

### 当前状态

- 轻量 `widget-loader.js` + iframe/嵌入聊天
- 品牌化：主色、欢迎语、Bot 名称
- SSE 流式、访客 token、域名白名单
- 拖拽调整尺寸、全屏模式

### 规划：对标 Intercom / Chatwoot 成熟体验

参考 [Intercom Messenger](https://www.intercom.com/messenger) 与 [Chatwoot Website Widget](https://www.chatwoot.com/features/website-live-chat) 的常见能力：

| 类别 | 规划能力 |
|------|----------|
| 外观 | 多主题、圆角/位置、移动端全屏、Launcher 图标与未读角标 |
| 会话前 | 预聊天表单（姓名/邮箱/自定义字段）、营业时间、离线留言 |
| 会话中 | 已读回执、输入状态、富文本/链接预览、文件上传与预览 |
| 会话后 | CSAT 评分、转人工排队提示 |
| 运营 | 主动消息（Proactive）、根据 URL/停留时间触发 |
| 集成 | `postMessage` API、与 CRM/工单 webhook、GDPR 同意条 |
| 性能 | 懒加载、CDN、体积预算（目标 &lt; 50KB 核心 loader） |

实现原则：**默认简单嵌入一行 script，高级能力通过 `data-*` 与 JS API 可选开启**。

---

## 3. 多渠道（频道）

### 当前状态

| 渠道 | 状态 |
|------|------|
| Web Widget | ✅ 已实现 |
| 微信公众号 | ✅ `wechat_adapter.py` |
| REST / WebSocket | ✅ API 集成 |
| 钉钉 / WhatsApp / Telegram / Slack / LINE | 🟡 管理后台**配置 UI 已预留**，后端适配器待实现 |
| Custom Webhook | 🟡 字段预留 |

配置定义见 `src/frontend/src/i18n/channelTypes.ts`。

### 规划：预留频道落地

每个渠道统一抽象 `ChannelAdapter`：

```
入站消息 → 归一化 Message → ChatService / BotEngine
出站回复 ← 格式化（文本/卡片/媒体）← 渠道限制
```

| 渠道 | 实现要点 |
|------|----------|
| **钉钉** | 企业内部应用 / 机器人 webhook；签名验证；卡片消息 |
| **WhatsApp** | Meta Cloud API；模板消息；媒体下载 |
| **Telegram** | Bot API long polling / webhook；Markdown 限制 |
| **Slack** | Events API + Bolt 模式；线程回复 |
| **LINE** | Messaging API；Reply token 时效 |

共用能力：渠道级 Agent 绑定、消息幂等、重试队列、渠道专属自动回复规则。

---

## 4. 开放 API 与网站文档

### 当前状态

- 运行时 Swagger：`http://localhost:3001/docs`
- 仓库内 Markdown：[api.zh.md](api.zh.md)（偏内部/开发）

### 规划：面向集成方的公开 API 文档

**目标**：在官网（如 [mchat.9235.net](https://mchat.9235.net)）提供稳定、可分享的开发者文档。

| 内容 | 说明 |
|------|------|
| 认证 | JWT、API Key、Visitor Token 使用场景 |
| 核心 API | 对话、Agent、知识库检索、Widget、Webhook |
| WebSocket | 流式协议、事件类型 |
| 示例 | curl、Python、Node 最小可运行示例 |
| 限流与错误码 | 429/401 等统一约定 |
| 变更日志 | API 版本与破坏性变更说明 |

**交付方式（择一或组合）**：

1. 静态站点（VitePress / Docusaurus）挂载在 `/docs`
2. OpenAPI 3.0 导出 + Redoc 渲染
3. 与 Swagger 同源生成，避免文档与代码漂移

---

## 5. 客服运营与统计报告

### 当前状态

- 仪表盘基础统计：`/api/dashboard/stats`（会话量、消息量等趋势）
- 对话列表、消息记录、Agent 配置

### 规划：完善运营能力

| 模块 | 规划指标 / 能力 |
|------|-----------------|
| 会话分析 | 平均响应时长、首次响应时间、解决率、转人工率 |
| Agent 效能 | 各 Agent 会话量、满意度、知识库命中率 |
| 知识库 | 检索次数、零结果查询、热门 chunk |
| 渠道 | 各渠道流量占比、高峰时段 |
| 导出 | CSV / 按日期范围导出 |
| 告警 | 零结果检索激增、API 错误率（可选对接 Webhook） |

---

## 6. 用户角色与权限（RBAC）

### 当前状态

- 角色：`admin` / `agent`（粗粒度）
- 中间件：`require_admin`、`require_agent_or_admin`

### 规划：Role → Permission

```
User ── belongs_to ── Role(s)
Role ── has_many ── Permission(s)
Permission: resource + action  (e.g. knowledge:write, agent:read)
```

| 资源域 | 示例权限 |
|--------|----------|
| `knowledge` | read, write, delete, reindex |
| `agent` | read, write, publish |
| `conversation` | read, assign, export |
| `user` | read, invite, role_assign |
| `settings` | read, write |
| `channel` | read, write |
| `dashboard` | read |

- 管理后台：角色模板 + 自定义角色
- API：装饰器/依赖注入校验 `permission`
- 多租户：租户管理员仅能管理本租户资源

---

## 7. 超越「客服系统」的场景

MChat 核心是**可嵌入的多租户对话 + RAG + Skill**，不仅限于官网客服：

| 场景 | 用法 |
|------|------|
| **内部知识助手** | 接入企业 Wiki/Confluence，员工问答 |
| **产品文档 Copilot** | 文档站 Widget + 代码块引用 |
| **销售/售前** | 产品库 RAG + 自动发送彩页/报价模板 |
| **工单辅助** | Webhook 拉取工单上下文，生成回复草稿 |
| **垂直 Agent** | Skill 调用业务 API（专利检索、订单查询等已有实践） |
| **IoT / 设备** | 精简 Widget + 语音输入，设备说明 RAG |
| **社区/论坛** | Telegram/Slack 机器人答疑 |

产品叙事与示例将逐步补充到 [产品导览](product-tour.zh.md)。

---

## 优先级建议（供讨论）

| 优先级 | 方向 | 理由 |
|--------|------|------|
| ~~P0~~ | ~~可配置分块 + 多 Embedding~~ | ✅ 已完成 |
| ~~P0~~ | ~~混合检索 + Rerank~~ | ✅ 已完成（含 Query Rewriting、Parent-Child） |
| P1 | 检索可观测性（日志/评估/对比） | 调优与排查必需 |
| P1 | 钉钉 / Telegram / WhatsApp | 渠道 UI 已预留，用户需求明确 |
| P1 | 公开 API 文档站 | 降低集成门槛 |
| P1 | Widget 体验（预表单、CSAT、未读） | 对外产品力 |
| P1 | 轻客服收件箱（会话未读 + Admin WS） | 见 [inbox-notifications.zh.md](inbox-notifications.zh.md) |
| P1 | Workflow 运行回放与可观测 | Beta 走向生产 |
| P2 | 运营报表深化 | 企业采购决策因素 |
| P2 | 细粒度 RBAC | 团队规模扩大后必需 |
| P3 | 场景案例与模板 | 获客与差异化 |

欢迎通过 [GitHub Issues](https://github.com/windinwing/mchat/issues) 讨论优先级与具体需求。

---

## 8. Workflow 编排（Beta）

### 当前状态

| 能力 | 说明 |
|------|------|
| 线性编排 | 多 Skill 顺序执行、参数模板、步骤日志 |
| 图编排 | React Flow 编辑器 + DAG 执行（条件/并行/审批） |
| 触发 | 手动、定时任务、频道消息规则 |
| 运营 | 规则模板、导入导出、命中统计、待审批队列 |
| 告警 | 失败/拒绝 Webhook（`WORKFLOW_ALERT_WEBHOOK_URL`） |

详细设计见 [Workflow orchestrator（英文）](workflow-orchestrator.en.md) · [中文](workflow-orchestrator.zh.md)。

### 规划

| 方向 | 说明 |
|------|------|
| 运行态画布回放 | 在图编辑器中高亮节点执行状态 |
| 节点库增强 | 搜索、分类、ComfyUI 风格卡片 |
| 流程版本 | 发布/回滚、变更审计 |
| 可观测 | 运行指标、慢节点分析 |
