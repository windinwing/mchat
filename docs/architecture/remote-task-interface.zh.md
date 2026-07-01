# 通用 RemoteTask 接口设计草案

> 把 MChat 现有的「连其他主机干活」能力（DevBridge 编译 / Publisher-Client 发布与生成）统一成一个抽象。
> 配套阅读：[Server↔Client↔Server 架构介绍](./remote-host-bridge.zh.md)
> 状态：**设计草案，未实现**。最后更新：2026-07-01

> **决策记录（2026-07-01）**：经评估，全 Pull 在 NAT 友好、安全（中心不再持内网 SSH 私钥）、横向扩展、容错上均优于 Push，且协议更单一。结论：**新的远程连接一律优先用 Pull；已实现的 DevBridge Push（SSH pipeline / Windows HTTP agent）暂不迁移，保留观望。** 下文双后端设计作为过渡期参考与"离线编译机"场景的兜底，保留不删。

---

## 一、设计目标

1. **一个抽象盖住三种现状**：SSH pipeline、HTTP build agent、HTTP pull client，收敛到同一 `RemoteTask` 模型。
2. **传输可插拔**：`PushBackend`（中心→远程）与 `PullBackend`（远程→中心）是两个 backend，上层无感。
3. **不破坏现状**：分阶段迁移，旧 `PublishJob` / DevBridge 调用路径先并存、后替换。
4. **能力可枚举**：远程机上线时声明自己支持哪些 `task_type`，中心按能力路由。

## 二、非目标

- 不统一远程机的运行时（Playwright / ComfyUI / Cocos / SSH shell 各自保留）。
- 不引入消息总线 / MQ（Kafka/NATS）——继续用 Redis + HTTP，规模不需要。
- 不强行让 DevBridge 编译改成 Pull（保留双后端）。

---

## 三、核心抽象

### 3.1 `RemoteTask`（任务契约，传输无关）

```python
# app/remote_task/protocol.py
@dataclass
class RemoteTask:
    task_id: str
    task_type: str          # "compile" | "publish.social" | "generate.image" | "generate.video" | ...
    provider: str           # "gamecenter" | "comfyui" | "playwright" | 自定义
    payload: dict           # 类型相关：{slug,build_id} / {platform,content,media} / {prompt,...}
    status: str             # pending|claimed|running|done|failed  (统一五态)
    result: dict | None     # {success, remote_url?, remote_id?, ...}
    error: str | None
    error_code: str | None  # timeout | needs_login | captcha | client_error
    created_at: float
    updated_at: float
    deadline_at: float      # 超时绝对时间（替代各 publisher 自己的 timeout）
    transport: str          # "push" | "pull"  (运行期确定，路由用)
    target: str             # push: "ssh:10.98.8.186" / "http:10.98.8.186:19280"; pull: 客户机 cluster
    progress: dict | None   # 可选进度 {percent, stage, message}
    protocol_version: int = 1
```

**与现有 `PublishJob` 的关系**：`PublishJob` ≈ `RemoteTask(task_type="publish.*")`。迁移期 `job_from_dict` 可视为旧版协议的适配器。

### 3.2 状态机（统一）

```
pending ──claim──▶ claimed ──start──▶ running ──complete──▶ done
   │                  │                   │
   │                  └───── timeout ─────┴──▶ failed
   └──────── cancel (push only) ──────────────▶ failed
```

- **pending**：已入队，等执行端取走（pull）或被 push backend 派发（push）。
- **claimed**：执行端认领（pull 的 claim、push 的 agent 开始处理）。
- **running**：执行端报告开始干活（可选心跳）。
- **done/failed**：终态。

现有差异：
- `PublishJob` 只有 4 态（缺 `running`，缺心跳/进度）。
- DevBridge 编译靠 `metadata.json` 的 `queued|running|built|failed`，本质同构但字段名不同。

### 3.3 传输 Backend 接口

