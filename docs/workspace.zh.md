# Tenant Workspace — 控制面 + 执行面（Phase 1 / Phase 2）

## 结论（与当前代码对齐）

| 方向 | 可行性 | 建议 |
|------|--------|------|
| **用户级 Skill + 工作区 sidecar** | 高 | **Phase 1 做**；现有 `app/workspace/` 为地基，需补齐容器内 Skill 执行 |
| **每频道独立容器** | 中、复杂度高 | **不做**；频道是控制面路由单元，不是执行隔离单元 |
| **每用户完整独立栈** | 低、运维重 | **不做**；采用「主控制面 + 用户执行面」 |

## Phase 1 — 现在

### 控制面（主后端，始终）

主进程负责，**不进租户容器**：

- 登录 / 权限 / 多租户
- 频道 webhook、会话、工作流编排
- 数据库、Redis、Milvus/RAG 索引
- 上传与知识库元数据（租户目录 + 对象存储 S3/MinIO）

持久化**不依赖** sidecar 容器文件系统；容器重启后数据仍在宿主机租户目录 / 对象存储中。

### 执行面（每平台用户一个 sidecar）

- 粒度：**平台账号 `user_id`**（频道 owner），不是 Portal 访客
- 目录（宿主机 `{WORKSPACE_ROOT}/{user_id}/`）：
  - `skills/` — 用户级 Skill 包
  - `uploads/` — 租户上传（`MCHAT_UPLOAD_DIR`）
  - `data/` — 其它执行数据
- **不挂载** `studio/`（Cloud Studio 记忆由控制面读写，OpenClaw 风格 Markdown）
- Docker 不可用时自动降级为 local（同目录、主进程执行）

### 安全边界（强制）

控制面通过**宿主机 Docker CLI** 管理 sidecar；sidecar 内：

| 禁止 | 说明 |
|------|------|
| Docker socket | 不能 `--volume /var/run/docker.sock` |
| privileged | 不能 `--privileged` |
| 宿主机目录 | 不能 bind mount `/`、`/etc`、平台 `skills/` 等 |
| 任意 extra mount | 仅 `skills`、`uploads`、`data` 三个子目录 |

实现见 `app/workspace/security.py`：`cap-drop=ALL`、`no-new-privileges`、可选 `pids-limit` / `memory` / `cpus`。

### 当前半成品（待补）

1. **容器内 Skill 执行**：仍用主进程 `importlib` + 租户 env；sidecar 已就绪，下一步通过 `docker exec` 或 sidecar HTTP 跑 `/workspace/skills` 内脚本
2. **用户 Skill 同步**：平台 Skill 安装/更新时同步到 `{tenant}/skills/`
3. **配额**：`max_disk_bytes` 已建模，宿主机 enforcement 待做

## Phase 2 — 以后（可选）

若需要更强「写代码、长任务、严格磁盘配额」：

- 单独 **`mchat-runner`** 服务（见 `app/workspace/runner.py` 占位）
- 控制面发签名 Run 请求；runner **不**承载 auth / webhook / DB
- **不要**把主后端逻辑继续塞进租户容器

## 配置

```env
WORKSPACE_ROOT_DIR=../../data/tenants
WORKSPACE_DEFAULT_MODE=local
WORKSPACE_CONTAINER_ENABLED=false
WORKSPACE_CONTAINER_IMAGE=python:3.12-slim
# WORKSPACE_CONTAINER_NETWORK=none
# WORKSPACE_CONTAINER_MEMORY=512m
# WORKSPACE_CONTAINER_CPUS=1.0
```

## API

`GET /api/workspace/status?customer_id=` — mode、limits、tenant 路径、execution env。

## 分支

- **`dev`**：Core，`app/workspace/` 完整可用
- **`feature/channel-rental`**：Cloud Studio 走 `resolve_studio_path()`，与控制面 tenant 目录共存
