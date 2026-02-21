# API 说明（后端 ↔ 前端）

Weaver 以 **FastAPI OpenAPI** 作为 API 合约的单一真相来源：

- 后端会生成 OpenAPI
- 前端通过 OpenAPI 自动生成 TypeScript types（防止“静默漂移”）

推荐先阅读：

- `docs/openapi-contract.md`（合约与 types 对齐）
- `docs/chat-streaming.md`（SSE/legacy 流式协议）

---

## OpenAPI 文档与导出

本地运行后端后：

- OpenAPI UI：http://localhost:8001/docs

离线导出（不需要启动 server）：

```bash
python scripts/export_openapi.py --output /tmp/weaver-openapi.json
```

---

## 常用端点（概览）

> 端点会持续演进，以 OpenAPI 为准。本节仅给你“入口”。

- Chat：
  - `POST /api/chat/sse`（推荐：标准 SSE）
  - `POST /api/chat`（legacy 行协议，回滚/兼容用）
  - `POST /api/chat/cancel/{thread_id}`（取消某个线程）
  - `POST /api/chat/cancel-all`（取消全部）
- Research：
  - `POST /api/research/sse`（推荐：标准 SSE）
  - `POST /api/research`（legacy）
- Agents：
  - `GET /api/agents`
  - `GET /api/agents/{agent_id}`
  - `POST /api/agents`
- Sessions / Export / Evidence：
  - `GET /api/sessions`
  - `GET /api/sessions/{thread_id}`
  - `GET /api/sessions/{thread_id}/evidence`
  - `GET /api/export/{thread_id}`
- MCP：
  - `GET /api/mcp/config`
  - `POST /api/mcp/config`

---

## SSE 调用示例（curl）

```bash
curl -N -X POST "http://127.0.0.1:8001/api/chat/sse" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello Weaver"}],"agent_id":"default"}'
```

> 提示：`-N` 用于关闭 curl 缓冲，避免 SSE 输出“攒一坨才显示”。

事件字段含义与前端处理方式：见 `docs/chat-streaming.md`。
