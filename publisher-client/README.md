# Publisher-Client

独立客户机进程，为小红书/抖音等**无官方发布 API** 的平台提供 Playwright 自动发布能力。

## 为什么独立

- 浏览器自动化（反检测、cookie 持久化、模拟人节奏）很重很脏，不能跑在后端进程里
- 跑在真实用户机器（mac mini）上 + 持久化真实 profile + 真实 IP，才能"完全模拟人"
- 只主动连中心（Pull 模式），不开监听端口，穿 NAT 部署最简单

## 架构

```
MChat 中心 (/api/publish/jobs/*)
   ▲                                  │
   │ POST /result (回传结果)           │ POST /claim (拉任务)
   │                                  ▼
publisher-client/agent.py  ◄──►  runners/xiaohongshu.py (Playwright)
   └─ browser_data/  (持久化登录态)
```

## 快速开始

```bash
cd publisher-client
cp config.example.toml config.toml
# 编辑 config.toml: 填 center.url / center.token

# 安装依赖
pip install playwright
playwright install chromium

# 测试拉取（不实际发布）
python agent.py --dry-run

# 正式运行（持续轮询）
python agent.py
```

## 首次登录（建立持久 profile）

每个平台首次使用需要人工登录一次，之后 cookie 持久化：

```bash
python -m runners.login xiaohongshu   # 打开浏览器手动登录，关闭后保存
```

> login 工具 P3 实现。

## 开发新 runner

```python
# runners/xiaohongshu.py
from runners import BaseRunner, register

@register("xiaohongshu")
class XiaohongshuRunner(BaseRunner):
    def publish(self, job):
        # 用持久化 profile 打开浏览器 → 模拟点击发布 → 填内容/图 → 提交
        ...
        return {"success": True, "message": "已发布", "remote_id": "..."}
```

## API 端点（中心侧）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/publish/jobs/claim` | 客户机拉一个待执行任务 |
| POST | `/api/publish/jobs/{id}/result` | 客户机回传结果 |
| GET | `/api/publish/jobs/{id}` | 查询任务状态 |
| GET | `/api/publish/health` | 子系统健康检查 |

## 安全

- 登录态/cookie **只存在客户机本地**，从不上传中心
- 客户机通过 JWT token 鉴权（config.toml 配置）
- 内容经 HTTPS 下发（生产环境）

## 状态

- ✅ 中心侧协议 + API + dispatcher（P2）
- ✅ 客户机骨架 + Pull 主循环（P2）
- ⏳ Playwright runner 实现（P3）：xiaohongshu / douyin
- ⏳ 首次登录工具（P3）
