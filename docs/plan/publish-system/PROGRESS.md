# 开发日志 — 内容自动分发系统

> 回溯用。**每个模块完成即追加一条**,格式:`### [日期] 模块名 — 状态` + 改动文件 + 决策记录 + 待办。

## 决策记录(Decisions)

- **D1 (2026-06-25)** 采集复用 `skills/web-fetch`(已有代理),不重建抓取层。
- **D2 (2026-06-25)** 发布器注册表镜像 `devbridge_registry.py` 的 provider 模式;发布抽象镜像 `channels/base_adapter.py` 但 outbound。
- **D3 (2026-06-25)** 客户机用 Pull(轮询)模式,不穿 NAT,适配"连到 mac mini"拓扑。
- **D4 (2026-06-25)** 平台↔发布唯一接缝是 `skills/publish-content` skill。核心系统零侵入。
- **D5 (2026-06-25)** P1 不建新表,渠道凭证先走 skill payload 的 `channel_config`;规模上来后再建 `publish_jobs`。
- **D6 (2026-06-25)** 小红书/抖音走客户机 Playwright + 持久化真实 profile + 真实 IP,不做协议自动化。
- **D7 (2026-06-25)** Skill 跑在 skills 专用线程池(非事件循环线程),async 调用用 `asyncio.run()` 在该线程开新循环。
- **D8 (2026-06-25)** content-writer 复用用户默认 AIConfig(`is_default`),无需单独填 Key。镜像 `query_rewrite_chat` 的 provider 模式。
- **D9 (2026-06-25)** 客户机任务用进程内内存队列(带 24h TTL GC),无 Redis/DB 依赖,P2 再换持久化后端。

---

## 进度### [2026-06-25] P1 全部完成 — ✅
**改动文件:**
- `src/backend/app/publish/__init__.py` — 包导出
- `src/backend/app/publish/base.py` — `PublishRequest/PublishResult/PublishMedia/BasePublisher`
- `src/backend/app/publish/registry.py` — `PublisherProvider` + 注册表(镜像 devbridge_registry)
- `src/backend/app/publish/service.py` — `dispatch()` 门面(唯一入口,错误编码进 result 不抛异常)
- `src/backend/app/publish/publishers/__init__.py` — `build_builtin_publishers()`
- `src/backend/app/publish/publishers/feishu.py` — 飞书群机器人(text/card + HMAC 签名)
- `src/backend/app/publish/publishers/playwright_client.py` — 客户机派发 publisher(入队+轮询结果)
- `src/backend/app/publish/client/__init__.py` — 客户机协议包
- `src/backend/app/publish/client/protocol.py` — `PublishJob` + `PublishJobStatus` + 版本化 schema
- `src/backend/app/publish/client/dispatcher.py` — 内存队列 `enqueue/claim/complete/status`
- `skills/publish-content/` (SKILL.md + main.py) — **唯一接缝**
- `skills/read-uploads/` (SKILL.md + main.py) — 读 `tea/{yyyy.MM.dd}`(日期模板渲染)
- `skills/content-writer/` (SKILL.md + main.py) — LLM 生成(4 种风格)
- `src/backend/app/data/workflow_templates.py` — 茶叶日报模板(中/英)

**冒烟验证(运行时):**
- ✅ 注册表:feishu + playwright_client 已注册
- ✅ dispatch 四类错误路径(missing/unknown provider、empty payload、invalid config)正确编码
- ✅ feishu dispatch 成功路径(stub)
- ✅ protocol round-trip + PublishJobStatus
- ✅ dispatcher enqueue→claim→complete round-trip
- ✅ 全部文件语法编译通过
- ⏳ 真实飞书 webhook 端到端(待用户提供 webhook 联调)
- ⏳ 真实 LLM 生成(待用户配默认 AIConfig)

**修复的 bug:** `client/__init__.py` 导出 `PublishJobStatus` 但 protocol.py 未定义 → 已在 protocol.py 补 `PublishJobStatus` 类。

**下一步:** P2 — 多 API 渠道(公众号/企微/Slack/Telegram)+ 客户机骨架落地 + 客户机 HTTP 端点。

### [2026-06-25] P1.5 Skill 执行系统加固 — ✅
**背景:** 深度分析 skill 执行子系统(进程/线程/权限/性能),识别卡死风险并加固。详见 `SKILL-EXEC-RISK.md`。

**风险发现(核心):**
- R1 🔴 skill 默认无超时(`timeout_seconds=0`),一个挂起的 skill 永久占线程池槽 → 系统假死
- R2 🔴 local 模式 skill 同进程,大计算/OOM 拖垮全站(多租户隔离失效)
- R3 🟡 线程池满载静默排队,无背压无反馈
- R5 ✅ 我的 skill 用 asyncio.run() 已验证安全(线程池线程无 running loop)

