# MChat — 多租户垂直 RAG 平台

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node 20+](https://img.shields.io/badge/node-20+-green.svg)](https://nodejs.org/)

**[English](README.md)** · **[GitHub](https://github.com/windinwing/mchat)**

MChat 是一款**轻量、可嵌入、多租户**的垂直领域 RAG 平台，整合流式 Bot 引擎、生产级 RAG 知识库、Skill 热加载插件、**可视化 Workflow 编排（Beta）**与一行脚本可嵌入的 Widget，支持 **10+ 大模型**与多渠道触达（网站 Widget、WebSocket、REST、微信公众号等）。

内置 **AI 客服**开箱即用；同一套能力可扩展为**垂直通道**——专利查新、医疗咨询、法律问答等领域 RAG 套餐（专属知识库、技能包、检索策略），一行 `<script>` 嵌入任意网站。

## 为什么选择 MChat？

| 特色 | 说明 |
|------|------|
| **垂直 RAG 一站式** | Bot + 混合检索（向量 + BM25 + RRF）+ 重排序 + 查询改写 + Parent-Child 分块，不是简单套壳聊天 |
| **Skill 可落地** | 热加载 `SKILL.md`、OpenClaw 兼容、URL/zip 安装、ClawHub（如 `patent-search`） |
| **Workflow 编排（Beta）** | ComfyUI 风格图编辑器（指针/拖拽切换）、DAG 执行、merge/审批/条件分支、频道与定时触发 |
| **可嵌入 & 多租户** | 每通道独立 Widget 品牌；Agent、技能、知识库数据隔离 |
| **运营友好** | 完整中英文管理后台、仪表盘、频道规则、技能定时任务 |
| **开发友好** | FastAPI + React、Swagger、Docker Compose、MIT 开源 |

## 在线站点

- [英文主站](http://mchat.chat)
- [中文主站](https://mchat.9235.net)
- [完整图片说明](docs/product-tour.zh.md)
- [产品路线图](docs/roadmap.zh.md)（知识库、Widget、渠道、API、运营、权限、Workflow）
- [Workflow 编排（Beta）](docs/workflow-orchestrator.zh.md)

## 界面预览

点击任意截图可查看大图。

### 首页与后台分区

[![MChat 首页与后台分区](docs/images/mchat.home.zone.zh.png)](docs/images/mchat.home.zone.zh.png)

### 对话管理

[![对话管理](docs/images/mchat.conversations.zh.png)](docs/images/mchat.conversations.zh.png)

### 垂直通道配置（Agent）

[![客服 Agent 配置](docs/images/mchat.customer.zh.png)](docs/images/mchat.customer.zh.png)

### 知识库管理

[![知识库管理](docs/images/mchat.knowledge.zh.png)](docs/images/mchat.knowledge.zh.png)

### Widget 演示

[![Widget 演示](docs/images/mchat.widget.zh.png)](docs/images/mchat.widget.zh.png)

### Widget 聊天界面

[![Widget 聊天界面](docs/images/mchat.chat.zh.png)](docs/images/mchat.chat.zh.png)

### 渠道管理

[![渠道管理](docs/images/mchat.channel.zh.png)](docs/images/mchat.channel.zh.png)

### Workflow 编排（Beta）

[![工作流列表与模板](docs/images/workflow.cn.png)](docs/images/workflow.cn.png)

[![工作流图编辑器](docs/images/workflow.graph.cn.png)](docs/images/workflow.graph.cn.png)

## 特性

- **Bot 引擎** — 流式 LLM 推理与工具调用，支持 OpenAI、Anthropic、Google、DeepSeek、Ollama、Groq 等
- **Skill 插件** — 从磁盘、zip、URL 热加载 `SKILL.md`，兼容 OpenClaw；付费技能包可作为垂直通道增值能力
- **RAG 知识库** — 多策略分块、多 provider 嵌入、混合检索（向量 + BM25 + RRF）、重排序、查询改写、Parent-Child 上下文
- **Workflow 编排（Beta）** — React Flow 图编辑器、线性/图 DAG 执行、merge/条件/审批节点、内置报表模板、手动/定时/频道触发
- **嵌入式 Widget** — 一行 `<script>` 接入品牌化垂直 RAG 窗口
- **多租户** — 多个独立通道配置，各自拥有 AI、技能与知识库，数据完全隔离
- **垂直通道** — 领域模板一键创建：模型、Prompt、知识库、重排序、技能包、Widget 主题
- **多渠道** — Web Widget、REST、WebSocket、微信公众号（钉钉/WhatsApp/Telegram 等 [规划中](docs/roadmap.zh.md#3-多渠道频道)）
- **语音输入** — OpenAI Whisper 转写（可选本地模型）
- **安全认证** — JWT、API Key、RBAC
- **Docker 部署** — `docker compose up -d` 一键启动

## 快速开始

### Docker（推荐）
```bash
git clone https://github.com/windinwing/mchat.git
cd mchat

docker compose -f ops/docker/docker-compose.lite.yml up -d

# 管理后台: http://localhost:5173
# API 文档:  http://localhost:3001/docs
# 项目主页:  http://localhost:5173/
```

**默认管理员账号**（首次启动自动创建）：`admin` / `admin123`  
登录后请在 **管理后台 → 用户管理** 中修改密码。可通过 `.env` 设置 `ADMIN_USERNAME`、`ADMIN_PASSWORD`；生产环境建议设置 `SHOW_BOOTSTRAP_CREDENTIALS=false` 隐藏登录页默认密码提示。

### 嵌入 Widget

```html
<script
  src="http://localhost:5173/widget-loader.js"
  data-mchat-url="http://localhost:3001"
  data-agent-id="YOUR_AGENT_ID"
  data-primary-color="#3b82f6"
  data-welcome-message="你好！有什么可以帮助你的？"
  data-bot-name="智能助手"
></script>
```

### 本地开发

```bash
make install   # 安装依赖
make db-mysql-dev   # 可选：本地 MySQL
ollama pull nomic-embed-text   # 推荐：本地 Embedding（知识库向量）
make dev         # Core 本地开发（app.main，管理后台无「模板」菜单）
make cloud       # Cloud 本地开发（cloud.main + 方案市场 / 门户）

# 后端: http://localhost:3001  (/docs 为 Swagger)
# 前端: http://localhost:5173
```

| 命令 | 后端 | 管理后台「模板」 | 门户 / 方案市场 |
|------|------|------------------|-----------------|
| `make dev` | `app.main:app` | 无 | 无 |
| `make cloud` | `cloud.main:app` | 有 | 有 |
| `make deploy-core` | Core | 无 | 无 |
| `make deploy-cloud` | Cloud | 有 | 有 |
```bash
make test      # 运行测试
make lint      # 代码检查
mchat run      # CLI 启动服务
```

## 项目结构

```raw
mchat/
├── src/
│   ├── backend/          # FastAPI 后端 (Python 3.12+)
│   │   └── app/
│   │       ├── api/      # REST 路由
│   │       ├── bot/      # Bot 引擎 + 模型提供商
│   │       ├── knowledge/# RAG + Milvus
│   │       ├── skill/    # 技能系统
│   │       ├── worker/   # 定时任务与工作流调度
│   │       └── channels/ # 微信等频道适配
│   └── frontend/         # React + Vite + Tailwind
│       └── src/
│           ├── i18n/     # 中英文 (react-i18next)
│           └── pages/    # 落地页 + 管理后台
├── skills/               # 技能包目录
├── channel_templates/    # 垂直通道模板（专利查新、医疗咨询等）
├── docs/                 # 架构、API、部署、路线图
├── ops/docker/           # Docker Compose
└── Makefile
```

## 支持的 LLM 提供商

| 提供商 | 默认 API 地址 | 说明 |
|--------|---------------|------|
| `openai` | https://api.openai.com/v1 | GPT-4o、o1 等 |
| `anthropic` | https://api.anthropic.com | Claude |
| `google` | https://generativelanguage.googleapis.com | Gemini |
| `deepseek` | https://api.deepseek.com | OpenAI 兼容 |
| `ollama` | http://localhost:11434/v1 | 本地模型 |
| `groq` | https://api.groq.com/openai/v1 | 高速推理 |
| `zhipu` / `moonshot` / `siliconflow` / `together` | *(需配置 api_base)* | 国内/托管 API |
| `openai-compatible` | *(需配置 api_base)* | 任意 OpenAI 兼容端点 |

## API 概览

| 模块 | 路径 | 说明 |
|------|------|------|
| 聊天 | `/api/chat/*` | 对话与消息 |
| Agent | `/api/agents/*` | AI 配置 |
| 知识库 | `/api/knowledge/*` | 文档与检索 |
| Widget | `/api/widget/*` | 嵌入式聊天 |
| 技能 | `/api/skills/*` | 技能管理与安装 |
| 工作流 | `/api/workflows/*` | 工作流 CRUD、运行、模板（Beta） |
| 频道 | `/api/channels/*` | 微信公众号等 |
| 通道模板 | `/api/channels/templates/*` | 垂直通道一键创建 |
| 语音 | `/api/speech/*` | 语音转文字 |
| 认证 | `/api/auth/*` | 登录 / JWT |
| WebSocket | `/ws` | 实时流式 |
| 健康检查 | `/api/health` | 服务状态 |

详见 [docs/api.md](docs/api.md) 或启动后访问 `/docs`。

## 多语言

管理后台与项目主页支持**简体中文**与 **English**。语言偏好保存在 `localStorage`（`mchat_lang`），可在页头或侧栏切换。技能 `config.i18n` 与工作流界面按 UI 语言显示名称。

## CLI 工具

```bash
mchat init
mchat run
mchat config show
mchat skill list
mchat skill create <name>
mchat skill install <url-or-name>
mchat db init
mchat db seed
```
## Skill 兼容说明

- 支持标准 frontmatter `SKILL.md` 技能包
- 支持 OpenClaw 风格 `SKILL.md` 多语言 blocks（自动写入 `config.i18n`）
- 管理后台支持 zip 上传和 URL 安装（`/api/skills/install-url`）
- CLI 支持 URL 或 ClawHub 名称安装，例如：`mchat skill install patent-search`
- **付费技能包**：垂直通道可绑定专属技能作为增值服务
- **Workflow 复用**：同一 skill（如 `patent-search`）可在多个节点以不同 `command` / `dimension` 参数重复出现

## Docker 变体

| 文件 | 服务 | 场景 |
|------|------|------|
| `docker-compose.lite.yml` | MySQL + 后端 + 前端 | 开发 / 轻量 |
| `docker-compose.yml` | + Milvus、etcd、MinIO、Redis | 完整 RAG |
| `docker-compose.prod.yml` | + Nginx HTTPS | 生产 |
| `docker-compose.dev.yml` | 热重载 | 本地开发 |

## 技术栈

**后端：** FastAPI、SQLAlchemy 2.0、Milvus、OpenAI / Anthropic SDK、JWT、Loguru  

**前端：** React 19、TypeScript、Vite、Tailwind CSS 4、Zustand、react-i18next、React Flow

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎提交 Issue 与 Pull Request。仓库地址：[https://github.com/windinwing/mchat](https://github.com/windinwing/mchat)
