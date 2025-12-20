# API 说明（后端）

Base URL（本地开发）：

```
http://localhost:8000
```

## 1. 健康检查

### `GET /`

简单健康检查。

### `GET /health`

返回更详细的健康信息（包含时间戳等）。

## 2. 对话（流式）

### `POST /api/chat`

主入口（兼容 Vercel AI SDK `useChat` 的 `messages` 结构）。

请求示例：

```json
{
  "messages": [
    { "role": "user", "content": "帮我总结一下 LangGraph 的核心概念" }
  ],
  "stream": true,
  "model": "deepseek-chat",
  "search_mode": {
    "useWebSearch": true,
    "useAgent": true,
    "useDeepSearch": false
  }
}
```

响应：

- `Content-Type: text/event-stream`
- 每行是 Vercel AI SDK Data Stream Protocol：`0:{json}\n`

示例行：

```text
0:{"type":"text","data":{"content":"..."}}
```

### `POST /api/chat/cancel/{thread_id}`

取消某个流式任务（`thread_id` 通常来自 `/api/chat` 响应头 `X-Thread-ID`）。

### `POST /api/chat/cancel-all`

取消所有正在运行的任务。

### `GET /api/tasks/active`

查看当前活跃任务（取消管理器统计 + stream 数）。

## 3. 研究入口（流式）

### `POST /api/research?query=...`

与 `/api/chat` 的流式逻辑相同，但用 query 参数触发。

## 4. 中断与恢复（可选）

### `POST /api/interrupt/resume`

用于 human-in-the-loop：对 interrupt 的 LangGraph 线程恢复执行。  
如果没有启用 checkpoint（例如未配置 `DATABASE_URL`），可能返回 404。

## 5. MCP（可选）

### `GET /api/mcp/config`

读取当前 MCP 配置。

### `POST /api/mcp/config`

更新 MCP servers 配置并热重载工具。

## 6. 记忆（可选）

### `GET /api/memory/status`

返回当前记忆后端信息（Mem0 / fallback / store）。

## 7. ASR / TTS（可选）

依赖 `DASHSCOPE_API_KEY`。

- `GET /api/asr/status`
- `POST /api/asr/recognize`
- `POST /api/asr/upload`
- `GET /api/tts/status`
- `GET /api/tts/voices`
- `POST /api/tts/synthesize`

## 8. 指标（可选）

### `GET /metrics`

需要 `ENABLE_PROMETHEUS=true` 才会启用；否则可能 404。

