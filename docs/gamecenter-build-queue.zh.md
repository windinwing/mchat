# GameCenter 编译队列 — 配置与运维手册

> 适用：**MChat Cloud 服务器**（如 `10.98.8.15`）上 DevBridge / 群组 Agent 触发的 GameCenter 远程编译。  
> 目标：编译与 **API 进程解耦**；**5 槽并发**；某一任务卡住不拖死整站与其它编译。

---

## 1. 架构一览

```text
群组 patch / build 工具
    → API：build_project() 写 metadata（status=queued）
    → Redis LPUSH  mchat:build:queue
    → API 立即返回（毫秒级，不阻塞聊天/短信登录）

mchat-build-worker.service（独立进程）
    → 5 个 worker 槽（线程），各自 BRPOP 同一队列
    → 每槽执行：bash gamecenter-remote-pipeline-build.sh {slug}
        → SSH 到 Windows/Mac 编译机
        → gamecenter-local-pipeline.sh 拉源码 → Cocos 编 → 推回 build/web-mobile
    → 更新 metadata（running → built / failed）
    → 试玩：http://10.98.8.15:5099/<slug>/ 、https://xyx.9235.net/<slug>/
```

| 组件 | 路径 / 服务 |
|------|-------------|
| API 后端 | `mchat-cloud-backend.service`（uvicorn `:3001`） |
| 编译 worker | `mchat-build-worker.service` |
| 队列脚本 | `ops/scripts/gamecenter-build-worker.py` |
| 远程编译入口 | `ops/scripts/gamecenter-remote-pipeline-build.sh` |
| 构建记录 | `data/devbridge/gamecenter/<slug>/builds/<build_id>/` |
| Redis 队列键 | `mchat:build:queue` |

---

## 2. 服务器 `.env` 配置

文件：`/opt/xiaoxiao/mchat/.env`（修改后需重启对应 systemd 服务）

### 2.1 队列与 worker 池

| 变量 | 默认 | 说明 |
|------|------|------|
| `REDIS_URL` | — | OTP/队列共用，例：`redis://10.98.8.12:6379/0` |
| `GAMECENTER_BUILD_QUEUE_ENABLED` | `true` | `false` 时改回 **API 进程内同步编译**（不推荐，会阻塞接口） |
| `GAMECENTER_BUILD_WORKER_POOL_SIZE` | `5` | worker 进程内并发槽位数（1–32） |

```bash
GAMECENTER_BUILD_QUEUE_ENABLED=true
GAMECENTER_BUILD_WORKER_POOL_SIZE=5
```

改池大小后：

```bash
systemctl --user restart mchat-build-worker.service
```

### 2.2 远程编译机（SSH）

| 变量 | 示例 | 说明 |
|------|------|------|
| `GAMECENTER_BUILD_SSH_HOST` | `10.98.8.186` | Windows / Mac mini 编译机 IP |
| `GAMECENTER_BUILD_SSH_USER` | `administrator` | 编译机 SSH 用户 |
| `GAMECENTER_BUILD_PIPELINE_SCRIPT` | `/c/Users/.../gamecenter-local-pipeline.sh` | **编译机上** pipeline 路径 |
| `GAMECENTER_BUILD_SSH_IDENTITY` | `~/.ssh/id_gamecenter_build` | 服务器 → 编译机私钥 |
| `GAMECENTER_DEPLOY_HOST` | `10.98.8.15` | pipeline 回推目标 |

### 2.2.1 Windows Cocos 2.x：HTTP Agent + SwiftShader（推荐）

经典 **Windows 服务**跑在 Session 0，**不能**用来直接调 Cocos 2.4.x。

做法：在 **用户已登录的桌面会话**里跑 HTTP Agent（登录时计划任务自启，无需每次 RDP），同时 2.x 的 `gamecenter-local-build-project.sh` 已内置 `--use-gl=swiftshader --ignore-gpu-blocklist --disable-gpu-sandbox` 标志，用 CPU 模拟 WebGL 绕过 GPU/D3D 依赖。

> 详细部署与 Cocos 2.x 适配说明：`docs/gamecenter-windows-build-agent.zh.md`

```text
10.98.8.15 worker
  → 检测到 2.x 且配置了 GAMECENTER_BUILD_AGENT_URL
  → HTTP POST http://10.98.8.186:19280/v1/build
Windows Agent（登录会话）
  → gamecenter-local-pipeline.sh → Cocos 2.4.15 → rsync 回 15
```

**Windows 编译机一次性安装（管理员 PowerShell）：**

```powershell
cd C:\Users\Administrator\dev\mchat\ops\scripts
Set-ExecutionPolicy Bypass -Scope Process -Force
.\gamecenter-windows-build-agent-setup.ps1
```

