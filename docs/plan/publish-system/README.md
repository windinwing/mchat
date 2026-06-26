# 内容自动分发系统(Content Auto-Publish System)

> 本目录是该功能的长程开发档案。**每完成一个模块,必须更新 `PROGRESS.md`**。

## 一句话目标

用户登录后:设置提示词 / 指定资料(上传区 `tea/{yyyy.MM.dd}` 或 `web-fetch` 抓取)→ 自动生成文案 → 分发到国内外渠道(飞书/公众号/小红书…)。用现有 Workflow 编排 + Schedule 定时器驱动。

## 设计原则(不可妥协)

1. **零侵入核心** — Workflow 引擎、调度器、channel 适配器一行不改。发布能力只通过 **1 个 skill** 暴露。
2. **单向被调用** — `app/publish/` 是叶子模块,只被 `publish-content` skill 调用,不反向依赖任何核心模块。
3. **镜像现有模式** — 发布器注册表镜像 `app/services/devbridge_registry.py` 的 provider 模式;发布抽象镜像 `app/channels/base_adapter.py` 但方向相反(outbound)。
4. **采集不重建** — 远端抓取复用 `skills/web-fetch`(已支持 SOCKS5 代理)。仅新增"读上传区本地资料"的薄 skill。
5. **客户机独立** — 浏览器自动化(Playwright)跑在独立进程/独立机器(如 mac mini),与中心进程解耦。中心不跑浏览器。

## 模块拓扑

```
Workflow 引擎 (不改)
   │ 调用 skill 节点
   ▼
skills/publish-content        ← 平台↔发布能力的唯一接缝
   │
   ▼
app/publish/                  ← 中心侧发布抽象 (独立垂直模块)
   ├── service.py  (门面 dispatch)
   ├── registry.py (镜像 devbridge_registry)
   ├── base.py     (PublishRequest/Result/BasePublisher)
   ├── publishers/ (API 类: feishu/wechat_mp/slack/...)
   └── client/     (playwright 派发: protocol + dispatcher)

publisher-client/             ← 独立客户机进程 (不在核心代码库)
   ├── agent.py    (Pull 模式轮询中心)
   └── runners/    (Playwright: xiaohongshu/douyin/...)
```

## 渠道矩阵

| 渠道 | 实现 | 协议 | 阶段 |
|------|------|------|------|
| 飞书 | API | 群机器人 webhook / 开放平台 | P1 ✅ |
| 企业微信 | API | 机器人 webhook | P2 |
| 微信公众号 | API | 素材+发布(认证服务号) | P2 |
| Slack / Telegram / Discord | API | webhook / bot | P2 |
| X(Twitter) / Facebook / LinkedIn | API | 官方 API | P2 |
| 小红书 / 抖音 / 视频号 | **客户机** | Playwright | P3 |

## 分阶段

- **P1 MVP**: `app/publish/` 抽象 + 飞书 publisher + `publish-content` skill + `read-uploads`/`content-writer` skill + 茶叶推送 workflow 模板 → Schedule 定时跑通闭环。
- **P2**: 多 API 渠道 + 客户机骨架(Pull 协议 + hello runner)。
- **P3**: 小红书/抖音 Playwright runner 实战。
- **P4**: 平台风格化内容生成质量优化。

## 文档索引

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — 详细架构、数据模型、接口契约
- [`PROGRESS.md`](./PROGRESS.md) — 开发日志(回溯用,每个模块完成即更新)
