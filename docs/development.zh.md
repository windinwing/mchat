# mchat 开发指南

## 本地开发环境搭建

### 1. 克隆项目

```bash
git clone https://github.com/your-org/mchat.git
cd mchat
```

### 2. 系统依赖（新机器）

**Ubuntu / Debian：**

```bash
sudo apt update
sudo apt install -y git make python3 python3-venv python3-pip docker.io docker-compose-plugin
# Node.js 20+：见 https://nodejs.org/ 或使用 nvm
```

### 3. 一键搭建（推荐）

在项目根目录：

```bash
make setup   # lite MySQL、同步 .env、install、建表
make dev     # 本地热重载
# 或 Docker 全栈: make docker-up-lite
```

等价于 `bash ops/scripts/setup.sh` + `make dev`。

### 4. 手动搭建

#### 启动开发数据库

```bash
make db-mysql-dev   # 仅启动 lite MySQL（与 make setup 相同容器）
```

#### 后端开发

```bash
make install
# 或手动（与 make 相同，使用 source）:
cd src/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
python -m app.cli db init
uvicorn app.main:app --reload --port 3001
```

加载项目环境后可使用短命令：

```bash
source scripts/env.sh
mchat skill list
```

### 5. 前端开发

```bash
cd src/frontend
npm install
npm run dev  # 启动在 http://localhost:5173
```

### 6. 访问

- 前端: http://localhost:5173
- 后端 API: http://localhost:3001
- API 文档 (Swagger): http://localhost:3001/docs
- API 文档 (ReDoc): http://localhost:3001/redoc

---

## 项目结构约定

### Python 代码规范

- 使用 Python 3.12+ 类型注解
- 异步函数使用 `async/await`
- 遵循 PEP 8 风格
- 使用 `black` 格式化代码（推荐）
- 使用 `ruff` 进行 lint

### 前端代码规范

- TypeScript 严格模式
- 组件使用函数式组件 + Hooks
- 使用 Tailwind CSS 进行样式编写
- 组件文件使用 PascalCase 命名

### Git 提交规范

```raw
feat: 新功能
fix: 修复 Bug
docs: 文档更新
style: 代码格式调整
refactor: 重构
test: 测试
chore: 构建/工具
```

### Git 双仓（简要）

| | `origin`（GitHub） | `private`（9235） |
|--|-------------------|-------------------|
| 分支 | `dev`（日常）+ `main`（由 `dev:main` 发布） | `main`、`feature/*`、完整 Cloud |
| 推送 | `git push origin dev` / `git push origin dev:main` | `git push private main` 等 |

克隆后执行 `make install-git-hooks`。hook 会限制：仅允许从本地 `dev` 推到 `origin/dev` 或 `origin/main`。

---

## 后端开发指引

### 添加新 API 路由

1. 在 `app/api/` 创建路由文件
2. 使用 FastAPI `APIRouter`
3. 在 `app/api/__init__.py` 中注册路由

```python
# app/api/example.py
from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/example", tags=["example"])

@router.get("/")
async def example_route(user: User = Depends(get_current_user)):
    return {"message": "Hello", "user": user.username}
```

### 添加新数据模型

1. 在 `app/models/` 创建模型文件
2. 继承 `Base` (SQLAlchemy declarative base)
3. 在 `app/models/__init__.py` 中导入

### 添加新 Service

```python
# app/services/example_service.py
from sqlalchemy.ext.asyncio import AsyncSession

class ExampleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def do_something(self, data: dict):
        # 业务逻辑
        pass
```

### 添加 LLM Provider

1. 在 `app/bot/provider.py` 中添加新 provider 类
2. 继承 `LLMProvider` 基类
3. 实现 `async_stream_chat()` 方法

```python
class MyProvider(LLMProvider):
    async def stream_chat(self, messages, **kwargs):
        # 实现流式对话
        pass
```

---

## 前端开发指引

### 组件结构

```raw
src/
├── components/
│   ├── ui/           # 基础 UI 组件
│   ├── chat/         # 聊天相关组件
│   ├── widget/       # Widget 嵌入组件
│   ├── admin/        # 管理后台组件
│   └── layout/       # 布局组件
├── pages/            # 页面组件
├── stores/           # Zustand 状态管理
├── hooks/            # 自定义 Hooks
├── lib/              # 工具函数
│   ├── api.ts        # API 客户端
│   ├── websocket.ts  # WebSocket 客户端
│   └── utils.ts      # 工具函数
└── styles/           # 样式文件
```

### 添加新页面

1. 在 `src/pages/` 创建页面组件
2. 在 `src/App.tsx` 添加路由

### 添加新 Store

```typescript
// src/stores/example.ts
import { create } from 'zustand'

interface ExampleState {
  data: any[]
  loading: boolean
  fetchData: () => Promise<void>
}

export const useExampleStore = create<ExampleState>((set) => ({
  data: [],
  loading: false,
  fetchData: async () => {
    set({ loading: true })
    // ... API call
    set({ data: result, loading: false })
  },
}))
```

---

## 技能开发

### 技能结构

```raw
skills/my-skill/
└── SKILL.md
```

### SKILL.md 格式

```markdown
---
name: my-skill
description: 我的技能描述
version: 1.0.0
tools:
  - name: my_tool
    description: 工具描述
    parameters:
      param1:
        type: string
        description: 参数1说明
      param2:
        type: integer
        description: 参数2说明
    handler: my_handler_function
prompts:
  - role: system
    content: |
      你具备以下能力：
      - 能力1
      - 能力2
---

# 技能说明

详细的使用说明和示例。
```
### OpenClaw 兼容格式

MChat 也支持 OpenClaw 风格的 `SKILL.md` 多语言 blocks，可与标准 frontmatter 共存。示例：

```markdown
[[ _meta ]]
name = "patent-search"
description = "专利检索技能"

[[ locales.zh ]]
prompt = "你是一个专利分析助手..."

[[ locales.en ]]
prompt = "You are a patent analysis assistant..."
```

可通过以下方式安装：

- 管理后台上传 zip
- 管理后台 URL 安装：`POST /api/skills/install-url`
- CLI：`mchat skill install patent-search` 或 `mchat skill install <zip_url>`

### 技能工具处理函数

在 SKILL.md 同级目录创建 `handler.py`:

```python
# skills/my-skill/handler.py

async def my_handler_function(param1: str, param2: int, **kwargs):
    """工具处理函数"""
    result = f"处理完成: {param1}, {param2}"
    return {"result": result}
```

### 测试技能

1. 将技能文件夹放入 `src/backend/skills/`
2. 调用 API 重新加载: `POST /api/skills/reload`
3. 在管理后台启用技能
4. 通过对话测试

技能工具若需 Excel/Word 导出，可选依赖的安装与回退见 **[导出可选依赖（自动安装）](export-optional-deps.zh.md)**。

---

## 测试

### 后端测试

```bash
cd src/backend
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

### 前端测试

```bash
cd src/frontend
npm test
```

---

## 调试

### 后端调试

```python
# 在代码中添加断点
import pdb; pdb.set_trace()

# 或使用 loguru 日志
from loguru import logger
logger.debug("Debug info: {}", data)
```

### 前端调试

- 使用 React DevTools 浏览器扩展
- 使用 `console.log` 或浏览器断点
- Vite 开发服务器支持 HMR 热更新

### API 调试

- 访问 http://localhost:3001/docs 使用 Swagger UI 交互式调试
- 使用 curl 或 Postman 测试 API