**15 上 `.env` 追加（token 与 `gamecenter-windows-agent.json` 一致）：**

```bash
GAMECENTER_BUILD_AGENT_URL=http://10.98.8.186:19280
GAMECENTER_BUILD_AGENT_TOKEN=<setup 脚本输出的 token>
```

| 变量 | 说明 |
|------|------|
| `GAMECENTER_BUILD_AGENT_URL` | Windows Agent 基址；**仅 2.x** 走 HTTP，3.8.x 仍 SSH |
| `GAMECENTER_BUILD_AGENT_TOKEN` | Bearer 令牌，防火墙建议只放行 15 → 19280 |

健康检查：`curl http://10.98.8.186:19280/v1/health -H "Authorization: Bearer <token>"`

**Watchdog（每 5 分钟）**：`gamecenter-windows-build-agent-watchdog.ps1` 由计划任务 `GameCenterBuildAgentWatchdog` 执行；Agent 崩溃后自动拉起，无需重新登录。日志：`%USERPROFILE%\dev\gamecenter-agent\watchdog.log`

### 2.3 构建命令（DevBridge 也会读）

| 变量 | 推荐值 |
|------|--------|
| `GAMECENTER_BUILD_COMMAND` | `bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug} {build_id}` |
| `GAMECENTER_AUTO_BUILD_AFTER_PATCH` | `true` |
| `GAMECENTER_BUILD_TIMEOUT_SECONDS` | `1800`（单任务最长秒数，worker 内 subprocess 超时） |

### 2.4 源码根目录（Agent patch 扫描）

| 变量 | 说明 |
|------|------|
| `GAMECENTER_SOURCE_ROOT` | 例：`/opt/xiaoxiao/gamecenter/src`（支持 `src/<分类>/<slug>/` 分层发现） |
| `GAMECENTER_EXTRA_SOURCE_ROOTS` | 通常留空（改造后仅用 `src` 单根） |

---

## 3. DevBridge 管理端

路径：MChat 管理后台 → DevBridge / GameCenter 设置

| 配置项 | 推荐 |
|--------|------|
| 构建命令 | `bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}` |
| 改代码后自动编译 | ✅ 开启 |
| `build_timeout_seconds` | `1800` 或更大（2.x 首次编译慢） |
| 试玩基址 | `http://10.98.8.15:5099`、`https://xyx.9235.net` |

---

## 4. 服务安装与启停

### 4.1 首次安装 worker（服务器上 xiaoxiao 用户）

```bash
mkdir -p ~/.config/systemd/user
cp /opt/xiaoxiao/mchat/ops/deploy/mchat-build-worker.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mchat-build-worker.service
```

### 4.2 常用命令

```bash
# 状态
systemctl --user status mchat-cloud-backend.service
systemctl --user status mchat-build-worker.service

# 重启（改 .env 或脚本后）
systemctl --user restart mchat-build-worker.service
systemctl --user restart mchat-cloud-backend.service

# 日志
journalctl --user -u mchat-build-worker.service -f
journalctl --user -u mchat-cloud-backend.service -f
```

启动成功日志应包含：

```text
Build worker pool started (size=5)
Build worker slot 1 started
…
Build worker slot 5 started
```

---

## 5. 日常操作

### 5.1 手动触发编译（与 Agent 相同）

```bash
bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh <slug>
```

### 5.2 查看队列深度

```bash
redis-cli -h 10.98.8.12 LLEN mchat:build:queue
```

### 5.3 查看某次构建状态与日志

```bash
SLUG=pkg0215-creator
ls -lt /opt/xiaoxiao/mchat/data/devbridge/gamecenter/$SLUG/builds/ | head

BUILD_ID=<最新目录名>
cat /opt/xiaoxiao/mchat/data/devbridge/gamecenter/$SLUG/builds/$BUILD_ID/metadata.json
tail -100 /opt/xiaoxiao/mchat/data/devbridge/gamecenter/$SLUG/builds/$BUILD_ID/stdout.log
tail -50  /opt/xiaoxiao/mchat/data/devbridge/gamecenter/$SLUG/builds/$BUILD_ID/stderr.log
```

`metadata.json` 中 `status` 含义：

| status | 含义 |
|--------|------|
| `queued` | 已入队，等待空闲槽 |
| `running` | 某槽正在执行（含 SSH + Cocos） |
| `built` | 成功 |
| `failed` | 失败（看 stderr / returncode） |

### 5.4 聊天里查进度

对 Agent 说「查一下 xxx 编译进度」，或工具：`get_gamecenter_build_progress(slug)`。

---

## 6. 杀进程 / 停任务 / 清队列

> **说明**：5 个「槽」是 **同一 worker 进程里的 5 条线程**，不能单独 kill「第 3 号线程」而不影响其它槽；运维上按 **任务子进程** 或 **整个 worker 服务** 处理。

