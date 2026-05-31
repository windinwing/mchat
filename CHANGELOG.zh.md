# 更新日志

mchat 的所有重要变更都会记录在这个文件中。

## [Unreleased] - 2026-05-30

### 新增
- **Workflow 图编排增强（Beta）**：merge 节点、专利多维分析中英文内置模板、按 UI 语言筛选模板 API。
- **画布工具**：ComfyUI 风格 `V` 指针 / `H` 拖拽平移切换，工具栏快捷按钮。
- **技能 i18n**：`config.i18n` / OpenClaw locales 解析，工作流左栏与节点按系统语言显示技能名。
- **图编辑器 UX**：技能左栏拖拽上画布、节点/连线右键菜单、参数映射器（PayloadMapper）、未安装技能 ⚠ 提示。
- **落地页展示**：新增「界面预览」区块，含 Workflow 列表与图编辑器中英文截图。
- **文档**：README / 产品导览 / 路线图对齐 Workflow；新增 4 张工作流展示图。

### 变更
- 中文专利报表模板改为复用 `patent-search`（`analysis` / `export_analysis`）；英文模板为演示占位技能名。
- 移除工作流页「编辑步骤 JSON」入口，统一以图编排为主。
- `README.en.md` / `README.zh-CN.md` 指向主 README，避免多份文档漂移。

### 测试
- 新增 `tests/unit/test_workflow_graph.py`（模板列表、参数渲染、路径解析）。

## [1.0.0] - 2026-05-17

### 新增
- **核心聊天平台**：支持 WebSocket 实时流式输出的多租户 AI 对话平台。
- **Bot 引擎**：支持工具调用的模块化消息处理链路。
- **大模型提供商**：支持 OpenAI、Anthropic、Google Gemini、DeepSeek、Ollama、Groq 和 OpenAI 兼容接口。
- **技能系统**：基于文件的技能插件，支持热重载。
- **知识库**：集成 Milvus 的 RAG（检索增强生成）能力。
- **管理后台**：基于 React + Tailwind CSS 的后台，用于管理 AI 配置、对话、技能和知识库。
- **嵌入式 Widget**：轻量级网站聊天组件（小于 50KB）。
- **多租户**：每个客服 Agent 拥有独立的 AI 配置。
- **WebSocket**：基于 JWT 认证的实时双向通信。
- **Docker 部署**：一条 Docker Compose 命令即可启动 MySQL + Milvus + Backend + Frontend。
- **CLI**：项目管理命令行工具（`mchat init`、`mchat run`、`mchat skill create`）。
- **限流**：可选的令牌桶限流中间件。
- **API 文档**：`/docs` 自动生成 Swagger UI。
- **CI/CD**：GitHub Actions 自动化测试和 Docker 构建工作流。
- **测试**：基于 pytest 的后端测试集。