**加固改动(全部验证通过):**
- **A1** `skills/content-writer/main.py` — LLM 调用整体超时(`timeout_seconds=120`, `asyncio.wait_for`)
- **A1** `skills/publish-content/main.py` — dispatch 整体超时(`_DEFAULT_TIMEOUT=300`,防 playwright client 永不 claim)
- **A1** `skills/read-uploads/main.py` — `_MAX_FILES=200` + `_MAX_TOTAL_CHARS=100000` 资源上限,防海量文件撑爆内存
- **A2** `workflow_templates.py` — 茶叶模板(中/英)read/writer/publish 节点各配 `timeout_seconds`(30/180/60)
- **B1** `core/config.py` + `workflow_service.py` — **全局默认超时** `skill_default_timeout_seconds=300`;节点不配 timeout 时用全局值兜底(解决 R1)
- **A3** `core/skills_pool.py` + `api/health.py` — `pool_stats()` 暴露 max_workers/active/queued/headroom 到 `/api/health/metrics`(解决 R3 可观测性)

**运行时验证:**
- ✅ publish dispatch 超时 0.1s 触发 TimeoutError
- ✅ pool_stats 正确反映活跃任务数(空池 active=0,有任务 active=1)
- ✅ content-writer/read-uploads/publish-content 资源限制常量就位
- ✅ config + workflow_service 超时回退逻辑正确
- ✅ 全部文件语法编译通过

**待跟进(P2/P3 建议):**
- R2(local 同进程隔离)→ 高危 skill 选项化子进程执行
- B2 线程池背压(满载快速失败而非静默排队)
- C1 skill worker sidecar 化(完全进程隔离)

### [2026-06-25] R1/R2 决策 + R3 告警修复 — ✅
**负责人决策调整:**
- **R1(全局超时)暂不启用** — 抓取/下载类 skill 合理地慢,强制超时会误杀。`config.skill_default_timeout_seconds` 回退为默认 0(保留字段,需要时可开)。A1 自研 skill 内部超时保留(不影响其它 skill)。
- **R2(local 进程隔离)暂不解决** — 已主要走 Docker container 模式。

**R3(线程池满载无提示)修复:**
- `core/skills_pool.py` 新增 `warn_if_saturated()`:headroom ≤ 1 时 loguru WARNING(60s 冷却防刷屏)
- `skill/executor.py` 每次 `run_in_executor` 提交前调用,满载第一时间告警
- 配合 A3 的 `/api/health/metrics` → `pool_stats()`,双重可见

**运行时验证:** 空池不告警 / 满载告警 / 冷却防刷屏 全部通过。

### [2026-06-25] P1 联调 + 真实 Workflow 引擎验证 — ✅
**联调环境:** `make cloud`（cloud.main:app, --reload, MySQL 3307, deepseek-v4-flash）

**逐层联调（全部通过）:**
1. ✅ 飞书 webhook 直发（curl）
2. ✅ FeishuPublisher 代码路径（真实发包）
3. ✅ service.dispatch 门面（完整链路）
4. ✅ publish-content skill `run()` 入口
5. ✅ content-writer 真实 LLM 生成（deepseek）
6. ✅ read-uploads 真实读上传区（tea/2026.06.25, 2 文件）
7. ✅ **真实 Workflow 引擎全链路**: read(2文件)→writer(208字)→publish(飞书收到) 全 success

**联调中发现并修复的 3 个真实 bug:**

- **B-1 跨 event loop 崩溃**: content-writer 原用 `asyncio.run()` 在 skill 线程池开新 loop，但平台 async DB engine + LLM provider 绑定主 loop → 跨 loop 失败("Future attached to different loop")。
  **修复**: content-writer **全同步化**——同步 sqlalchemy 查 AIConfig（临时 engine from DATABASE_URL, +pymysql）、同步 openai SDK 调 LLM。纯同步，符合 skill 在线程池执行的约定。**经验:需要访问平台 async 资源的 skill 必须用同步客户端，不能 asyncio.run()。**

- **B-2 DeepSeek 思考模型 content 为空**: deepseek-v4-flash 是思考模型，最终答案在 `delta.content`，思考过程在 `reasoning_content`。最初同步版只读 content 拿到空（前几个 chunk 是思考阶段），误以为要读 reasoning_content → 反而把思考过程当答案。
  **修复**: 只取 `delta.content`（真正的答案），跳过 `reasoning_content`（思考链）。镜像 provider.py 的 type 分离逻辑。

- **B-3 workflow 模板 payload 引用多余 .result**: 模板写 `${nodes.writer.result.content}`，但 workflow 引擎存的节点结果是 `outputs["nodes"]["writer"] = {content,title,...}`（已铺平，无 result 层）→ 解析成 None。
  **修复**: 改为 `${nodes.writer.content}` / `${nodes.writer.title}`（与 patent 模板的 `${nodes.chart.charts}` 格式一致）。