```python
# app/remote_task/backends/base.py
class TaskBackend(Protocol):
    transport: str  # "push" | "pull"

    async def submit(self, task: RemoteTask) -> None: ...
        """把任务交给执行端。push=主动连远程；pull=放进队列等认领。"""

    async def wait(self, task_id: str, deadline: float) -> RemoteTask | None: ...
        """阻塞到终态或超时。复用层统一轮询。"""

    async def cancel(self, task_id: str) -> bool: ...
        """尽力取消。push 可发 kill；pull 只能标记放弃。"""
```

```python
# app/remote_task/backends/push.py
class PushBackend(TaskBackend):
    """中心主动连远程机。target 决定子传输：
       - ssh://   → subprocess ssh + 远程 pipeline script
       - http://  → POST /v1/run (同步或流式)
    兼容现有 gamecenter SSH pipeline 与 Windows build agent。"""

# app/remote_task/backends/pull.py
class PullBackend(TaskBackend):
    """远程机主动来取。底层换成 Redis 队列/DB（替代内存 dict）。
       HTTP 入口 /api/remote-tasks/{claim,result,heartbeat} 取代 /api/publish/jobs/*。"""
```

### 3.4 执行端 Handler 接口（远程机侧）

```python
# 远程机（客户机 / agent）实现，与中心解耦
class TaskHandler(Protocol):
    task_type: str  # 这个 handler 处理哪类任务

    def handle(self, task: RemoteTask) -> TaskResult: ...
        # 同步或带进度回调；失败抛 TaskError(code=...)
```

现有 `BaseRunner.publish(job)` 天然映射成 `TaskHandler.handle(task)`，只需把 `job` 字段重命名对齐。

---

## 四、HTTP 协议（对外契约）

### 4.1 Push（中心→远程，仅 HTTP agent 子类）

中心调远程 agent：

```
POST http://<agent>/v1/run
Authorization: Bearer <token>
{ "task_id": "...", "task_type": "compile", "payload": {"slug":"pkg0019","build_id":"..."} }

← 200 { "ok": true, "result": {...} }            # 同步
← 200 { "ok": true, "status": "running", "task_id": "..." }  # 或异步，后续轮询
GET  http://<agent>/v1/tasks/{task_id}            # 异步查进度（复用现有 /v1/health 风格）
```

> Windows build agent 现有 `/v1/build` 只需包一层：把 `{slug,build_id}` 视作 `payload`，`task_type="compile"`。

### 4.2 Pull（远程→中心，客户机轮询）

```
POST /api/remote-tasks/claim
  { "client_id": "macbook-1", "capabilities": ["publish.social","generate.image"] }
← { "task_id": "...", "task": {...} }  或  { "task_id": null }

POST /api/remote-tasks/{task_id}/heartbeat     # 可选，报告 running + progress
  { "stage": "rendering", "percent": 42 }

POST /api/remote-tasks/{task_id}/result
  { "status": "done", "result": {...} }
  { "status": "failed", "error": "...", "error_code": "needs_login" }

POST /api/remote-tasks/upload                   # 产物文件回传（现 /video-upload 泛化）
  multipart file → { "url": "/uploads/..." }

GET  /api/remote-tasks/{task_id}                # 中心侧查状态（publisher 轮询用）
```

**能力声明**：claim 时带 `capabilities`，中心只派该 client 声明支持的 task_type。这取代当前「靠 platform 字符串匹配」的隐式路由。

---

## 五、路由：怎么选 backend

中心接到一个远程工作请求时：

```
1. 解析出 (task_type, provider)
2. 查 provider 配置 → transport = push | pull
   - provider 配了 ssh_host / agent_url  → push
   - provider 配了 client cluster         → pull
3. 构造 RemoteTask(transport=...) → backend.submit()
4. 上层 await backend.wait(task_id, deadline)
```

| 场景 | task_type | provider | transport |
|------|-----------|----------|-----------|
| 小红书发布 | publish.social | playwright | pull |
| ComfyUI 生图 | generate.image | comfyui | pull |
| Cocos 编译（内网编译机）| compile | gamecenter | push (ssh) |
| Cocos 编译（Windows agent）| compile | gamecenter | push (http) |
| 邮件群发（假设）| notify.email | smtp-relay | pull |

