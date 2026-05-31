# 短信通知（mchat-notify）

Core 仅内置 **dev**（写日志，不发真短信）。公有仓库**不包含** SMSbao、阿里云等厂商实现；私有部署可按需安装 provider 插件。

## 快速测试（dev 模式）

1. **系统设置 → 安全**：启用「短信通知技能」，填写手机号白名单（必填），保存  
2. **技能管理 → 重新加载**，启用 `mchat-notify`  
3. **Workflow → 模板**：选用「短信通知 Ping 测试」，填入白名单内手机号，运行  
4. 查看 **执行详情** 或后端日志中的 `[dev-sms]` 行  

无需配置任何厂商账号即可验证整条链路。

## 真发短信（私有部署）

```bash
# 示例：短信宝（勿提交 git）
cp docs/examples/notify-providers/smsbao.py.example \
   skills/mchat-notify/providers/smsbao.py
# 编辑 smsbao.py / .env 填入账号；providers/*.py 已在 .gitignore
```

| 步骤 | 说明 |
|------|------|
| 复制 example | `docs/examples/notify-providers/*.py.example` → `skills/mchat-notify/providers/` |
| 环境变量 | 如 `SMSBAO_USERNAME` / `SMSBAO_PASSWORD` 写在 `.env`，勿提交 |
| Provider 选择 | 设置里选 `auto`（依次尝试已安装的 smsbao、aliyun、custom）或指定名称 |
| 阿里云模板 | 复制 `aliyun.py.example`；需配置 `ALIYUN_SMS_*`（与登录 OTP 可共用 AK，模板独立） |

## 配置项

### 环境变量（`src/backend/.env`）

| 变量 | 说明 |
|------|------|
| `SMS_DEFAULT_PROVIDER` | `dev`（默认）或 `auto` / 已安装插件名 |
| `SMS_WORKFLOW_ALERT_ENABLED` | Workflow 失败是否发短信 |

### 管理后台（系统设置 → 安全）

- 启用「短信通知技能」
- 手机号白名单（必填）
- Workflow 告警接收号
- 默认 provider、Workflow 失败短信开关

## Workflow 拓扑

```text
start → mchat-notify (command=ping, phone=${input.alert_phone}) → end
```

内置模板 id：`notify_ping_test`。

或在失败告警路径：配置 Workflow 失败短信 + 告警手机号，无需单独节点。

## Skill 子命令

| command | 说明 |
|---------|------|
| `ping` | 测试短信 |
| `send` | 自定义内容（≤500 字；dev / 文本类 provider） |
| `workflow_alert` | 告警模板 |

## 安全

- `scope: notification`，仅管理员；Widget/频道不可用
- 手机号白名单 + 冷却（默认 60s）
- 审计表 `sms_send_logs`

## 相关代码

- `app/services/notification_service.py`
- `app/services/notification_providers.py`
- `app/services/sms/dev.py`
- `skills/mchat-notify/`
- `docs/examples/notify-providers/`

## 与站内提醒的区别

| | 短信（本文档） | 会话收件箱 |
|--|----------------|------------|
| 场景 | Workflow 节点、运行失败告警 | 访客新消息、管理员介入 |
| 接收 | 手机号 | 登录后台的用户 |
| 文档 | 本文档 | [inbox-notifications.zh.md](inbox-notifications.zh.md) |