**结论:** 茶叶日报系统在真实 workflow 引擎下完全可用。read→write→publish 闭环 5982ms 跑通，飞书群收到 AI 生成的茶叶文案。

### [2026-06-25] B-1/B-2 彻底解决 — ✅

**B-1 跨 event loop 问题 — 彻底方案（非 workaround）：**
不再用"全同步化"这种牺牲并发的 workaround，而是**给 skill 框架增加 async 入口原生支持**，从根本上解决易用性 + 并发：

- `workspace/skill_runner.py`: `execute_skill_script` 检测 `async def run()`，返回 coroutine 供调用方 await
- `skill/executor.py`: 新增 `_skill_has_async_run()`（AST 检测，无 import 副作用）。async skill **直接在主 event loop await**（不经线程池），能用平台原生 async DB engine + async LLM provider；sync skill 照旧线程池
- `skills/content-writer/main.py`: 改回 `async def run()`，用 async_session_factory + AsyncOpenAI
- `skills/publish-content/main.py`: 改回 `async def run()`，直接 await dispatch

**为什么这是彻底解：**
- async skill 在主 loop 跑，IO 调用（DB/LLM/HTTP）协作式让出，**不阻塞其它协程，并发友好**
- skill 作者只需 `async def run()`，自动获得正确路由，**易用**
- 同步 skill（web-fetch 等）零改动，**向后兼容**
- 根除了跨 loop 问题（"Future attached to different loop"），因为不再有第二个 loop

**B-2 DeepSeek 思考模式 — 彻底解决：**
经实测，`deepseek-v4-flash` 确实是思考模型（默认产 reasoning_content）：
- 默认：content 空（max_tokens 被思考链耗尽），reasoning 162 字
- `reasoning_effort=low`：content 出现，reasoning 缩短

**修复（content-writer）:**
- deepseek provider 加 `reasoning_effort="low"`（缩短思考链，保留答案质量）
- 只读 `delta.content`（真答案），跳过 `reasoning_content`（思考链）
- 系统 prompt 加"请直接输出最终文案,不要输出分析过程"
- 非 deepseek provider 不传该参数（兼容）

**验证:** async skill 全链路 success（read 2文件 → writer 200字 → publish 飞书收到），6789ms。

### [2026-06-25] P2 完成 — 客户机骨架 + 多渠道 — ✅
**客户机协议（Pull 模式）:**
- `app/api/publish.py` — 4 个 HTTP 端点: `/api/publish/jobs/claim`、`/jobs/{id}/result`、`/jobs/{id}`、`/health`
- 注册到 api_router (tags=["Publish"])
- `publisher-client/agent.py` — 独立进程 Pull 主循环（轮询中心拉任务→Playwright 执行→回传），urllib 无额外依赖
- `publisher-client/config.example.toml` — 中心地址/平台/轮询间隔/浏览器配置
- `publisher-client/runners/__init__.py` — BaseRunner + 注册装饰器（P3 补具体 Playwright runner）
- `publisher-client/README.md` — 架构/快速开始/开发新 runner

**新增 API 渠道:**
- `app/publish/publishers/slack.py` — Slack incoming webhook
- `app/publish/publishers/telegram_channel.py` — Telegram bot→channel
- 注册表现含 4 个: feishu / slack / telegram_channel / playwright_client

**验证:** 语法全过 / 4 publisher 注册 / publish API health ✅ / 客户机 claim 协议 ✅ / Slack+Telegram 错误处理正确

**P2 检查清单 ✅:**
- [x] 客户机 HTTP 端点
- [x] publisher-client 独立骨架
- [x] Slack + Telegram publisher
- [x] runner 基类 + 注册机制

**P3 待办:**
- [ ] `runners/xiaohongshu.py` Playwright runner（持久化 profile + 模拟人节奏）
- [ ] `runners/douyin.py`
- [ ] 首次登录工具（建立持久 cookie）
- [ ] dispatcher 换持久化后端（Redis/DB，支持多 worker）

### [2026-06-25] P3 完成 — Playwright runner 框架 — ✅

**合规定位（明确写入文档）：** 个人/小团队发布辅助工具，用真实账号 + 持久化登录态 + 模拟人节奏。**不做验证码自动绕过**（人在回路：遇验证码暂停 + 通知人工）。不用于营销号矩阵。

**客户机 runner 基础设施:**
- `runners/browser.py` — 持久化 profile 管理（每平台独立 `browser_data/<platform>/`）+ managed_browser 上下文管理器 + 基础反检测（隐藏 webdriver flag）
- `runners/human.py` — 人节奏模拟：随机延迟、逐字输入、滚动、鼠标抖动
- `runners/selectors.py` — 选择器集中管理（UI 变了只改这里），含 xiaohongshu + douyin
- `runners/__init__.py` — BaseRunner + @register 装饰器 + 懒加载（不污染 import playwright）

