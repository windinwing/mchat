# mchat
MChat is a lightweight, embeddable, multi-tenant AI customer service platform. It integrates a powerful Bot Engine, RAG knowledge base, Skill plugin system, and an embedded chat Widget — with support for 10+ LLM providers and multi-channel connectivity (Web Widget, WebSocket, REST API, and extensible channel adapters for messaging apps).

## Key Features
- 🤖 Multi-LLM Support — OpenAI, Anthropic, Google, DeepSeek, Ollama, Groq, Zhipu, Moonshot, SiliconFlow, Together, and any OpenAI-compatible provider
- 🧠 RAG Knowledge Base — Document import (PDF/DOCX/TXT/MD/URL) → chunking → Milvus vector search → context injection
- 🔌 Skill Plugin System — Hot-reloadable plugins with SKILL.md manifest; supports Python scripts, webhooks, and shell commands
- 💬 Embedded Widget — One-line `<script>` tag with domain whitelisting, customizable themes, and SSE streaming
- 🔗 Multi-Channel — WebSocket for admin chat, SSE for widget, REST API, with extensible channel architecture for WeChat, Telegram, Slack, etc.
- 👥 Multi-Tenancy — Each tenant has independent AI config, KBs, skills, theme, and domain settings
- ⚡ Streaming — Real-time token-by-token AI response via WebSocket or SSE
- 🐳 Easy Deployment — Docker Compose (lite/full/dev/prod), CLI tool, Makefile
- 🔐 Auth & Security — JWT with role-based access (admin/agent), rate limiting, CORS

## Tech Stack
Python 3.12+ / FastAPI / SQLAlchemy 2.0 / MySQL 8.0 / Milvus 2.5 / Redis / React 19 / TypeScript 5.8 / Tailwind CSS 4 / Zustand