**同一 task_type 可有两种 transport**：编译机在内网走 push，搬去 NAT 后改 pull 配置即可，业务代码不变。

---

## 六、与现有代码的映射

| 现有 | 统一后 |
|------|--------|
| `PublishJob` | `RemoteTask(task_type="publish.*")`，旧 dataclass 作为 v1 兼容层 |
| `enqueue_job/claim_job/complete_job`（内存）| `PullBackend`（底层换 Redis/DB）|
| `PlaywrightClientPublisher._wait_for_result` | `backend.wait()` |
| DevBridge `build_project`（subprocess）| `PushBackend(ssh)` |
| Windows agent `POST /v1/build` | `PushBackend(http)` |
| `gamecenter-build-worker.py` worker 池 | 复用，改成消费 `RemoteTask` 队列 |
| `BaseRunner.publish(job)` | `TaskHandler.handle(task)` |
| `/api/publish/jobs/*` | `/api/remote-tasks/*`（旧路径保留一个版本做灰度）|
| `data/devbridge/.../metadata.json` | `RemoteTask` 表（DB）+ 进度字段 |
| `publish_record` 表 | 保留，`task_id` 外键关联 |

---

## 七、迁移路径（分四步，每步可独立上线）

### Step 1 — 抽象层落地（不改调用方）
- 新增 `app/remote_task/` 包：`protocol.py`（RemoteTask）、`backends/{base,push,pull}.py`、`router.py`。
- `PullBackend` 先内部包装现有 `dispatcher.py`，行为不变。
- `PushBackend` 先包装现有 SSH subprocess 调用。
- **零行为变更**，只是把代码搬进新包。

### Step 2 — 状态持久化
- `RemoteTask` 落 DB 表（或 Redis hash），替代内存 dict。
- Publisher-Client 重启不丢任务；编译 metadata 与 task 表对齐。
- 客户机 `/jobs/*` 路由内部读新表，对外路径暂不动。

### Step 3 — HTTP 协议升级（双轨）
- 新增 `/api/remote-tasks/*`，支持 capabilities + heartbeat + upload。
- 客户机 agent 同时支持新旧两套 claim（配置开关）。
- 新 task_type（如邮件群发、新平台发布）只走新协议。

### Step 4 — DevBridge 收编（可选，最大收益）
- 编译 provider 增配 `transport=pull`，编译机跑一个 pull agent（复用 publisher-client 框架）。
- NAT 后的编译机无需 SSH 打洞。
- Windows build agent 的 `/v1/build` 包成 `task_type=compile` 的 push handler。

---

## 八、待确认的设计点

1. **进度粒度**：编译进度（Cocos 阶段）和发布进度（Playwright 步骤）的进度 schema 是否统一？建议 `{stage, percent, message}` 最低公约数。
2. **取消语义**：push 能 kill 远程进程，pull 只能放弃——是否对上层暴露这个差异？建议 `cancel()` 返回 `supported: bool`。
3. **多租户/多客户机**：pull 模式下多个客户机竞争同一队列，是否需要亲和性（某账号只给固定客户机发）？当前是 first-come，可能需要 `client_affinity` 字段。
4. **安全**：push 的 SSH key / agent token 管理；pull 的 client 身份除 JWT 外是否要加 client 证书。
5. **产物回传大小**：视频可能几百 MB，`/upload` 是否要走分片/直传对象存储（现 MinIO）。

---

## 九、验收标准（实现完成后）

- [ ] 新增一类远程工作（如「某新社交平台发布」）只需写一个 `TaskHandler`，零传输代码。
- [ ] 编译进度与发布进度在同一处 UI 可见，同一套轮询。
- [ ] 一个客户机挂掉，其任务可被另一个同能力客户机接管（pull）或被标记失败重试。
- [ ] 重启中心服务，进行中的 pull 任务不丢失。
- [ ] DevBridge 编译可仅改 provider 配置就从 push 切到 pull。