**平台 runner:**
- `runners/xiaohongshu.py` — 小红书图文笔记发布：登录检查→上传图→填标题/正文→风控检测→发布→成功确认。NeedsLoginError / CaptchaEncountered 两个特殊错误类
- `runners/douyin.py` — 抖音发布（同模式）
- `runners/login.py` — 首次登录工具：打开浏览器让用户手动登录，关闭后保存持久 cookie

**人在回路:**
- agent.py 捕获异常时分类: needs_login / captcha / error，回传中心明确状态
- 验证码：**暂停 + 回传 captcha 错误**，不自动绕过
- 登录失效：回传 needs_login，提示运营跑 login 工具

**验证:** 语法全过 / runner 懒加载注册正确（xiaohongshu+douyin）/ 选择器层 OK / 未知 platform 返回 None

**P3 检查清单 ✅:**
- [x] runner 基础设施（浏览器 + profile + 人节奏）
- [x] 选择器层
- [x] 小红书 runner
- [x] 抖音 runner
- [x] 首次登录工具
- [x] 人在回路（验证码暂停 + 错误分类）

**待实际环境验证（需 mac mini + 真实账号 + playwright install）:**
- [ ] 小红书端到端发布（选择器需对照实际 DOM 校准）
- [ ] 抖音端到端发布
- [ ] 持久登录态有效期验证
- [ ] dispatcher 换持久化后端（多 worker）

### [2026-06-25] P3 小红书全自动发布成功 — ✅🎉

**在真实账号 + 持久登录态下，无头模式全自动发布成功**（笔记"GLM-5.2 使用体验"已发布，跳转 /publish/success）。

**联调中校准的真实 DOM 与交互（全部对照实际页面，非猜测）:**
- **入口**：`/publish/publish?from=homepage&target=image`（图文模式 + 自动开选图器）
- **标题**：`input[placeholder*="填写标题"]`（placeholder="填写标题会有更多赞哦"，上传图后才出现）
- **正文**：`div.tiptap.ProseMirror`（ProseMirror contenteditable）
- **上传**：切图文 tab 后 `input[type=file]`（accept=.jpg/.png/.webp）
- **登录检测**：URL 是否含 "login"（不在登录页 = 已登录）
- **提交按钮**：自定义元素 `<xhs-publish-btn>`（无内部 DOM，无 shadow，事件委托到 document）

**三个关键发现（破解发布的关键）:**

- **D10 提交按钮是坐标分区**：`<xhs-publish-btn>` 横跨整个编辑区宽度，内部无 DOM 节点。它通过 document 级事件委托，**按点击的 X 坐标区分"暂存离开"（左半）和"发布"（右半）**。手动成功点击坐标 x≈733/760（元素 x=338,w=680）。点中心(678)落分界线无效。**修复：点击 width*0.6 处（≈746），稳稳落在发布区。**
- **D11 话题清洗**：小红书话题不允许特殊符号（`.` 等），LLM 生成的 `#GLM5.2` 会触发"话题内不允许包含特殊符号"拦截。**修复：`_sanitize_content` 清洗话题，只保留中文/字母/数字/下划线（#GLM5.2→#GLM52）。**
- **D12 持久 profile 锁清理**：chromium 异常退出会残留 SingletonLock，导致下次 launch_persistent_context 的 TargetClosedError。**修复：`_clear_stale_locks` 启动前清理。**

**验证流程（全自动无头）:**
登录检测✅ → 切图文tab✅ → 上传图✅ → 填标题正文✅（话题已清洗）→ 风控检测✅ → 点击发布区(0.6)✅ → 跳转 /publish/success ✅

**P3 小红书检查清单 ✅:**
- [x] runner 基础设施（浏览器持久 profile + 人节奏 + 锁清理）
- [x] 选择器校准（对照真实 DOM）
- [x] 提交按钮坐标分区定位
- [x] 话题清洗（LLM 文案适配）
- [x] 校验提示检测（失败时返回明确原因）
- [x] 首次登录工具
- [x] **全自动无头发布成功**

**剩余（低优先级）:**
- [ ] 抖音端到端（同模式，需校准抖音 DOM）
- [ ] dispatcher 持久化后端（Redis，多 worker）
- [ ] 图片 URL 自动下载（当前只支持本地 path）

### [2026-06-25] 收尾增强（任务1-4，无人值守完成）— ✅

