# MChat — Multi-Tenant Vertical RAG Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node 20+](https://img.shields.io/badge/node-20+-green.svg)](https://nodejs.org/)

**[中文文档](README.zh.md)** · **[GitHub](https://github.com/windinwing/mchat)**

MChat is a **lightweight, embeddable, multi-tenant vertical RAG platform**. It combines a streaming Bot engine, production-grade RAG knowledge base, hot-reload Skill plugins, **visual Workflow orchestration (Beta)**, and a one-line embeddable Widget — with **10+ LLM providers** and multi-channel delivery (Web Widget, WebSocket, REST, WeChat Official Account, and more).

Built-in **AI customer service** works out of the box. Extend the same stack into **vertical channels** — patent search, medical, legal, and other domain RAG packages with dedicated knowledge bases, skill packs, and tuned retrieval — embed anywhere with a single `<script>` tag.

## Why MChat?

| Strength | What you get |
|----------|----------------|
| **Vertical RAG in one stack** | Bot + hybrid retrieval (vector + BM25 + RRF) + rerank + query rewrite + parent-child chunks — not a thin chatbot wrapper |
| **Skills that ship** | Hot-reload `SKILL.md`, OpenClaw-compatible packs, URL/zip install, ClawHub (`patent-search`, etc.) |
| **Workflow orchestration (Beta)** | ComfyUI-style graph editor (pointer/pan), DAG runs, merge nodes, approval gates, channel & schedule triggers |
| **Embed & multi-tenant** | Branded Widget per channel; isolated agents, skills, and knowledge bases |
| **Operator-friendly** | Full admin UI in **English & 简体中文**, dashboards, channel rules, skill schedules |
| **Developer-friendly** | FastAPI + React, Swagger, Docker Compose, MIT license |

## Live websites

- [English main site](http://mchat.chat)
- [Chinese main site](https://mchat.9235.net)
- [Full screenshot tour](docs/product-tour.en.md)
- [Product roadmap](docs/roadmap.en.md)
- [Workflow orchestrator (Beta)](docs/workflow-orchestrator.zh.md)

## UI preview

Click any screenshot to open the full image.

### Homepage and admin zones

[![MChat homepage and admin zones](docs/images/mchat.home.zone.en.png)](docs/images/mchat.home.zone.en.png)

### Conversation management

[![Conversation management](docs/images/mchat.conversations.en.png)](docs/images/mchat.conversations.en.png)

### Vertical channel configuration (Agent)

[![Customer agent configuration](docs/images/mchat.customer.en.png)](docs/images/mchat.customer.en.png)

### Knowledge base

[![Knowledge base](docs/images/mchat.knowledge.en.png)](docs/images/mchat.knowledge.en.png)

### Widget demo

[![Widget demo](docs/images/mchat.widget.en.png)](docs/images/mchat.widget.en.png)

### Widget chat panel

[![Widget chat panel](docs/images/mchat.chat.en.png)](docs/images/mchat.chat.en.png)

### Channel management

[![Channel management](docs/images/mchat.channel.en.png)](docs/images/mchat.channel.en.png)

### Workflow orchestration (Beta)

[![Workflow list and templates](docs/images/workflow.en.png)](docs/images/workflow.en.png)

[![Workflow graph editor](docs/images/workflow.graph.en.png)](docs/images/workflow.graph.en.png)

## Features

- **Bot engine** — Streaming LLM inference + tool calling; OpenAI, Anthropic, Google, DeepSeek, Ollama, Groq, and more
- **Skill plugins** — Hot-reload `SKILL.md` from disk/zip/URL, OpenClaw-compatible formats; premium packs as vertical add-ons
- **RAG knowledge base** — Multi-strategy chunking, multi-provider embeddings, hybrid retrieval (vector + BM25 + RRF), rerank, query rewriting, parent-child context
- **Workflow orchestration (Beta)** — React Flow DAG editor, linear or graph execution, merge/condition/approval nodes, built-in report templates, manual/schedule/channel triggers
- **Embeddable Widget** — One `<script>` tag for branded vertical RAG chat on any website
- **Multi-tenant** — Independent channel configs with isolated AI, skills, and knowledge bases
- **Vertical channels** — One-click domain templates: model, prompt, KB, rerank, skills, widget theme
- **Multi-channel** — Web Widget, REST, WebSocket, WeChat (DingTalk/WhatsApp/Telegram [planned](docs/roadmap.en.md#3-channels))
- **Speech input** — OpenAI Whisper (optional local models)
- **Security** — JWT, API keys, RBAC
- **Docker** — `docker compose up -d` full stack

## Quick start

### Docker (recommended)
```bash
git clone https://github.com/windinwing/mchat.git
cd mchat

docker compose -f ops/docker/docker-compose.lite.yml up -d

# Admin UI:  http://localhost:5173
# API docs:  http://localhost:3001/docs
# Landing:   http://localhost:5173/
```

**Default admin credentials** (created on first startup): `admin` / `admin123`  
Change the password under **Admin → Users** after sign-in. Override via `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`. Set `SHOW_BOOTSTRAP_CREDENTIALS=false` to hide the hint on the login page in production.

### Embed the Widget

```html
<script
  src="http://localhost:5173/widget-loader.js"
  data-mchat-url="http://localhost:3001"
  data-agent-id="YOUR_AGENT_ID"
  data-primary-color="#3b82f6"
  data-welcome-message="Hello! How can I help you?"
  data-bot-name="Assistant"
></script>
```

### Local development

```bash
make install   # install dependencies
make dev       # start backend + frontend

# Backend:  http://localhost:3001  (/docs for Swagger)
# Frontend: http://localhost:5173
```
```bash
make test      # run tests
make lint      # lint
mchat run      # start via CLI
```

## Project structure

```raw
mchat/
├── src/
│   ├── backend/          # FastAPI (Python 3.12+)
│   │   └── app/
│   │       ├── api/      # REST routes
│   │       ├── bot/      # Bot engine + LLM providers
│   │       ├── knowledge/# RAG + Milvus
│   │       ├── skill/    # Skill system
│   │       ├── worker/   # Schedules & workflow jobs
│   │       └── channels/ # WeChat & channel adapters
│   └── frontend/         # React + Vite + Tailwind
│       └── src/
│           ├── i18n/     # zh / en (react-i18next)
│           └── pages/    # Landing + admin console
├── skills/               # Skill packages
├── channel_templates/    # Vertical channel templates (patent, medical, etc.)
├── docs/                 # Architecture, API, deployment, roadmap
├── ops/docker/           # Docker Compose
└── Makefile
```

## Supported LLM providers

| Provider | Default API base | Notes |
|----------|------------------|-------|
| `openai` | https://api.openai.com/v1 | GPT-4o, o1, etc. |
| `anthropic` | https://api.anthropic.com | Claude |
| `google` | https://generativelanguage.googleapis.com | Gemini |
| `deepseek` | https://api.deepseek.com | OpenAI-compatible |
| `ollama` | http://localhost:11434/v1 | Local models |
| `groq` | https://api.groq.com/openai/v1 | Fast inference |
| `zhipu` / `moonshot` / `siliconflow` / `together` | *(configure `api_base`)* | Regional / hosted APIs |
| `openai-compatible` | *(configure `api_base`)* | Any OpenAI-compatible endpoint |

## API overview

| Group | Path | Description |
|-------|------|-------------|
| Chat | `/api/chat/*` | Conversations and messages |
| Agents | `/api/agents/*` | AI configuration |
| Knowledge | `/api/knowledge/*` | Documents and retrieval |
| Widget | `/api/widget/*` | Embedded chat API |
| Skills | `/api/skills/*` | Skill management |
| Workflows | `/api/workflows/*` | Workflow CRUD, runs, templates (Beta) |
| Channels | `/api/channels/*` | WeChat and other channels |
| Channel Templates | `/api/channels/templates/*` | One-click vertical channel creation |
| Speech | `/api/speech/*` | Voice transcription |
| Auth | `/api/auth/*` | Login / JWT |
| WebSocket | `/ws` | Real-time streaming |
| Health | `/api/health` | Service status |

See [docs/api.md](docs/api.md) or `/docs` (Swagger) after startup.

## Internationalization

The admin console and landing page support **English** and **简体中文**. Language preference is stored in `localStorage` (`mchat_lang`). Switch language from the header or sidebar.

## CLI

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
## Skill compatibility

- Supports standard frontmatter `SKILL.md` skill packages
- Supports OpenClaw-style `SKILL.md` locale blocks (auto `config.i18n` for UI display names)
- Admin can install skills by zip upload or URL (`/api/skills/install-url`)
- CLI supports direct URL or ClawHub name install, for example: `mchat skill install patent-search`
- **Premium skill packs**: Vertical channels can bundle specialized skills as value-added services
- **Workflow reuse**: One skill (e.g. `patent-search`) can appear in multiple DAG nodes with different `command` / `dimension` payloads

## Docker variants

| File | Services | Use case |
|------|----------|----------|
| `docker-compose.lite.yml` | MySQL + Backend + Frontend | Dev / lightweight |
| `docker-compose.yml` | + Milvus, etcd, MinIO, Redis | Full RAG |
| `docker-compose.prod.yml` | + Nginx HTTPS | Production |
| `docker-compose.dev.yml` | Hot reload | Local dev |

## Tech stack

**Backend:** FastAPI, SQLAlchemy 2.0, Milvus, OpenAI / Anthropic SDKs, JWT, Loguru  

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4, Zustand, react-i18next, React Flow

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) if present.
