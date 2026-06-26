# 各发布渠道凭证申请指南

> 拿到 webhook/token 后给我，我直接测。每个渠道约 2-3 分钟。

---

## 1. 钉钉群机器人（最快）

1. 打开钉钉 → 进入一个**群聊**（没有就建个测试群）
2. 点右上角 **群设置**（⚙️）→ **机器人**
3. 点 **添加机器人** → 选 **自定义**（通过 webhook 接入）
4. 机器人名字随便填（如"MChat"）→ **安全设置**勾"加签"→ **完成**
5. 会给你一个 **webhook URL**：`https://oapi.dingtalk.com/robot/send?access_token=xxx`
6. 还有一个 **加签密钥**（SEC 开头）：`SECxxxxxxxx`

**给我：** webhook URL + 加签密钥

---

## 2. 企业微信群机器人

1. 打开企业微信 → 进入一个**群聊**
2. 点右上角 **···** → **群机器人**
3. 点 **添加** → 起个名字 → **添加**
4. 复制 **webhook 地址**：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`

**给我：** webhook URL（或只要 key）

---

## 3. Discord Webhook

1. 打开 Discord → 进入一个**服务器/频道**
2. 频道设置（⚙️）→ **整合 / Integrations** → **Webhooks**
3. 点 **New Webhook** → 起个名字 → **复制 Webhook URL**
   URL：`https://discord.com/api/webhooks/xxx/xxx`

**给我：** webhook URL

> 不需要 Discord 账号也能注册，免费。

---

## 4. Slack Incoming Webhook

1. 打开 Slack → 建一个**频道**（如 #mchat-test）
2. 访问 https://api.slack.com/apps → **Create New App** → **From scratch**
3. App 名随便 → 选你的 Workspace → **Create App**
4. 左侧 **Incoming Webhooks** → 打开开关 → **Add New Webhook to Workspace**
5. 选频道 → **Allow** → 复制 **webhook URL**
   URL：`https://hooks.slack.com/services/Txxx/Bxxx/xxx`

**给我：** webhook URL

> 需要 Slack 账号 + Workspace（免费版即可）。

---

## 5. Telegram Bot → Channel

1. Telegram 里搜 **@BotFather** → 发 `/newbot`
2. 给 bot 起名 → 拿到 **Bot Token**：`123456789:ABCdefGHIjklMNOpqr...`
3. 新建一个**频道**（Channel）→ 把你的 bot 设为**管理员**（否则发不了消息）
4. 频道的 **@username** 或 **chat_id**（数字 ID）

**给我：** Bot Token + 频道 @username（或 chat_id）

> Telegram 在国内需要代理（和我给 web-fetch 配的代理类似）。

---

## 6. 飞书（已配置 ✅）

你已有：`https://open.feishu.cn/open-apis/bot/v2/hook/5bdd63a7-...`

---

## 7. X / Twitter（需开发者账号，较麻烦）

1. 访问 https://developer.x.com → 申请开发者账号（需审核，可能要等）
2. 创建 App → 拿 **OAuth2 access_token**（需 tweet.write scope）
3. 或用现有 token

**这个最麻烦**，建议放最后。

---

## 8. Facebook / LinkedIn / 微信公众号

这三个都需要：
- Facebook：需 Page + 开发者 App + Page Access Token
- LinkedIn：需开发者 App + OAuth2（w_member_social scope）+ person URN
- 公众号：需认证的服务号/订阅号 + app_id/app_secret

**建议先跳过**，等核心渠道测完再说。

---

## 优先级建议

**先测这些（最快、2 分钟搞定）：**
1. ✅ 钉钉（国内最常用）
2. ✅ 企业微信
3. ✅ Discord（海外测试）

**其次：**
4. Slack
5. Telegram

**最后（需申请/审核）：**
6. X / Facebook / LinkedIn / 公众号