**任务1: 茶叶日报多渠道双发（飞书 + 小红书并行）**
- `workflow_templates.py` 茶叶模板（中/英）改为 DAG 双发：`writer → [publish_feishu, publish_xhs] → merge → end`
- 两条渠道独立并行，互不影响；start 增加 `xhs_image_path`（可选）
- 验证：DAG 结构合法，飞书纯文字 + 小红书文字+图

**任务4: 图片 URL 自动下载（小红书/抖音支持远端图）**
- `publisher-client/runners/media.py` — `resolve_media_paths`：本地 path 直用，http(s) url 自动下载到临时文件，用完 `cleanup_paths` 清理
- 小红书/抖音 runner 改用共享的 media 解析（删除各自重复的 `_resolve_images`）
- 验证：本地 path ✅ / URL 下载 ✅ / suffix 推断 ✅ / 无效媒体安全跳过 ✅ / 临时文件清理 ✅

**任务3: 定时自动化（客户机侧轻量定时器）**
- `agent.py` 新增 `--trigger WORKFLOW_ID PAYLOAD_JSON`（一次性触发 workflow run-once）
- `agent.py` 新增 `--schedule`（按 config `[schedule]` 配置循环触发，固定间隔）
- 设计取舍：定时放客户机侧，**零后端侵入**（不改 worker/SkillSchedule）。精度要求高时改用后端 worker（WORKER_ENABLED=true + cron）
- 验证：`--trigger` 真实触发中心 workflow 成功（run=7f2dc5ca）；`--schedule` 无配置时正确提示
- `config.example.toml` 加 `[schedule]` 配置示例

**任务2: 抖音 runner（代码就绪，待登录联调）**
- `runners/douyin.py` 重写，复用小红书验证过的模式（持久 profile + 人节奏 + media 解析 + 人在回路 NeedsLogin/Captcha）
- 选择器按抖音 creator 公开 UI 写，**标注待实际 DOM 校准**（同小红书流程：login → 探查 DOM → 校准）
- 验证：注册正确 + 复用 media 解析

**清理：**
- 删除联调临时文件（截图/测试图/探查脚本）
- 新增 `publisher-client/.gitignore`（排除 venv/browser_data/config.toml 含敏感信息）

**新增文件：** `runners/media.py`
**修改文件：** `workflow_templates.py`, `runners/xiaohongshu.py`, `runners/douyin.py`, `agent.py`, `config.example.toml`

### [2026-06-25] 全渠道扩展（国内+海外）— ✅

**国内 API 渠道（合规，中心直发）:**
- `publishers/dingtalk.py` — 钉钉群机器人（webhook + HMAC 签名 + text/markdown）
- `publishers/wecom.py` — 企业微信群机器人（webhook 或 key，text/markdown）
- `publishers/wechat_mp.py` — 微信公众号（access_token 缓存 + 封面上传 + 草稿 + 发布，最复杂）

**海外 API 渠道（合规）:**
- `publishers/discord.py` — Discord webhook（204 成功判定）
- `publishers/twitter_x.py` — X/Twitter API v2（OAuth2 access_token 或 refresh）
- `publishers/facebook.py` — Facebook Graph API（Page feed 发布）
- `publishers/linkedin.py` — LinkedIn UGC Posts API

**客户机渠道（无 API，Playwright）:**
- `runners/weibo.py` — 微博 web composer（选择器待校准，同小红书流程）

**注册表现 11 个 publisher + 3 个 client runner:**
| 类型 | 渠道 | 验证 |
|------|------|------|
| 国内API | 飞书 ✅真实 钉钉/企微/公众号 ✅自测 | validate_config 全过 |
| 海外API | Slack/Discord/Telegram ✅自测 X/FB/LinkedIn ⏳需凭证 | validate_config 全过 |
| 客户机 | 小红书 ✅真实 抖音⏳ 微博⏳ | 注册正确 |

**验证:** 全部 11 publisher 注册 + validate_config + dispatch 错误编码统一（不抛异常）；3 client runner 注册正确。

**待联调（需用户凭证）:**
- [ ] 钉钉/企微 webhook（用户提供机器人 URL）
- [ ] 公众号 app_id/secret（需认证服务号）
- [ ] Discord/X/FB/LinkedIn OAuth 凭证
- [ ] 抖音/微博 login + DOM 校准

### [2026-06-25] 多账号分发 + 采集 + 简报系统（4 子系统）— ✅

**决策记录:**
- **D13** 多账号凭证复用 Channel 表 + field_encryption 加密（不新建表）
- **D14** 批量分发复用现有 batch 节点（不改 workflow 引擎）
- **D15** 采集内容存知识库 KB（create_document 向量化，可 RAG 检索）
- **D16** 简报复用 content-writer/daily-summary 纯 skill 实现（不新建 service）

