# Skill 执行系统 — 风险分析与加固方案

> 分析对象:整个 skill 执行子系统(线程池 / 权限 / 进程 / 超时 / 资源)。
> 目标:skill 执行不卡死系统,在相对独立的异步空间运行。
> 本文档由代码实读得出,非推测。

## 1. 现状架构(实读确认)

### 1.1 执行链路

```
Workflow engine (主事件循环,asyncio)
  │
  ├─ run_node() → _execute_skill_for_user(timeout_s)   # 主循环协程
  │     │
  │     └─ asyncio.wait_for(execute_skill(skill, payload), timeout=timeout_s)
  │           │
  │           └─ loop.run_in_executor(get_skills_pool(), _run_local)  # ① 提交到专用线程池
  │                 │
  │                 └─ execute_skill_script()  # ② 同步,在线程池线程执行
  │                       │
  │                       └─ module.run() / module.main()  # ③ skill 代码
  │
  └─ asyncio.gather(*[run_node(nid) for nid in batch])   # 同层节点并行
```

### 1.2 关键组件实读

| 组件 | 位置 | 行为 |
|------|------|------|
| 专用线程池 | `core/skills_pool.py` | `ThreadPoolExecutor(max_workers=16)`,前缀 `skill-exec`,与默认池隔离 ✅ |
| 超时机制 | `workflow_service.py:124` | `_execute_skill_for_user(timeout_s=0)`,**默认 0 = 不超时** ⚠️ |
| 超时来源 | `workflow_service.py:1433` | `cfg.get("timeout_seconds")`,来自**节点配置**,默认无 ⚠️ |
| 权限模型 | `workspace/skill_policy.py` | 平台 skill 直接执行;**租户自建 skill 必须在 container 模式** ✅ |
| 并发控制 | `workflow_service.py:1322` | batch 节点用 `asyncio.Semaphore(max_concurrent)`,默认 3 ✅ |
| 同层并行 | `workflow_service.py:1470` | `asyncio.gather` 同层节点,但**共享 self.db** ⚠️(代码注释已意识) |
| 容器隔离 | `workspace/factory.py` | container 模式 skill 跑在 Docker 容器,真正进程隔离 ✅ |

## 2. 风险清单(按严重度)

> **决策记录(2026-06-25,与负责人确认):**
> - **R1 暂不解决** — 抓取/下载类 skill 确实跑很久(几分钟到几十分钟),强制全局超时会误杀。保留 `config.skill_default_timeout_seconds` 字段(默认 0=不强制),需要时再开。仅在自研 skill 内部保留宽松超时(A1)。
> - **R2 暂不解决** — 当前已主要走 Docker container 模式(进程级隔离),local 模式仅用于平台受信 skill。
> - **R3 已修复** — 见下。

### 🔴 高危(暂不解决)

#### R1. skill 执行默认无超时 → 可永久占线程池
- **现象**:`timeout_seconds` 默认 0,`wait_for(..., timeout=0)` 等于 `timeout=None`(永不超时)。一个卡死的 skill(死循环/网络挂起)会**永久占用一个线程池槽位**,16 个槽位被占满后,所有后续 skill 执行排队等待,系统假死。
- **影响范围**:webhook skill 有 30s httpx 超时(自保),但 python tool skill 无任何保护。
- **决策**:**暂不强制**。抓取/下载类 skill 耗时合理地长。保留 config 字段 `skill_default_timeout_seconds`(默认 0),仅在自研 skill(publish-content/content-writer)内部加宽松超时(A1)。

#### R2. 同一进程内执行 → OOM / CPU 满载拖垮全站
- **现象**:本地模式(local workspace)skill 跑在**主后端进程的线程池**里。
- **决策**:**暂不解决**。当前主要走 Docker container 模式(进程级隔离),local 模式仅用于平台受信 skill。

### 🟡 中危(已修复)

#### R3. 线程池满 → 静默排队无反馈 ✅ 已修复
- **现象**:`run_in_executor` 满载时新任务排队,无背压、无提示。用户看到 workflow 一直 running,无超时无报错,排查困难。
- **修复**:
  - `core/skills_pool.py` 新增 `warn_if_saturated()`:headroom ≤ 1 时 loguru 打 WARNING(每 60s 至多一次,防刷屏)
  - `skill/executor.py` 在每次 `run_in_executor` 提交前调用 `warn_if_saturated()`,满载时第一时间告警
  - `/api/health/metrics` 已暴露 `pool_stats()`(A3),运维可主动查 max_workers/active/queued/headroom
- **效果**:线程池满不再"无提示",通过日志管线 + 健康检查端点双重可见。

