# 排障与常见问题

本文档优先覆盖 Windows + 本项目的真实结构与配置。

## 1) 最常见：Key/配置缺失

### 搜索不可用（Tavily）

症状：调用搜索时报错或无结果。  
检查：

- `.env` 是否配置 `TAVILY_API_KEY`
- 后端启动日志是否打印了相关 warning/error

### 代码执行不可用（E2B）

症状：writer 阶段调用 `execute_python_code` 报错 `E2B_API_KEY is required...`  
检查：

- `.env` 是否配置 `E2B_API_KEY`

### ASR/TTS 返回 503

症状：`/api/asr/*` 或 `/api/tts/*` 返回 503。  
检查：

- `.env` 是否配置 `DASHSCOPE_API_KEY`
- Python 依赖是否满足（建议 `dashscope>=1.24.6`）

## 2) /metrics 返回 404

这是预期行为：只有 `ENABLE_PROMETHEUS=true` 才会暴露 `/metrics`。

## 3) /api/interrupt/resume 返回 404

通常原因：

- 未配置 `DATABASE_URL`（使用了 `InMemorySaver`，无法恢复）
- `thread_id` 不存在 checkpoint

## 4) 前端连不上后端

检查：

- `web/.env.local` 的 `NEXT_PUBLIC_API_URL` 是否指向 `http://localhost:8000`
- 后端是否已启动并监听 `8000`
- CORS：`.env` 里的 `CORS_ORIGINS` 是否包含 `http://localhost:3000`

## 5) PowerShell 无法执行 venv 激活脚本

症状：执行 `.\venv\Scripts\Activate.ps1` 报执行策略错误。  
解决（当前终端临时允许）：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## 6) 数据库相关问题

如果启用了 Postgres：

- `docker-compose up -d postgres`
- 检查 5432 端口是否被占用
- 确认 `.env` 的 `DATABASE_URL` 与 compose 的账号/密码一致

