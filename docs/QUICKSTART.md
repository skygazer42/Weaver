# 快速开始

目标：在本地跑起来 Weaver（后端 FastAPI + 前端 Next.js）。

为避免 Windows 控制台/编辑器编码问题，本文档尽量不使用 emoji。

## 依赖

- Python 3.11+
- Node.js 18+
- Docker Desktop（可选：用于启动 Postgres / pgvector）

## 1) 配置环境变量

在项目根目录：

```powershell
Copy-Item .env.example .env
Copy-Item web\.env.local.example web\.env.local
```

编辑 `.env`，至少填写：

```env
OPENAI_API_KEY=...
TAVILY_API_KEY=...
E2B_API_KEY=...            # 可选：启用代码执行
DASHSCOPE_API_KEY=...      # 可选：启用 ASR/TTS
```

## 2) 安装依赖

后端（Windows PowerShell）：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

前端：

```powershell
cd web
npm install
```

## 3) 启动服务

### 方案 A：本地运行（推荐）

1) 启动数据库（可选；仅当你启用 Postgres checkpointer 或 memory store 后端时需要）：

```powershell
docker-compose up -d postgres
```

2) 启动后端：

```powershell
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

3) 启动前端：

```powershell
cd web
npm run dev
```

访问：
- Web：`http://localhost:3000`
- Backend：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`

### 方案 B：Docker 运行后端 + 数据库

```powershell
docker-compose up --build
```

前端仍需单独在 `web/` 里 `npm run dev`（或自行容器化）。

## 4) 快速自检

```powershell
curl http://localhost:8000/health
pytest tests/test_smoke_api.py -q
```

