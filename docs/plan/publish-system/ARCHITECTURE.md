# 架构设计 — 内容自动分发系统

## 1. 模块与文件清单

### 1.1 中心侧 `src/backend/app/publish/`

| 文件 | 职责 |
|------|------|
| `base.py` | 数据契约:`PublishRequest`、`PublishResult`、`BasePublisher` 抽象基类。镜像 `channels/base_adapter.py`。 |
| `registry.py` | 发布器注册表 `PublisherProvider(key,title,capabilities,factory)`。镜像 `services/devbridge_registry.py`。 |
| `service.py` | 对外门面 `publish_service.dispatch(provider, config, request)` → 选 publisher → publish。 |
| `publishers/__init__.py` | 注册所有内置 API 发布器。 |
| `publishers/feishu.py` | 飞书群机器人 webhook(文字 + 富文本卡片)。 |
| `publishers/wechat_mp.py` | 微信公众号(P2) |
| `publishers/slack.py` | Slack incoming webhook(P2) |
| `publishers/telegram_channel.py` | Telegram bot→channel(P2) |
| `publishers/discord.py` / `twitter_x.py` / `facebook.py` / `linkedin.py` | 海外渠道(P2) |
| `publishers/playwright_client.py` | 统一转发给远端客户机(P2/P3)。调 `client/dispatcher.py`。 |
| `client/protocol.py` | 客户机任务/结果 JSON schema(版本化)。 |
| `client/dispatcher.py` | 派发任务 + 轮询/收结果。 |

### 1.2 Skill `skills/publish-content/`

| 文件 | 职责 |
|------|------|
| `SKILL.md` | 声明参数:`provider`/`channel_config`/`content`/`media`/`mode`。`type: tool`。 |
| `main.py` | 调 `publish_service.dispatch(...)`。这是平台↔发布唯一接缝。 |

### 1.3 Skill `skills/read-uploads/`

读租户上传区本地资料(`tea/{yyyy.MM.dd}`),日期模板渲染。

### 1.4 Skill `skills/content-writer/`

"提示词模板 + 资料 → 平台风格文案",内部调 bot engine 的 LLM。

### 1.5 客户机 `publisher-client/`(独立)

| 文件 | 职责 |
|------|------|
| `agent.py` | Pull 模式:轮询中心拉任务 → 执行 → 回传。 |
| `runners/*.py` | 每平台一个 Playwright runner。 |
| `browser_data/` | 持久化登录态/cookies/指纹(每平台独立 profile)。 |
| `config.toml` | 中心地址、平台列表、代理。 |

## 2. 数据契约

### 2.1 `PublishRequest`(`base.py`)

```python
@dataclass
class PublishMedia:
    type: str            # "image" | "video" | "file"
    url: str | None      # 远端 URL 或同源 /uploads 路径
    path: str | None     # 本地绝对路径(客户机场景)
    caption: str | None

@dataclass
class PublishRequest:
    content: str                      # 正文(必填)
    title: str | None = None          # 可选标题
    media: list[PublishMedia] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # 渠道专属字段(tags/topic/...)
    request_id: str = ""              # 追踪用(P2)
```

### 2.2 `PublishResult`

```python
@dataclass
class PublishResult:
    success: bool
    provider: str
    message: str = ""
    remote_id: str | None = None      # 平台返回的内容ID
    remote_url: str | None = None     # 发布后的链接
    raw: dict = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
```

### 2.3 `BasePublisher`

```python
class BasePublisher(ABC):
    provider_key: str = ""
    capabilities: tuple[str, ...] = ("publish:text",)

    @abstractmethod
    async def publish(self, config: dict, request: PublishRequest) -> PublishResult: ...

    async def validate_config(self, config: dict) -> bool: return True
```

### 2.4 渠道凭证存储

**复用现有 `Channel` 模型,不新建表**(最小耦合):

```
Channel.channel_type = "publisher"
Channel.config = {
  "provider": "feishu",                 # 或 "playwright_client"
  "webhook_url": "https://open.feishu.cn/...",   # API 类
  # 客户机类:
  # "platform": "xiaohongshu",
  # "client_id": "mac-01"
}
```

P1 不依赖 Channel 表(skill 节点 payload 直接带 `channel_config`),只是约定好将来可迁。规模上来后再建独立 `publish_jobs` 表。

## 3. 客户机协议(Pull 模式,P2)

中心侧三个端点(挂在 `/api/publish/` 下):

- `POST /jobs/claim` — 客户机拉一个待执行任务(`platform`, `request`, 超时)。返回 `{job_id, runner, payload}` 或空。
- `POST /jobs/{job_id}/result` — 客户机回传结果(`PublishResult`)。
- `GET /jobs/{job_id}` — 查询状态。

`client/protocol.py` 定义任务 schema(版本字段 `protocol_version`),保证中心/客户机演进兼容。

**为什么 Pull**:客户机主动连中心,无需在客户机开端口/穿 NAT,与"连到 mac mini"拓扑契合;客户机天然适配多机水平扩展。

## 4. 风险与合规

| 渠道 | 风险 | 处置 |
|------|------|------|
| 小红书/抖音/视频号 | 无官方发布 API,自动化违反 ToS,封号风险 | 仅走客户机 + 持久化真实 profile + 真实 IP;**不做协议自动化**,Playwright 模拟人节奏 |
| 海外 API | 合规但需密钥管理 | secrets 走 skill config 加密(`field_encryption`) |

## 5. 与现有系统的接缝(唯一)

```
Workflow skill 节点
  payload_template:
    provider: "feishu"
    channel_config: {webhook_url: "${input.webhook}"}
    content: "${nodes.writer.result.content}"
  ↓
execute_skill(publish-content skill, payload)
  ↓
skills/publish-content/main.py
  ↓
publish_service.dispatch(...)
```

除这一个 skill 外,核心系统对发布能力零感知。