### 6.1 杀掉卡住的远程编译（推荐，不动 API）

编译链：`worker` → `bash gamecenter-remote-pipeline-build.sh` → `ssh` → Windows `gamecenter-local-pipeline.sh` → `CocosCreator`

```bash
# 在 10.98.8.15 上：结束本机侧的 pipeline / ssh（正在占用的槽会失败并标 failed）
pkill -f "gamecenter-remote-pipeline-build.sh"
pkill -f "gamecenter-local-pipeline.sh"

# 若仍挂着，看 PID 后精确杀
pgrep -af "gamecenter-remote-pipeline-build"
kill -9 <pid>
```

在 **Windows 编译机**上结束 Cocos（需 RDP 或 SSH 到 10.98.8.186）：

```powershell
taskkill /F /IM CocosCreator.exe
```

### 6.2 重启整个 worker 池（5 槽全部重建）

```bash
systemctl --user restart mchat-build-worker.service
```

正在跑的 subprocess 可能被中断；对应 `metadata` 可能停在 `running`，需人工标记或重新触发 build。

### 6.3 停止 worker（不再消费队列，API 仍可入队）

```bash
systemctl --user stop mchat-build-worker.service
```

恢复：

```bash
systemctl --user start mchat-build-worker.service
```

### 6.4 清空 Redis 队列（慎用）

仅当确认 **不想执行** 队列里尚未开始的任务：

```bash
redis-cli -h 10.98.8.12 DEL mchat:build:queue
```

已在 `running` 的任务不受影响（已从队列弹出）。

### 6.5 禁止 API 被编译拖死（历史问题）

若未开队列、或 worker 全停，**切勿**在 API 进程里长时间跑 `gamecenter-remote-pipeline-build.sh`。  
确认：

```bash
grep GAMECENTER_BUILD_QUEUE_ENABLED /opt/xiaoxiao/mchat/.env
# 应为 true，且 mchat-build-worker 为 active
```

---

## 7. 调池大小与性能

| 场景 | 建议 |
|------|------|
| 编译机只有 1 台 Windows | `POOL_SIZE=2~3`，避免 Cocos 同时开太多 GUI |
| 有 Mac mini 专跑 3.x + Windows 跑 2.x | 可保持 `5`，注意编译机 CPU/内存 |
| 某 slug 经常卡几小时 | 先 `pkill` pipeline + `taskkill Cocos`；槽释放后其它任务继续 |

改大池：**不会**让同一 slug 更快，只是 **更多 slug 可并行**。

---

## 8. 故障排查速查

| 现象 | 排查 |
|------|------|
| 短信/登录/聊天卡住 | API 是否在跑同步编译？`pgrep -af gamecenter-remote` 是否挂在 **uvicorn 子进程** 下；应只在 worker 下 |
| patch 后显示「已入队」一直 `queued` | `systemctl --user status mchat-build-worker`；`LLEN mchat:build:queue` |
| 长期 `running` | `stdout.log` 是否增长；Windows Cocos 是否卡；`pkill` + 重启 worker |
| `failed` exit 23 | 远端 resolve 路径错误：确认 `source_root` 指向 `src` 且 `GAMECENTER_WORKSPACE` 指向 xcx，见 `gamecenter-local-build-guide.zh.md` |
| Cocos 2.x 失败 | 检查 `--use-gl=swiftshader` 标志是否生效；确认编译机 `swiftshader/` DLL 存在；详见 `docs/gamecenter-windows-build-agent.zh.md` |
| 试玩不更新 | 强刷；查 `build/web-mobile/index.html` mtime；nginx 缓存 |

---

## 9. 相关文件

| 文件 | 说明 |
|------|------|
| `ops/scripts/gamecenter-build-worker.py` | worker 池主程序 |
| `ops/deploy/mchat-build-worker.service` | systemd 单元 |
| `src/backend/app/services/build_queue_service.py` | Redis 入队/出队 |
| `src/backend/app/services/rooted_project_bridge_service.py` | `build_project` / `run_queued_build` |
| `docs/gamecenter-local-build-guide.zh.md` | 本机/Windows pipeline、路径、Cocos 版本 |
| `docs/gamecenter-agent-integration.zh.md` | Agent 接入设计 |

---

## 10. 变更记录（运维备注）

- **编译队列**：`GAMECENTER_BUILD_QUEUE_ENABLED`，独立 `mchat-build-worker.service`
- **5 槽并发**：`GAMECENTER_BUILD_WORKER_POOL_SIZE=5`，单任务卡住不阻塞其它槽与 API
- **API 阻塞修复**：编译不得再在 `mchat-cloud-backend` 进程内同步 `subprocess` 长跑
