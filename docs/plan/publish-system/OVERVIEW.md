# MChat 内容自动分发系统 — 完整说明

> 本文档面向运维和开发，说明系统的完整能力、使用方式、待办事项。
> 最后更新：2026-06-27

---

## 一、系统概述

MChat 内容自动分发系统是一个多渠道内容自动化平台，支持：
- AI 生成文案/图片/视频 → 审批确认 → 自动发布到多个渠道
- 多账号管理（一个用户管理 N 个同渠道账号）
- 付费套餐（1元/年5账号、2元/年10账号）
- 发送记录统计

**生产地址**：https://mchat.9235.net

---

## 二、发布渠道（13个 + 客户机）

### API 类渠道（中心直接发送，合规）
| 渠道 | provider_key | 状态 | 需要的凭证 |
|------|-------------|------|-----------|
| 飞书 | `feishu` | ✅ 已联调 | 群机器人 Webhook URL |
| 钉钉 | `dingtalk` | 代码就绪 | 群机器人 Webhook + 加签密钥 |
| 企业微信 | `wecom` | 代码就绪 | 群机器人 Key |
| 微信公众号 | `wechat_mp` | 代码就绪 | app_id + app_secret（需认证服务号）|
| Slack | `slack` | 代码就绪 | Incoming Webhook URL |
| Discord | `discord` | 代码就绪 | 频道 Webhook URL |
| Telegram | `telegram_channel` | 代码就绪 | Bot Token + Channel ID |
| X/Twitter | `twitter_x` | 代码就绪 | OAuth2 Access Token |
| Facebook | `facebook` | 代码就绪 | Page ID + Page Access Token |
| LinkedIn | `linkedin` | 代码就绪 | Access Token + Author URN |

### 客户机类渠道（Playwright 浏览器自动化）
| 渠道 | platform | 状态 | 需要 |
|------|----------|------|------|
| 小红书 | `xiaohongshu` | ✅ 已联调 | 客户机登录（手机验证码）|
| 抖音 | `douyin` | 代码就绪 | 客户机登录 + DOM 校准 |
| 微博 | `weibo` | 代码就绪 | 客户机登录 + DOM 校准 |

### 媒体生成（客户机 ComfyUI/API）
| 类型 | provider_key | 状态 | 需要 |
|------|-------------|------|------|
| 图片生成 | `image_client` | 代码就绪 | ComfyUI API JSON 工作流 |
| 视频生成 | `video_client` | 代码就绪 | ComfyUI API JSON 工作流 |

---

## 三、用户使用流程

### 普通用户
1. 注册登录 mchat.9235.net（role=user）
2. 访问 `/portal/templates` → 选择"推广基础版(1元/年)"或"推广标准版(2元/年)"
3. 支付宝/微信扫码支付 → 开通成功
4. `/portal/publishing-accounts` → 添加发布账号（飞书/小红书等，受配额限制）
5. `/portal/workflows` → 从模板创建工作流（如"社媒内容矩阵"）
6. 执行工作流 → Run once 或挂定时任务

### 管理员
1. `/admin/publishing-accounts` → 管理所有发布账号（不受配额限制）
2. `/admin/send-records` → 查看全平台发送记录与统计
3. `/admin/templates` → 管理套餐模板（定价、账号数配额）

---

## 四、工作流模板（15个）

### 基础模板
| 模板 | 说明 |
|------|------|
| `multi_account_publish` | 一篇内容 → 查询全部账号 → 并发分发到每个账号 |
| `keyword_collect` | 批量抓取URL → 存知识库 → AI生成简报 → 发飞书 |
| `daily_briefing` | 每日发布汇总 → 发飞书 |

### 场景模板
| 模板 | 说明 |
|------|------|
| `intel_monitor` | 资讯情报监控（市场/运营/PR） |
| `social_media_matrix` | 社媒内容矩阵（电商/品牌） |
| `customer_sentiment` | 客户舆情监控（客服/产品） |
| `tech_intel` | 技术情报/知识沉淀（技术团队） |
| `product_promotion` | 产品推广全流程（综合） |

### 审批模板
| 模板 | 说明 |
|------|------|
| `review_then_publish` | AI生成 → 审批确认 → 发布 |
| `content_draft_review` | 完整提示词 → AI生成 → 存待选 → 审批 → 发布 |
| `n_pick_one_publish` | AI生成多篇 → 用户选1篇 → 只发选中的 |

### 媒体模板
| 模板 | 说明 |
|------|------|
| `video_generate_review` | 提示词 → 客户机生成视频 → 审批 → 发布 |
| `image_generate_review` | 提示词 → 客户机生成图片 → 审批 → 发布 |

### 茶叶模板
| 模板 | 说明 |
|------|------|
| `tea_daily_publish` | 茶叶日报多渠道推送（飞书+小红书） |
| `tea_daily_publish_en` | 英文版 |

---

## 五、客户机配置

### 安装
```bash
cd publisher-client
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

### 配置
编辑 `config.toml`：
```toml
platforms = ["xiaohongshu", "image:comfyui", "video:comfyui"]

[center]
url = "https://mchat.9235.net"
token = "<JWT token from /api/auth/login>"

[client]
id = "macbook-local"