**子系统1: 多账号凭证管理（Channel 加密 + dispatch 桥接）**
- `schemas/channel.py` — channel_type 正则加 11 个 publisher 类型
- `services/channel_service.py` — create/update 加密敏感 key（webhook/token/secret/cookie 等），API 响应脱敏(********)，新增 `get_channel_config`(返回解密明文供 dispatch)
- `publish/service.py` dispatch — payload 带 `channel_id` 时从 DB 查 Channel → 解密 → 注入 channel_config（**唯一桥接点**，~15 行）
- **自测**: 加密/解密/脱敏 round-trip 全通过

**子系统2: 批量分发（list-accounts + batch 节点）**
- `skills/list-accounts/` — async run 查 DB 该 provider 类型的所有 Channel → 返回 accounts 列表
- workflow batch 节点遍历 accounts，子节点 publish-content 用 `${item.channel_id}` 引用每个账号
- **零引擎改动**：batch 节点已支持 dict item

**子系统3: 内容采集 + KB 存储**
- `skills/web-fetch/main.py` — 新增 `async def run()`（workflow 可调），返回 markdown_content/title/url
- `skills/save-to-kb/` — async run 调 KnowledgeService.create_document 入库向量化
- web-fetch async 检测 ✅，复用 WebFetcher（延迟 import 不崩模块加载）

**子系统4: 每日发布简报**
- `skills/daily-summary/` — async run 查当天 SkillWorkflowRun → 遍历 output_payload 提取 publish 结果（含 batch 子节点）→ 聚合 provider/成功/失败 → 生成简报文本
- **自测**: 提取逻辑（直接节点 + batch 子节点）3 条记录全对；简报生成正确（含明细 ✅❌）

**新 workflow 模板（`data/publish_workflow_templates.py`，独立文件低耦合）:**
- `multi_account_publish` — 多账号批量分发（list-accounts → batch → publish）
- `keyword_collect` — 关键词采集+存库+简报（batch web-fetch → save-to-kb → writer → publish）
- `daily_briefing` — 每日发布简报（daily-summary → publish 飞书）

**全局自测（全通过）:**
- ✅ 后端全部语法编译
- ✅ 3 新模板注册
- ✅ 7 个 skill async 检测（6 async + read-uploads sync）
- ✅ Channel 加解密 round-trip
- ✅ daily-summary 提取+简报逻辑

**解耦验证（0 核心侵入）:**
- workflow_service.py: **0 改动**
- field_encryption.py: **0 改动**
- 现有 publisher: **0 改动**
- 每个新能力 = 独立 skill；桥接仅 dispatch 的 channel_id（15 行）

**新增文件:** web-fetch/main.py(改) / list-accounts / save-to-kb / daily-summary / publish_workflow_templates.py
**修改文件:** schemas/channel.py / channel_service.py / publish/service.py / workflow_templates.py

### [2026-06-25] 前端账号管理页 + 5 场景方案模板 — ✅

**前端：发布账号管理页（多账号 CRUD）**
- `src/frontend/src/pages/PublishingAccountsPage.tsx` — 精简 CRUD 页面（卡片网格 + 动态凭证表单 + 加密提示）
- `src/frontend/src/i18n/publishingAccountTypes.ts` — 11 个渠道的凭证字段元数据（敏感字段 password 类型 + 客户机/api 分类）
- `routes.tsx` — 注册 `/admin/publishing-accounts` 路由
- `Sidebar.tsx` — 加"发布账号"菜单项（Send 图标）
- `en.json`/`zh.json` — 加 `nav.publishingAccounts`
- **复用现有 Channel API + 自研 UI 组件**，前端过滤只显示 publisher 类型 channel

**5 个场景方案模板（`publish_workflow_templates.py`）:**
| 模板 | 场景 | 链路 |
|------|------|------|
| `intel_monitor` | 资讯情报监控 | 采集URL→存KB→AI简报→发飞书 |
| `social_media_matrix` | 社媒内容矩阵 | AI文案→查多账号→batch矩阵分发 |
| `customer_sentiment` | 客户舆情监控 | 采集评价→AI情感分析→简报发团队群 |
| `tech_intel` | 技术情报/知识沉淀 | 采集技术内容→存KB(长期RAG) |
| `product_promotion` | 产品推广全流程 | AI文案→飞书+小红书并行→汇总 |

**隔离确认:** uploads(KB) 均已天然按 user_id 隔离（tenant_uploads_dir / KnowledgeBase.user_id + _get_kb_row 越权校验），新 skill 走 workspace_context 取 user_id，无需额外改动。

**自测:** 5 场景模板 + 3 基础模板 = 10 个发布类模板全部注册；前端语法遵循现有模式（同 ChannelsPage 结构）。

**当前完整模板矩阵（10 个发布类）:**
- 基础: multi_account_publish / keyword_collect / daily_briefing
- 场景: intel_monitor / social_media_matrix / customer_sentiment / tech_intel / product_promotion
- 茶叶: tea_daily_publish / tea_daily_publish_en

