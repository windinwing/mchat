# mchat Development Guide

## Local Development Environment

### 1. Clone the project

```bash
git clone https://github.com/your-org/mchat.git
cd mchat
```

### 2. One-shot setup (recommended)

```bash
make setup   # lite MySQL, sync .env, install, db init
make dev
# or: make docker-up-lite
```

### 3. Start MySQL only (manual)

```bash
make db-mysql-dev
```

### 4. Backend development

```bash
cd src/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env for database settings

# Initialize database tables
python -c "
from app.core.database import engine, Base
from app.models import *  # noqa
import asyncio
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"

# Start development server with hot reload
uvicorn app.main:app --reload --port 3001
```

### 4. Frontend development

```bash
cd src/frontend
npm install
npm run dev  # starts at http://localhost:5173
```

### 5. Access URLs

- Frontend: http://localhost:5173
- Backend API: http://localhost:3001
- API Docs (Swagger): http://localhost:3001/docs
- API Docs (ReDoc): http://localhost:3001/redoc

---

## Project Conventions

### Python coding style

- Use Python 3.12+ type annotations
- Use `async/await` for async functions
- Follow PEP 8
- Format code with `black` (recommended)
- Run `ruff` for linting

### Frontend coding style

- TypeScript strict mode
- Functional components + Hooks
- Tailwind CSS for styling
- PascalCase component file names

### Git commit conventions

```raw
feat: new feature
fix: bug fix
docs: documentation update
style: formatting change
refactor: refactor
test: tests
chore: build/tooling
```

---

## Backend Development Guide

### Add a new API route

1. Create a route file under `app/api/`.
2. Use FastAPI `APIRouter`.
3. Register the router in `app/api/__init__.py`.

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

### Add a new data model

1. Create a model file in `app/models/`.
2. Inherit from `Base` (SQLAlchemy declarative base).
3. Import it in `app/models/__init__.py`.

### Add a new service

```python
# app/services/example_service.py
from sqlalchemy.ext.asyncio import AsyncSession

class ExampleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def do_something(self, data: dict):
        # business logic
        pass
```

### Add a new LLM provider

1. Add a new provider class to `app/bot/provider.py`.
2. Inherit from the `LLMProvider` base class.
3. Implement `async_stream_chat()`.

```python
class MyProvider(LLMProvider):
    async def stream_chat(self, messages, **kwargs):
        # implement streaming chat
        pass
```

---

## Frontend Development Guide

### Component structure

```raw
src/
├── components/
│   ├── ui/           # Base UI components
│   ├── chat/         # Chat-related components
│   ├── widget/       # Embedded widget components
│   ├── admin/        # Admin console components
│   └── layout/       # Layout components
├── pages/            # Page components
├── stores/           # Zustand state stores
├── hooks/            # Custom hooks
├── lib/              # Utility functions
│   ├── api.ts        # API client
│   ├── websocket.ts  # WebSocket client
│   └── utils.ts      # Utilities
└── styles/           # Style files
```

### Add a new page

1. Create the page under `src/pages/`.
2. Add the route in `src/App.tsx`.

### Add a new store

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

## Skill Development

### Skill structure

```raw
skills/my-skill/
└── SKILL.md
```

### SKILL.md format

```markdown
---
name: my-skill
description: My skill description
version: 1.0.0
tools:
  - name: my_tool
    description: Tool description
    parameters:
      param1:
        type: string
        description: Parameter 1 description
      param2:
        type: integer
        description: Parameter 2 description
    handler: my_handler_function
prompts:
  - role: system
    content: |
      You have the following capabilities:
      - Capability 1
      - Capability 2
---

# Skill Notes

Detailed usage instructions and examples.
```
### OpenClaw-compatible format

MChat also supports OpenClaw-style multilingual blocks in `SKILL.md`, and they can coexist with standard frontmatter. Example:

```markdown
[[ _meta ]]
name = "patent-search"
description = "Patent search skill"

[[ locales.zh ]]
prompt = "你是一个专利分析助手..."

[[ locales.en ]]
prompt = "You are a patent analysis assistant..."
```

You can install skills by:

- Uploading a zip in the admin console
- Installing by URL in the admin console: `POST /api/skills/install-url`
- Using the CLI: `mchat skill install patent-search` or `mchat skill install <zip_url>`

### Skill tool handler

Create `handler.py` beside `SKILL.md`:

```python
# skills/my-skill/handler.py

async def my_handler_function(param1: str, param2: int, **kwargs):
    """Tool handler"""
    result = f"Done: {param1}, {param2}"
    return {"result": result}
```

### Test a skill

1. Put the skill folder into `src/backend/skills/`.
2. Reload via API: `POST /api/skills/reload`.
3. Enable the skill in the admin console.
4. Test it through chat.

---

## Testing

### Backend tests

```bash
cd src/backend
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

### Frontend tests

```bash
cd src/frontend
npm test
```

---

## Debugging

### Backend debugging

```python
# Add a breakpoint in code
import pdb; pdb.set_trace()

# Or use loguru logs
from loguru import logger
logger.debug("Debug info: {}", data)
```

### Frontend debugging

- Use the React DevTools browser extension
- Use `console.log` or browser breakpoints
- The Vite development server supports HMR hot reload

### API debugging

- Open http://localhost:3001/docs for interactive Swagger UI debugging
- Use curl or Postman for API testing
