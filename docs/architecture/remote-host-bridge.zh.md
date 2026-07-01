# Server ↔ Client ↔ Server 远程主机桥接架构

> 本文档梳理 MChat 与「其他主机」协作的全部现有机制，提出统一抽象，并给出迁移方向。
> 面向：架构设计、后端开发、运维。
> 最后更新：2026-07-01

---

## 一、为什么需要「连别的机器」

MChat 中心（`mchat-cloud-backend`，一台云服务器）本身受限于：

1. **没有真实身份/指纹**：云服务器 IP 发小红书/抖音会被秒封；Cocos Creator 编译需要 GUI 与 GPU。
2. **没有 GPU/重算力**：图片/视频生成（ComfyUI）跑在本地 Mac mini 才现实。
3. **没有源码树/编译工具链**：游戏源码在开发机 `10.98.8.186`，Cocos 编辑器也在那。
4. **不希望暴露任意 shell**：安全边界要求中心只能做「受控动作」。

于是 mchat 把这些「做不了/不该做」的事，外包给**远程主机**。外包的方式现在有三套，但本质都是同一个模式——

---

## 二、核心模式：Server-Client-Server (S-C-S)

```
        ① 下发任务
   ┌──────────────────┐
   │                  ▼
┌──┴──┐          ┌─────────┐          ┌──────┐
│ S   │          │   C     │          │ 目标  │
│中心 │ ◀─────── │ 客户机  │ ────────▶ │ 系统  │
│     │  ③ 回传   │         │  ② 执行  │      │
└─────┘  结果     └─────────┘          └──────┘
```

- **S（Server/中心）**：决定「做什么」，组装任务、鉴权、记账、对外给用户看进度。
- **C（Client/客户机或代理）**：决定「怎么做」，在远程环境里真正执行，可能再连第三方的「目标系统」。
- **S'（目标系统，可选的第三跳）**：C 的下游——ComfyUI、Cocos Creator、浏览器登录态、社交平台站点。

**S→C→S 的回环**：中心把任务发出去，执行结果/产物再回到中心。这个回环是统一抽象的关键——无论传输方向如何，都收敛到「任务 + 结果」两段式。

> 命名说明：第二个 S 既是「中心的回传」，也可以理解为「目标系统（Social platform / Source repo / Service）」。文档里统一指「结果回流到中心」。

---

## 三、现有三套实现（事实梳理）

### 3.1 DevBridge — 编译/改码（Push：中心→远程机）

**代码**：`app/services/rooted_project_bridge_service.py`、`app/api/devbridge.py`、`ops/scripts/gamecenter-*`

**流向**：中心**主动连**远程机（SSH 或 HTTP），同步等结果。

```
用户在群组/聊天触发工具 (patch/build/publish)
   → 中心 bridge service 直接 subprocess 或 SSH
   → 远程编译机执行 gamecenter-local-pipeline.sh → Cocos 编译
   → 产物 rsync 回中心 → 更新 metadata.json
```

| 维度 | 实现 |
|------|------|
| 方向 | S → C（中心推） |
| 传输 | `subprocess` 调 SSH；或 HTTP POST 到 Windows build agent `/v1/build` |
| 协议载体 | shell 命令 + 文件路径（slug/build_id） |
| 异步 | Redis 队列 `mchat:build:queue` + 独立 `mchat-build-worker.service`（5 槽）|
| 状态 | 文件系统 `data/devbridge/<provider>/<slug>/builds/<build_id>/metadata.json` |
| 远程机要求 | **必须内网可达**（SSH 可登录 / HTTP agent 监听端口）|
| 能力 | read / patch / build / publish / rollback |

**两种 Push 子形态**：

- **SSH pipeline**（Mac/Linux 编译机）：worker `subprocess(["ssh", host, pipeline_script, slug])` 同步等返回。
- **HTTP agent**（Windows 编译机，Session 0 限制）：worker `POST http://host:19280/v1/build`，agent 同步跑完返回。这是 Push 模式里唯一的「HTTP RPC」子类，**但它仍然是 Push 且同步**——agent 不会主动来取任务。

### 3.2 Publisher-Client — 发布/生成（Pull：客户机→中心）

**代码**：`app/publish/client/{protocol,dispatcher}.py`、`app/api/publish.py`、`publisher-client/`

**流向**：客户机**主动来取**任务，做完回传。中心从不连客户机。

```
中心 enqueue_job(PublishJob)         # 内存队列
   ↑（中心 publisher 在 _wait_for_result 轮询 job 状态）
   │
客户机 while True:
   POST /api/publish/jobs/claim       # 拉一个 pending 任务 → claimed
   执行 (Playwright / ComfyUI)
   POST /api/publish/video-upload     # 产物文件回传
   POST /api/publish/jobs/{id}/result # 状态回传 done/failed
```

| 维度 | 实现 |
|------|------|
| 方向 | C → S（客户机拉） |
| 传输 | 纯 HTTP（客户机只出站，无监听端口）|
| 协议载体 | `PublishJob` dataclass（JSON，versioned）|
| 异步 | 客户机自己轮询（`poll.interval_seconds`，默认 15s）|
| 状态 | 进程内存 dict（MVP，重启丢失，TTL 24h GC）|
| 远程机要求 | **只需出站 HTTP**，可穿透 NAT |
| 能力 | publish(text/image/video) / generate(image/video) |

