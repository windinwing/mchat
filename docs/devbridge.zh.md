# DevBridge 桥接开发

DevBridge 让群组对话中的 AI 通过**受控工具**读写服务器上的项目目录（GameCenter / Cocos、Web 前端、Node 模板等），而不是裸跑 shell。

## 架构

| 层 | 说明 |
|----|------|
| **Provider** | `gamecenter`（内置）+ Admin 自定义 provider |
| **Bot 工具** | `gamecenter_*` / `devbridge_*` / `git_*`（群组内） |
| **Prompt Skill** | `gamecenter-dev-agent`、`dev-assistant` 等，教 LLM 正确调工具 |
| **Admin UI** | `/admin/devbridge` 浏览/改码/构建/发布 |

改代码能力在 **Bot 内置工具**；Skill 是 prompt 引导，不是 handler。

## 快速启用

### 1. 环境变量（`src/backend/.env`）

```bash
GAMECENTER_BRIDGE_ENABLED=true
GAMECENTER_SOURCE_ROOT=/path/to/game/projects
GAMECENTER_BRIDGE_WRITE_ENABLED=true          # 允许 patch/build
GAMECENTER_BUILD_COMMAND=bash ops/scripts/gamecenter-bridge-build.sh {project_dir}
GAMECENTER_BRIDGE_GROUP_SCOPE_ONLY=true       # 仅群组对话暴露工具
```

构建队列：`GAMECENTER_BUILD_QUEUE_ENABLED=true` 并运行 `ops/scripts/gamecenter-build-worker.py`。

### 2. 开发 Skill（已随仓库提供）

```bash
# skills/ 下已有：
#   gamecenter-dev-agent  — Cocos/GameCenter
#   dev-assistant         — 通用 DevBridge 工作流
#   git-commit-writer     — 提交说明
#   code-reviewer         — patch 后审查清单
```

Admin → **技能** → 刷新 → 启用 → 群组 **default_skill_ids** 勾选。

或：

```bash
python ops/scripts/seed-gamecenter-group.py --user admin --group "开发组" --projects "your-slug"
```

### 3. 群组白名单

群组设置 → **DevBridge 项目白名单**（按 provider 限制 slug）。Bot 会自动应用白名单。

## 推荐工作流

**GameCenter：** list → read → patch(old_text+new_text) → build → get_gamecenter_build_progress

**通用：** search → read → patch → diff → build → git_commit

## 权限

| 角色 | 读 | 写/构建/发布 |
|------|----|--------------|
| 群 member | ✅ | ❌ |
| 群 owner/editor | ✅ | ✅ |
| 平台 admin/agent | ✅ | ✅ |

## 多 Provider

- REST：`/api/devbridge/providers/{key}/...`
- 聊天：`devbridge_*` 工具传 `provider`（默认 `gamecenter`）
- `list_devbridge_projects` 聚合所有已启用 provider

自定义 provider 在 Admin → DevBridge → 设置 中配置。

## 与 mchat-ops 区别

| | DevBridge | mchat-ops |
|--|-----------|-----------|
| 用途 | 改项目代码、编译、发布 | 服务器 health/logs/db |
| 场景 | 群组 + 项目白名单 | 运维 allowlist |

**禁止**用 mchat-ops 执行 `list_gamecenter_projects`。

## 相关文档

- [GameCenter 代理接入](gamecenter-agent-integration.zh.md)
- [本地/远程构建](gamecenter-local-build-guide.zh.md)
- [构建队列](gamecenter-build-queue.zh.md)