### [2026-06-25] 全面检查测试（对接前）— ✅

**修复的 bug:**
- **F1 前端 lazy import 崩溃**: `export default` → `export function`（项目用 lazyNamed 取具名导出）
- **F2 平台下拉选择无效**: Select 组件是原生 `<select>`，onChange 收到 event 而非 value，改用 `e.target.value`
- **F3 客户机字段设计错误**: 去掉 client_id/cookie，改为 平台下拉(xiaohongshu/douyin/weibo) + 登录账号 + 登录密码；新增 select 字段类型

**全面测试结果（全通过）:**
| 类别 | 项 | 结果 |
|------|---|------|
| 语法 | 后端 27 + 客户机 10 + skill 7 = 44 文件 | ✅ |
| 后端运行时 | 11 publisher 注册 / dispatch 4 类错误 / 加解密脱敏 / channel_type 正则 / 10 模板 / 7 skill async / daily-summary 逻辑 | ✅ 8 项 |
| 客户机 | 3 runner 注册 / 选择器层 / media 解析 / 话题清洗 / trigger+schedule 子命令 | ✅ 5 项 |
| 前端 | vite build 成功(3.34s) / 具名导出 / Select onChange / select 字段渲染 | ✅ |
| 模板 DAG | 10 模板 nodes/edges 连通性 + start/end + batch 子节点 | ✅ |
| R3 告警 | 空池不告警 / 满载告警 / 冷却防刷屏 | ✅ |
| 真实 API | publish health / 10 模板 API 可见 / 客户机 claim 协议 | ✅ |

**系统就绪状态:** 全部子系统通过编译+运行时+API 三层验证，可对接联调。

### [2026-06-25] 对接联调 + 3 个关键修复 — ✅

**联调验证通过:**
- ✅ Channel 加密生效（.env 配 SECRETS_ENCRYPTION_KEY 后，DB 存 enc:v1: 加密）
- ✅ dispatch channel_id 桥接（用存储的加密账号自动解密发飞书，无需手写 webhook）
- ✅ 多账号分发（list-accounts → 2 个账号各发一条 → 飞书群收到 2 条）
- ✅ **真实 workflow 引擎 multi_account_publish：batch 遍历 2/2 成功**

**修复的 3 个关键 bug（联调发现）:**

- **F4 async skill 在 workspace provider 路径下没 await**: `_execute_python_tool` 里 fast-path 在 `ws_ctx is not None` 的 provider 分支**之后**，导致 async skill 走了 provider 路径返回 stringified coroutine。**修复**：fast-path 提前到 provider 分支之前。
- **F5 dispatch channel_config 跨 event loop**: `_load_channel_config` 用全局 async_session_factory，engine 绑定主 loop，workflow 后台 task 跨 loop 报 "Future attached to a different loop"。**修复**：改用同步 sqlalchemy engine（pymysql + asyncio.to_thread），loop-free。
- **F6 asyncio 未 import**: service.py 漏 `import asyncio`（to_thread 需要）。已补。

**配置补充:** `.env` 加 `SECRETS_ENCRYPTION_KEY`（Fernet key），否则加密是空操作（encrypt_value 直接返回明文）。

**当前完整联调状态:**
| 能力 | 验证 |
|------|------|
| Channel 加密存储 | ✅ DB enc:v1: |
| dispatch channel_id 桥接 | ✅ 自动取解密凭证 |
| 多账号 batch 分发 | ✅ workflow 2/2 |
| 前端账号管理页 | ✅ 可用（修复 lazy/onChange/select 3 bug）|

### [2026-06-26] 生产部署 + 性能优化（API 从 1.7s→50ms）— ✅

**部署:**
- 备份 DB(12M)+data(336M)+skills(40M)+.env 到服务器本机
- 部署升级成功（migrate + 7 新 skill + publish 路由）
- nginx 静态资源本地直供（8.12 边缘 nginx）
- 部署脚本加自动同步 dist 到 8.12

**性能优化（4 个根因，全部修复）:**

| 问题 | 根因 | 修复 | 效果 |
|------|------|------|------|
| bcrypt 阻塞 event loop | `verify_password` 在 async 里同步调，冻住 1.5s | `verify_password_async` 放线程池 | 登录不再阻塞其它请求 |
| User 模型 15 个 selectin | 每次 `db.get(User)` 触发 13+ SQL 全量加载 messages/skills/channels | 全改 `lazy="select"` | **所有 API 快 7-45 倍** |
| ORM 关系 selectin 过度加载 | Skill/Workflow/Channel 模型 selectin 加载不需要的关联 | 改 `lazy="select"` | 减少无谓查询 |
| 限流阈值过低 | 60次/60秒，页面加载十几请求就触发 | 调到 300/60秒 | 不再误伤正常使用 |