#### R4. skill 代码可访问全进程状态
- **现象**:local 模式 skill 同进程,可 `import` 任意 `app.*` 模块(如 `app.core.config` 读 `settings.jwt_secret`)。`_skill_secrets_env` 还会把 skill secrets 注入 `os.environ`,若 skill 代码读取 `os.environ` 能看到**前一个 skill 泄留的 env**。
- **影响**:平台 skill 受信尚可;**租户自建 skill 是安全隐患**(虽有 container 门禁,但 local 模式下 bypass)。

#### R5. 我的 publish-content/content-writer 用 asyncio.run()
- **现象**:线程池线程里调 `asyncio.run()`。已验证**安全**(线程无 running loop)。但每次创建新事件循环有开销,且 `dispatch` 里的 `httpx.AsyncClient` / DB session 都在该临时循环里,**循环结束即销毁**,资源不会泄漏。✅ 无实质风险,确认可接受。

#### R6. 环境变量泄漏跨 skill
- **现象**:`_skill_secrets_env` 用 contextmanager 在 `with` 块内临时注入 env,finally 里还原。**设计正确**,但如果 skill 在子线程里又派生线程,env 会泄漏(因 os.environ 是进程级)。当前 skill 执行是单线程,风险低。

### 🟢 低危(已有缓解)

- **R7. shutil 操作阻塞事件循环**:`ensure_skill_in_tenant` 做 `copytree/rmtree`,代码已用 `asyncio.to_thread` 包裹 ✅(`executor.py:143`)
- **R8. pip 安装阻塞**:`warm_skill_export_deps` 也用 `to_thread` ✅
- **R9. webhook skill 网络挂起**:httpx 有 30s timeout ✅

## 3. 加固方案(分层)

### 第一层:立即加固(本次 PR)— 给新 skill + 建立超时默认

| 措施 | 改动 | 收益 |
|------|------|------|
| **A1. 我的 skill 内部自带超时** | content-writer 的 LLM 调用加超时;publish-content dispatch 已有超时 | 即使节点没配 timeout,skill 自身有保护 |
| **A2. 茶叶模板节点配 timeout_seconds** | 模板里 read/writer/publish 节点加 `timeout_seconds` | 示范正确用法,防卡死 |
| **A3. skills_pool 暴露监控指标** | pool 加活跃任务计数 | 排查"为什么卡" |

### 第二层:系统级加固(P2,建议跟进)

| 措施 | 改动 | 收益 |
|------|------|------|
| **B1. 全局默认超时** | `_execute_skill_for_user` 默认 timeout_s 从 0 改为 300s(可配) | 彻底解决 R1,零成本 |
| **B2. 线程池背压 + 拒绝策略** | 满载时快速失败返回 "busy" 而非静默排队 | 解决 R3 |
| **B3. local 模式也走子进程** | 给高危 skill 选项:子进程执行 + 超时杀进程 | 解决 R2/R4,真正的独立空间 |
| **B4. env 注入用 runpy 隔离** | skill 在独立 namespace 执行,不污染 os.environ | 解决 R6 |

### 第三层:架构级(长期)

- **C1. skill 执行 worker 独立为 sidecar 进程**(类似 publisher-client 的思路),主进程通过 IPC 调用。完全的进程/内存/CPU 隔离,崩溃不影响主进程。项目已有 devbridge 的"外部 provider"模式可复用。

## 4. 本次落地的加固清单(已全部验证)

- [x] **A1** 自研 skill 内部超时:content-writer(LLM 120s)、publish-content(dispatch 300s)、read-uploads(文件/字符上限)
- [x] **A2** 茶叶模板节点配 timeout_seconds(read 30 / writer 180 / publish 60)
- [x] **A3** skills_pool 监控:`pool_stats()` → `/api/health/metrics`
- [x] **R3 修复** `warn_if_saturated()` 满载告警 + executor 调用 + 日志可见
- [~] **B1** 全局默认超时:**保留 config 字段(默认 0=不强制)**,需要时可改。按决策暂不启用
- [-] **R1** 暂不解决(抓取/下载 skill 耗时合理地长)
- [-] **R2** 暂不解决(已主要走 Docker container 隔离)

## 5. 结论

当前 skill 系统的隔离设计方向正确(专用线程池 + container 门禁 + webhook 超时)。本次加固聚焦于:
1. **自研 skill 的内部超时**(A1)——不影响其它 skill,值宽松,不会误杀长任务
2. **R3 满载告警**——线程池满不再无提示,日志 + 健康检查端点双重可见

R1(全局超时)/R2(进程隔离)按负责人决策暂缓:抓取下载类 skill 合理地慢;生产主要走 Docker 容器。
