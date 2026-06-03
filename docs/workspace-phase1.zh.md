# Phase 1：主控制面 + 用户执行面

> 本文档区分 **目标状态** 与 **当前实现差距**，避免与 `docs/workspace.zh.md` 运维说明混淆。

## 1. 背景与目标

MChat 需要租户级 Skill 执行隔离与可回收 sidecar，以支持后续写代码、文件操作、磁盘配额，而 **不是** 为每个用户部署一整套独立 mchat 栈（DB、webhook、工作流全部复制）。

**目标**

- 主后端保持 **控制面**：认证、频道、工作流、DB、对象存储代理
- 每 **平台用户**（`user_id`）一个 **执行面 sidecar**，只暴露该用户的 `skills/`、`uploads/`、`data/`
- 持久化落在宿主机租户目录 + 对象存储，容器可删可重建

**依据**：`app/main.py`（API/WebSocket 注册）、`app/workspace/runner.py`（Phase 2 占位）

## 2. 范围

### Phase 1 包含

| 项 | 说明 |
|----|------|
| 租户工作区目录 | `{WORKSPACE_ROOT}/{user_id}/skills|uploads|data` |
| 每用户 sidecar | Docker `sleep infinity` + 分目录 mount |
| 安全运行参数 | `cap-drop=ALL`、`no-new-privileges`、可选 network/memory/cpus |
| 执行上下文 | `workspace_execution_scope` + env 注入 |
| 可观测性 | `GET /api/workspace/status` |
| 用户 Skill 磁盘根 | 用户 CRUD 写入租户 `skills/` |
| 平台 Skill 同步 | 执行前复制到租户 `skills/`（只读来源仍在全局目录） |
| 容器内执行（最小） | `docker exec` + 租户内 `run_skill.py` 入口 |

### Phase 1 不包含

- 每 **频道** 独立容器
- 独立 **runner** 服务（Phase 2）
- 文件系统级 **硬 quota**
- 主后端进程下沉到 sidecar

**依据**：`app/workspace/security.py`、`app/workspace/runner.py`

## 3. 当前实现基线

### 控制面（主后端）

仍承载：登录、权限、REST/WebSocket、频道 webhook、工作流编排、数据库、Milvus/RAG、上传代理。

**依据**：`app/main.py:261-276`

### 执行面（workspace 模块）

| 模块 | 职责 |
|------|------|
| `resolver.py` | 解析 mode、执行用户、容器名 |
| `paths.py` | 租户路径；studio 不在 sidecar mount 内 |
| `local.py` / `container.py` | ensure sidecar、execution env |
| `security.py` | docker run 硬约束 |
| `skill_sync.py` | 平台 Skill → 租户 skills |
| `skill_runner.py` | 容器/本地统一脚本入口 |

### 执行用户

优先 `customer_config.user_id`（频道 owner），**不使用** Portal 访客身份。

**依据**：`app/bot/engine.py`、`app/workspace/resolver.py` `workspace_user_id_for_execution`

## 4. 目标架构

```
┌──────────────── 控制面（主后端） ────────────────┐
│ Auth · Channel/Webhook · Workflow · DB · RAG     │
│ Upload/S3 代理 · Studio 记忆（Markdown）          │
└───────────────────────┬──────────────────────────┘
                        │ ensure sidecar + sync skills
                        ▼
┌──────────────── 执行面（每 user_id 一 sidecar）─┐
│ /workspace/skills · uploads · data               │
└──────────────────────────────────────────────────┘
```

## 5. 工作区模型

- 根目录：`settings.workspace_root_dir`（默认 `../../data/tenants`）
- **Execution 目录**（sidecar 可见）：`skills/`、`uploads/`、`data/`
- **Studio**：`{tenant}/studio/{channel_id}/`，控制面读写，**不 mount 进 sidecar**

**依据**：`app/workspace/paths.py`、`app/workspace/types.py`

## 6. 容器模型

- 每用户一个 sidecar，名前缀 `mchat-ws`，后缀为 **裁剪后** 用户 id（非完整 UUID）
- 创建：`docker run -d … sleep infinity`；running 则复用，否则 `rm` 后重建
- 禁止：Docker socket、privileged、**非租户 execution 目录**的宿主机 bind mount

**依据**：`app/core/config.py`、`app/workspace/resolver.py`、`app/workspace/container.py`、`app/workspace/security.py`

## 7. 持久化与可恢复性

- 不依赖容器可写层
- 数据在宿主机 `{tenant}/` 与 S3/MinIO；sidecar 可随时删除重建

## 8. 平台 Skill vs 用户 Skill

| 类型 | 磁盘位置 | 执行策略 |
|------|----------|----------|
| 平台内置 / 全局 pack | `SKILLS_DIR`、extra roots | 执行前 **同步** 到租户 `skills/`（容器模式必须） |
| 用户自建 / 上传 | 租户 `skills/` | 直接执行 |
| server_ops / notification | 全局，受 ops_policy 控制 | **不同步**；仅控制面 local 执行 |

**依据**：`app/skill/loader.py`（tenant root 优先扫描）、`app/workspace/skill_sync.py`

## 9. Sidecar 内脚本入口规范

- 入口文件：`main.py` 或 `tool.py`（与现执行器一致）
- 优先 `run(**kwargs)`；其次带参 `main(**kwargs)`；无参 `main()` 走 namespace 分发
- 容器模式：stdout 为 JSON（由 `data/.mchat/run_skill.py` 输出）

## 10. 当前差距（随实现更新）

| 差距 | 状态 |
|------|------|
| 主进程 importlib 执行 | 容器模式已走 `docker exec`；local fallback 仍 importlib |
| 用户 Skill 全局目录 | 已切租户 `skills/`（CRUD + reload） |
| 平台 Skill 同步 | 已实现 `ensure_skill_in_tenant` |
| `max_disk_bytes` enforcement | 软拦截（写入前检查）；无 FS quota |
| `usage_storage_bytes` 回写 | 已实现租户目录统计 API |

## 11. Phase 2 方向

独立 `mchat-runner`：signed job、无 auth/webhook/DB；sidecar 不膨胀为完整应用栈。

**依据**：`app/workspace/runner.py`

## 12. Sidecar 生命周期（Phase 1 最小策略）

| 事件 | 行为 |
|------|------|
| 首次执行 / status 探测 | `ensure_ready` → 不存在或非 running 则 `docker run` |
| 复用 | `inspect.State.Running == true` 则跳过创建 |
| 镜像升级 | 手动 `docker rm -f mchat-ws-*` 后下次自动重建（文档化，无自动 rolling） |
| 清理 | 无 idle TTL；Phase 2 可考虑 runner 池回收 |

## 13. 开关与回退

- 默认 `WORKSPACE_CONTAINER_ENABLED=false`
- Pro/Enterprise + 开关开启 → container；Docker 不可用 → `effective_mode=local` + `fallback_reason`
- 启用条件见 `docs/workspace.zh.md`