[comfyui]
server_url = "http://127.0.0.1:8000"
output_dir = "/Users/xiaoxiao/ComfyUI/output"
# text_to_image_workflow = "workflows/t2i.json"
```

### 首次登录（小红书/抖音/微博）
```bash
.venv/bin/python -m runners.login xiaohongshu   # 打开浏览器手动登录
```

### 运行
```bash
.venv/bin/python agent.py              # 持续轮询
.venv/bin/python agent.py --dry-run    # 测试（不实际发布）
.venv/bin/python agent.py --trigger <workflow_id> '<payload_json>'  # 一次性触发
.venv/bin/python agent.py --schedule   # 定时触发工作流
```

---

## 六、套餐定价

| 套餐 | 年费 | 发布账号数 | 工作流配额 |
|------|------|-----------|-----------|
| 推广基础版 | ¥1/年 | 5个 | 30个工作流 / 500次/月 |
| 推广标准版 | ¥2/年 | 10个 | 30个工作流 / 500次/月 |

- admin/agent 角色不受配额限制
- 配额存储在 ChannelTemplate.max_publishing_accounts → 开通时复制到 CustomerConfig
- gate 在 `app/publish/entitlements.py`

---

## 七、关键文件索引

### 后端
| 文件 | 说明 |
|------|------|
| `app/publish/` | 发布系统核心（base/registry/service/entitlements/drafts） |
| `app/publish/publishers/` | 13个 API publisher + playwright_client + video_client + image_client |
| `app/publish/client/` | 客户机协议（protocol/dispatcher） |
| `app/api/publish.py` | 客户机 API（claim/result/video-upload） |
| `app/api/health.py` | 健康检查 + skills_pool 监控 |
| `app/models/publish_record.py` | 发送记录表 |
| `cloud/api/portal.py` | portal 发布账号 + 发送记录 + 草稿 API |
| `cloud/services/portal_service.py` | 套餐开通（rent_channel） |
| `app/services/channel_service.py` | Channel CRUD（加密/解密/脱敏） |
| `app/services/workflow_entitlements.py` | 工作流配额 gate |
| `app/data/publish_workflow_templates.py` | 15个工作流模板 |

### Skill（9个）
| Skill | 说明 |
|-------|------|
| `skills/read-uploads/` | 读上传区资料（支持日期模板 tea/{yyyy.MM.dd}） |
| `skills/content-writer/` | AI生成文案（4种风格 + DeepSeek reasoning_effort） |
| `skills/multi-content-writer/` | 生成N篇候选（N选1用） |
| `skills/publish-content/` | 发布到渠道（唯一接缝，支持 channel_id + draft） |
| `skills/list-accounts/` | 查询用户的发布账号列表 |
| `skills/save-to-kb/` | 存入知识库（向量化） |
| `skills/daily-summary/` | 每日发布汇总 |
| `skills/generate-video/` | 视频生成（提交客户机） |
| `skills/generate-image/` | 图片生成（提交客户机） |

### 客户机
| 文件 | 说明 |
|------|------|
| `publisher-client/agent.py` | 主进程（Pull轮询 + trigger + schedule） |
| `publisher-client/runners/xiaohongshu.py` | 小红书发布（已验证全自动） |
| `publisher-client/runners/douyin.py` | 抖音发布（待DOM校准） |
| `publisher-client/runners/weibo.py` | 微博发布（待DOM校准） |
| `publisher-client/runners/video.py` | 视频/图片生成（ComfyUI + 占位） |

### 前端
| 文件 | 说明 |
|------|------|
| `src/pages/PublishingAccountsPage.tsx` | 发布账号管理（portal+admin） |
| `src/pages/portal/SendRecordsPage.tsx` | portal 发送记录 |
| `src/pages/SendRecordsAdminPage.tsx` | admin 发送汇总 |
| `src/routes-portal.tsx` | portal 路由（含发布账号/发送记录/工作流） |

---

## 八、待办事项

### 需要配合的
- [ ] **渠道联调**：提供钉钉/企微/Discord webhook URL 测真实发送
- [ ] **抖音/微博**：在客户机 login 一次，校准 DOM 选择器
- [ ] **ComfyUI**：从界面导出 API JSON 工作流接入图片/视频生成

### 后续优化
- [ ] 视频 N选1（当前是单篇审批，扩展成生成N个视频选1个）
- [ ] 客户机 dispatcher 持久化（Redis，支持多worker）
- [ ] 前端工作流编辑器优化（更多字段类型、批量操作）
- [ ] 发布账号分组（按渠道/用途分组管理）

---

## 九、性能优化记录

| 优化 | 效果 |
|------|------|
| bcrypt 异步化 | 登录不再阻塞 event loop 1.5s |
| User 模型 15个 selectin→select | 所有 API 快 7-45 倍 |
| ORM 关系 lazy 加载 | skills/workflows/channels 快 17-45 倍 |
| 限流 60→300/分钟 | 不再误伤正常使用 |
| nginx 静态资源边缘直供 | 静态资源 72ms→2ms |

---

## 十、文档索引

- `docs/plan/publish-system/README.md` — 设计原则与拓扑
- `docs/plan/publish-system/ARCHITECTURE.md` — 数据契约与接口
- `docs/plan/publish-system/PROGRESS.md` — 开发日志（决策记录 + 每轮成果）
- `docs/plan/publish-system/SKILL-EXEC-RISK.md` — Skill 执行风险分析
- `docs/plan/publish-system/CHANNEL-SETUP-GUIDE.md` — 渠道申请指南
