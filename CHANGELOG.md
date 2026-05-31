# Changelog

All notable changes to mchat will be documented in this file.

## [Unreleased] - 2026-05-30

### Added
- **Workflow graph enhancements (Beta)**: merge node, patent multi-dimension report templates (zh/en), locale-filtered template API.
- **Canvas tools**: ComfyUI-style `V` pointer / `H` pan mode with toolbar toggles.
- **Skill i18n**: `config.i18n` and OpenClaw locale parsing; workflow palette and nodes show localized skill titles.
- **Graph editor UX**: drag skills from palette, node/edge context menus, PayloadMapper, missing-skill warnings.
- **Landing preview**: new screenshot section including Workflow list and graph editor (en/zh).
- **Docs**: README, product tour, and roadmap aligned with Workflow; four workflow showcase images.

### Changed
- Chinese patent report template reuses `patent-search` commands; English template uses placeholder skill names for demos.
- Removed linear steps JSON editor from workflows page; graph editor is primary.
- `README.en.md` / `README.zh-CN.md` point to canonical README files.

### Tests
- Added `tests/unit/test_workflow_graph.py` (templates, payload rendering, path resolution).

## [1.0.0] - 2026-05-17

### Added
- **Core Chat Platform**: Multi-tenant AI chat with real-time streaming via WebSocket
- **Bot Engine**: Modular message processing pipeline with tool calling
- **LLM Providers**: OpenAI, Anthropic, Google Gemini, DeepSeek, Ollama, Groq, and OpenAI-compatible providers
- **Skill System**: File-based skill plugins with hot-reload support
- **Knowledge Base**: Milvus vector store integration for RAG (Retrieval-Augmented Generation)
- **Admin Dashboard**: React + Tailwind CSS admin panel for managing AI configs, conversations, skills, and knowledge bases
- **Embedded Widget**: Lightweight JavaScript chat widget for website embedding (< 50KB)
- **Multi-tenant**: Independent AI configurations per customer service agent
- **WebSocket**: Real-time bidirectional communication with JWT authentication
- **Docker Deployment**: One-command Docker Compose setup (MySQL + Milvus + Backend + Frontend)
- **CLI**: Command-line interface for project management (`mchat init`, `mchat run`, `mchat skill create`)
- **Rate Limiting**: Optional token bucket rate limiter middleware
- **API Documentation**: Auto-generated Swagger UI at `/docs`
- **CI/CD**: GitHub Actions workflow for automated testing and Docker builds
- **Tests**: Backend test suite with pytest