**性能提升（生产实测）:**
| 接口 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| /api/skills | 989ms | 59ms | 17x |
| /api/workflows | 1655ms | 37ms | 45x |
| /api/channels | 893ms | 21ms | 43x |
| /api/dashboard/stats | 907ms | 43ms | 21x |
| /api/workspace/users | 1935ms | 209ms | 9x |

**修改文件:** security.py, auth_service.py, user.py, skill.py, workflow.py, channel.py, config.py, deploy-remote-cloud.sh

### [2026-06-26] 业务闭环：用户付费开通发布推广功能 — ✅

**目标:** 普通用户在 portal 购买发布套餐（1元/年5账号、2元/年10账号）→ 开通后添加发布账号 + 用推广工作流自动发内容。

**复用度 ~85%**（套餐体系+支付+配额gate全现成，只补了发布账号权限和数量配额）

**实施（5步）:**

- **步骤1 字段+迁移**: ChannelTemplate + CustomerConfig 加 `max_publishing_accounts`（0=无发布权限），migrations.py 补 ALTER TABLE
- **步骤2 套餐模板**: 创建两条 ChannelTemplate（推广基础版100分/年5账号、推广标准版200分/年10账号），category=promotion，is_published=true
- **步骤3 gate**: `publish/entitlements.py` — `ensure_can_manage_publishing_accounts`（检查套餐）+ `ensure_within_publishing_quota`（检查账号数）。admin/agent 无限，普通用户按套餐
- **步骤4 portal API**: `cloud/api/portal.py` 加 `/publishing-accounts` CRUD（GET/POST/PUT/DELETE + entitlement 查询）。复用 ChannelService（加密已就绪），只允许 publisher 类型
- **步骤5 前端**: PortalRoutes 加 `/portal/publishing-accounts` + `/portal/workflows` + `/portal/workflow-center`；UserLayout 菜单接通；PublishingAccountsPage 动态适配 portal API（isPortal 判断）

**验证通过:**
- ✅ 推广基础版/标准版模板创建（1元/5账号、2元/10账号）
- ✅ admin entitlement allowed=True max=999（不受限）
- ✅ portal 创建发布账号成功
- ✅ 未开通套餐返回 402 + 升级引导（gate 生效）
- ✅ admin_templates schema 支持 max_publishing_accounts（create+update+response）

**新增文件:** `app/publish/entitlements.py`
**修改文件:** channel_template.py, customer.py, migrations.py, portal.py, portal_service.py, admin_templates.py, portal.py(schema), routes.tsx, UserLayout.tsx, PublishingAccountsPage.tsx, en/zh.json

**用户完整使用流程:**
1. 注册登录 → /portal/templates 看到"推广基础版1元/年""推广标准版2元/年"
2. 开通 → 支付宝/微信支付 → plan=pro + 5/10发布账号配额
3. /portal/publishing-accounts → 添加小红书/飞书账号（受配额限制）
4. /portal/workflows → 从"社媒内容矩阵"等模板创建工作流
5. Run once / 挂定时 → 自动发内容到小红书/飞书

---

## P1 检查清单 ✅

- [x] `app/publish/base.py` — 数据契约
- [x] `app/publish/registry.py` — 注册表
- [x] `app/publish/service.py` — 门面
- [x] `app/publish/publishers/feishu.py` — 飞书
- [x] `app/publish/publishers/playwright_client.py` — 客户机派发
- [x] `app/publish/client/protocol.py` + `dispatcher.py` — 客户机协议骨架
- [x] `skills/publish-content/` — 唯一入口 skill
- [x] `skills/read-uploads/` — 读上传区
- [x] `skills/content-writer/` — LLM 生成
- [x] 茶叶推送 workflow 模板(中/英)
- [x] 运行时冒烟验证通过
- [ ] 真实飞书 webhook 端到端联调(待用户)

---

## P2 待办

- [ ] 客户机 HTTP 端点:`POST /api/publish/jobs/claim`、`/result`、`GET /status`
- [ ] `publisher-client/` 独立程序骨架(agent.py Pull 循环 + config.toml)
- [ ] 更多 API publisher:wechat_mp / slack / telegram_channel / discord / twitter_x
- [ ] 客户机 dispatcher 换持久化后端(Redis/DB),支持多 worker

## P3 待办

- [ ] `publisher-client/runners/xiaohongshu.py` Playwright runner
- [ ] `publisher-client/runners/douyin.py`
- [ ] 持久化登录态/cookies/指纹管理
- [ ] 模拟人节奏(随机延迟、滚动、停留)

## P4 待办

- [ ] 平台风格化内容生成质量调优(小红书 emoji/标签节奏、海外本地化语言)