**同一协议承载多类 job**：`PublishJob.platform` 区分——
- `xiaohongshu` / `douyin` / `weibo` → Playwright 发布
- `image:comfyui` / `video:comfyui` → 媒体生成
- `job_type` in `extra` → 进一步区分语义

### 3.3 Windows Build Agent — 编译（Push，但走 HTTP）

其实是 3.1 的一个传输变体，单独列出是因为它代表了「远程机跑一个常驻 HTTP 服务」的形态：

```
中心 worker → POST http://10.98.8.186:19280/v1/build
                {slug, build_id, deploy_host}
              ← 同步返回 {ok, status: built, ...}
```

- agent 在用户已登录的桌面会话里跑（`ThreadingHTTPServer`），有 Bearer token 鉴权
- watchdog 计划任务自动拉起
- **它仍是 Push**：agent 不轮询中心，是中心去连它

---

## 四、三套机制对比

| 维度 | DevBridge (SSH) | DevBridge (HTTP agent) | Publisher-Client |
|------|----------------|----------------------|-----------------|
| **传输方向** | S→C Push | S→C Push | C→S Pull |
| **调用模式** | 同步 RPC | 同步 RPC | 异步队列 |
| **远程机可达性** | SSH 入站 | HTTP 入站 | 仅出站 |
| **协议** | shell 命令 | REST `/v1/build` | `PublishJob` JSON |
| **任务模型** | slug + 文件路径 | slug + build_id | 通用 job dict |
| **状态持久化** | 文件 metadata | 内存 + 回传 body | 内存 dict |
| **NAT 穿透** | ❌ | ❌ | ✅ |
| **典型负载** | 编译（分钟级）| 编译（分钟级）| 发布/生成（秒~分钟级）|

**核心矛盾**：DevBridge 和 Publisher-Client 在做**同一件事**（把工作外包给远程机），却用了两套互不兼容的协议、两套任务状态、两套鉴权。新增任何一类远程工作都要重复造轮子。

---

## 五、目标：统一为 `RemoteTask` 抽象

详见 [《通用 RemoteTask 接口设计》](./remote-task-interface.zh.md)。一句话概括：

> 把「下发任务 + 回传结果」的回环抽象成一个 `RemoteTask`，传输层抽成两个可插拔 backend：`PushBackend`（SSH/HTTP，内网编译机）与 `PullBackend`（HTTP 队列，NAT 后客户机）。上层 DevBridge 和 Publisher-Client 都变成 `RemoteTask` 的两类 provider 配置。

统一后的收益：

1. **新增远程能力只写 handler**：接一个「邮件群发客户机」「某 IDE 远程编译」只需写 `RemoteTaskHandler`，传输/鉴权/状态/进度都复用。
2. **状态/进度统一**：编译进度和发布进度走同一套 `status` 流转和轮询 UI。
3. **可观测性统一**：一类 job 一张表/一套日志，不再散落 metadata 文件 + 内存 dict。
4. **DevBridge 编译也能 Pull**：当编译机位于 NAT 后时，复用 Pull backend，无需 SSH 打洞。

---

## 六、关键文件索引

### 中心侧
| 文件 | 作用 |
|------|------|
| `app/publish/client/protocol.py` | `PublishJob` dataclass + `PROTOCOL_VERSION`（Pull 协议载体）|
| `app/publish/client/dispatcher.py` | 内存队列 enqueue/claim/complete（Pull backend MVP）|
| `app/api/publish.py` | `/jobs/claim` `/jobs/{id}/result` `/video-upload` HTTP 入口 |
| `app/publish/publishers/{playwright,video,image}_client.py` | 三类 publisher，都是 enqueue + 轮询 job 状态 |
| `app/services/rooted_project_bridge_service.py` | DevBridge 核心：read/patch/build/publish/rollback |
| `app/services/build_queue_service.py` | Redis 编译队列 enqueue/pop |
| `app/services/build_worker_runner.py` | worker 槽内执行一个编译 job |
| `app/api/devbridge.py` | DevBridge REST 入口 |

### 客户机侧
| 文件 | 作用 |
|------|------|
| `publisher-client/agent.py` | Pull 客户机主进程（轮询 + trigger + schedule）|
| `publisher-client/runners/__init__.py` | `BaseRunner` + `@register` 注册表 |
| `publisher-client/runners/{xiaohongshu,douyin,weibo}.py` | Playwright 发布 runner |
| `publisher-client/runners/video.py` | ComfyUI 视频/图片生成 runner |
| `ops/scripts/gamecenter-windows-build-agent.py` | Windows HTTP build agent（Push 的 HTTP 子类）|
| `ops/scripts/gamecenter-remote-pipeline-build.sh` | 中心 → SSH 编译机入口 |
| `ops/scripts/gamecenter-build-worker.py` | 编译 worker 池主程序 |

### 文档
| 文件 | 作用 |
|------|------|
| `docs/devbridge.zh.md` | DevBridge 桥接开发总览 |
| `docs/gamecenter-build-queue.zh.md` | 编译队列运维手册 |
| `docs/gamecenter-agent-integration.zh.md` | GameCenter 代理接入设计 |
| `docs/plan/publish-system/OVERVIEW.md` | 发布系统总览 |
| `docs/plan/publish-system/ARCHITECTURE.md` | 发布系统数据契约 |
