---
name: mchat-notify
description: 短信通知（默认 dev 仅写日志）。仅管理员且在系统设置中启用；手机号须在白名单。真发短信请安装本地 provider 插件。
type: tool
scope: notification
requires_admin: true
parameters: {"type":"object","properties":{"command":{"type":"string","enum":["ping","send","workflow_alert"]},"phone":{"type":"string"},"provider":{"type":"string","enum":["dev","auto"]},"content":{"type":"string"},"workflow_name":{"type":"string"},"event":{"type":"string"},"run_id":{"type":"string"},"message":{"type":"string"}},"required":["command","phone"]}
---

# MChat 短信通知

平台内置 `NotificationService` 发送短信，用于 Workflow 测试、运行失败告警等。

## 子命令

- `ping` — 发送测试短信「MChat notify ping」
- `send` — 发送 `content` 正文（≤500 字；dev 或已安装的文本类 provider）
- `workflow_alert` — 使用工作流告警模板（`workflow_name` / `event` / `run_id` / `message`）

## 配置

系统设置 → **安全**：启用通知 skill、手机号白名单、默认 provider（dev / auto）。

真发短信：复制 `docs/examples/notify-providers/*.example` 到 `providers/`（见 providers/README.md）。

## 安全

- 非 Widget/门户通道；仅管理员对话或 Workflow 节点
- 手机号必须在白名单；同号有发送冷却
