# 项目结构对比

## 完整目录树对比

### Before (重构前)
```
manus-app/
├── backend/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── graph.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── search.py
│   │   └── code_executor.py
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── chat/
│   │   │   ├── Chat.tsx
│   │   │   ├── MessageItem.tsx
│   │   │   └── ArtifactsPanel.tsx
│   │   └── ui/
│   │       ├── button.tsx
│   │       ├── input.tsx
│   │       ├── card.tsx
│   │       └── scroll-area.tsx
│   ├── lib/
│   │   └── utils.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── .env.local.example
│
├── scripts/
│   ├── setup.sh
│   └── dev.sh
│
├── .gitignore
├── .env.example
├── package.json
├── docker-compose.yml
├── README.md
├── DEVELOPMENT.md
├── API.md
└── (其他文档...)
```

### After (重构后)
```
manus-app/
├── agent/                    ← 从 backend/agent 移出
│   ├── __init__.py
│   ├── state.py
│   ├── nodes.py
│   └── graph.py
│
├── tools/                    ← 从 backend/tools 移出
│   ├── __init__.py
│   ├── search.py
│   └── code_executor.py
│
├── web/                      ← 重命名自 frontend
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── chat/
│   │   │   ├── Chat.tsx
│   │   │   ├── MessageItem.tsx
│   │   │   └── ArtifactsPanel.tsx
│   │   └── ui/
│   │       ├── button.tsx
│   │       ├── input.tsx
│   │       ├── card.tsx
│   │       └── scroll-area.tsx
│   ├── lib/
│   │   └── utils.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── .env.local.example
│
├── scripts/
│   ├── setup.sh
│   └── dev.sh
│
├── main.py                   ← 从 backend 移出
├── config.py                 ← 从 backend 移出
├── requirements.txt          ← 从 backend 移出
├── Dockerfile                ← 从 backend 移出
├── .gitignore
├── .env.example              ← 合并了 backend/.env.example
├── package.json
├── docker-compose.yml
├── README.md
├── DEVELOPMENT.md
├── API.md
└── (其他文档...)
```

## 关键差异

| 方面 | Before | After | 说明 |
|------|--------|-------|------|
| **前端目录** | `frontend/` | `web/` | 更准确的命名 |
| **后端位置** | `backend/` 子目录 | 根目录 | 扁平化结构 |
| **Python 模块** | `backend.agent`<br>`backend.tools` | `agent`<br>`tools` | 更简洁的导入 |
| **虚拟环境** | `backend/venv/` | `venv/` | 标准位置 |
| **配置文件** | 分散在两处 | 集中在根目录 | 更易管理 |

## 文件移动映射

### Python 文件
```
backend/agent/__init__.py    → agent/__init__.py
backend/agent/state.py       → agent/state.py
backend/agent/nodes.py       → agent/nodes.py
backend/agent/graph.py       → agent/graph.py

backend/tools/__init__.py    → tools/__init__.py
backend/tools/search.py      → tools/search.py
backend/tools/code_executor.py → tools/code_executor.py

backend/main.py              → main.py
backend/config.py            → config.py
backend/requirements.txt     → requirements.txt
backend/Dockerfile           → Dockerfile
```

### TypeScript 文件
```
frontend/                    → web/
frontend/app/*               → web/app/*
frontend/components/*        → web/components/*
frontend/lib/*               → web/lib/*
(所有子文件保持相对路径不变)
```

## 命令对比

### 安装依赖

| Before | After |
|--------|-------|
| `cd backend && pip install -r requirements.txt` | `pip install -r requirements.txt` |
| `cd frontend && npm install` | `cd web && npm install` |

### 启动开发服务器

| Before | After |
|--------|-------|
| `cd backend`<br>`source venv/bin/activate`<br>`uvicorn main:app --reload` | `source venv/bin/activate`<br>`uvicorn main:app --reload` |
| `cd frontend`<br>`npm run dev` | `cd web`<br>`npm run dev` |

### Docker 构建

| Before | After |
|--------|-------|
| `docker build -t manus-backend ./backend` | `docker build -t manus-backend .` |

## 导入路径对比

### Python 导入（无需更改）
```python
# Before 和 After 都相同
from common.config import settings
from agent import create_research_graph, AgentState
from tools import tavily_search, execute_python_code
```

原因：Python 将根目录添加到 sys.path

### TypeScript 导入（无需更改）
```typescript
// 前端内部导入使用相对路径或别名，无需更改
import { Button } from '@/components/ui/button'
import { Chat } from '@/components/chat/Chat'
```

## 配置文件变化

### package.json
```json
// Before
{
  "workspaces": ["frontend"],
  "scripts": {
    "dev:frontend": "cd frontend && npm run dev",
    "dev:backend": "cd backend && uvicorn main:app --reload"
  }
}

// After
{
  "workspaces": ["web"],
  "scripts": {
    "dev:web": "cd web && npm run dev",
    "dev:backend": "uvicorn main:app --reload"
  }
}
```

### docker-compose.yml
```yaml
# Before
services:
  backend:
    build: ./backend
    volumes:
      - ./backend:/app

# After
services:
  backend:
    build: .
    volumes:
      - .:/app
```

## 优缺点分析

### 优点 ✅
1. **更扁平的结构** - 减少目录嵌套
2. **更短的路径** - `backend/agent/nodes.py` → `agent/nodes.py`
3. **符合标准** - Python 项目通常不嵌套在子目录
4. **简化命令** - 减少 `cd` 命令的使用
5. **更清晰** - 一眼就能看到项目主要模块

### 注意事项 ⚠️
1. **破坏性变更** - 旧的路径引用需要更新
2. **需要重新安装** - venv 位置改变
3. **IDE 配置** - 需要更新解释器路径

## 迁移检查清单

- [ ] 拉取最新代码
- [ ] 删除旧的 venv: `rm -rf backend/venv`
- [ ] 删除旧的 node_modules: `rm -rf frontend/node_modules node_modules`
- [ ] 运行 `./scripts/setup.sh`
- [ ] 更新 IDE Python 解释器: `./venv/bin/python`
- [ ] 测试后端: `source venv/bin/activate && uvicorn main:app --reload`
- [ ] 测试前端: `cd web && npm run dev`
- [ ] 验证应用正常运行

## 总结

这次重构主要是**结构优化**，代码逻辑完全不变。主要目的是：
1. 使项目结构更符合业界标准
2. 简化开发流程
3. 提高代码可维护性

如果你是新用户，直接按照新的 README.md 使用即可。  
如果你是老用户，按照迁移检查清单更新即可。
