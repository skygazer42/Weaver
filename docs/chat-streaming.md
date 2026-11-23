# Streaming Protocols (SSE vs Legacy)

Weaver 当前支持两种流式协议（Chat / Research），目的是在“标准化（更通用）”与“兼容性（便于回滚）”之间取得平衡：

- **SSE（推荐）**：标准 Server-Sent Events（`event:` / `data:` / `id:`），端点为：
  - Chat：`POST /api/chat/sse`
  - Research：`POST /api/research/sse`
- **Legacy（兼容）**：Vercel AI SDK Data Stream Protocol 的简化行协议（`0:{json}\n`），端点为：
  - Chat：`POST /api/chat`
  - Research：`POST /api/research?query=...`

> 默认前端会优先使用 **SSE**。如果你的部署平台/代理对 SSE 支持不佳（例如缓冲、断连、Header 被改写），可以切回 legacy。

---

## 1) SSE Chat Stream（推荐）

**Endpoint**

- `POST /api/chat/sse`
- `Content-Type: application/json`
- `Accept: text/event-stream`

**Response**

- `Content-Type: text/event-stream`
- 事件帧是标准 SSE 形式：
  - `id: <number>`（可选）
  - `event: <type>`
  - `data: <json>`
  - 空行作为 frame 分隔（`\n\n`）

Weaver 的 `data` 通常是一个 **envelope**：

```json
{ "type": "text", "data": { "content": "..." } }
```

常见 `event/type`：

- `status`：状态提示（规划中/检索中/总结中…）
- `text`：增量文本片段（流式）
- `completion`：最终文本（一次性）
- `tool`：工具事件（开始/完成/失败）
- `sources`：结构化来源列表（用于引用/可追溯）
- `error`：错误信息
- `done`：流结束

---

### Web Deep Research 重连

Web 聊天通过 `POST /api/chat/sse?research_id=<32 位随机小写十六进制标识>` 启动 Deep Research。同一用户重复提交同一标识会接回仍可回放的运行。`GET /api/chat/sse/{research_id}` 回放已有事件并继续接收进度，客户端可通过 `Last-Event-ID` 指定最后收到的事件。后端单独分配 `X-Thread-ID` 供证据和工具视图使用。`DELETE /api/chat/sse/{research_id}` 停止研究。

回放保存在处理请求的 API 进程内。已结束的任务最多保留一小时，也可能随容量淘汰。进程重启会清除回放。

## 2) SSE Research Stream（推荐）

Research 的 SSE 协议与 Chat 基本一致（复用同一个 SSE parser），差别在于请求体字段。

**Endpoint**

- `POST /api/research/sse`
- `Content-Type: application/json`
- `Accept: text/event-stream`

**Request body**

```json
{
  "query": "your question",
  "model": "optional override",
  "search_mode": { "useWebSearch": false, "useAgent": true, "useDeepSearch": true },
  "agent_id": "optional",
  "user_id": "optional"
}
```

**Response headers**

- `X-Thread-ID: thread_<uuid>`
- `Content-Type: text/event-stream`

> 前端会读取 `X-Thread-ID` 来连接 `/api/events/{thread_id}`（进度可视化）以及拉取 `/api/sessions/{thread_id}/evidence`（证据面板）。

---

## 3) Legacy Chat Stream（兼容）

**Endpoint**

- `POST /api/chat`

**Response**

- `Content-Type: text/event-stream`
- 但 payload 并非标准 SSE frame，而是逐行输出：

```
0:{"type":"text","data":{"content":"hello"}}\n
0:{"type":"completion","data":{"content":"final"}}\n
```

前端会用 `fetch().body.getReader()` 自行逐行解析。

---

## 4) Legacy Research Stream（兼容）

**Endpoint**

- `POST /api/research?query=...`

**Response**

- `Content-Type: text/event-stream`
- 同样是逐行输出 legacy 协议：

```
0:{"type":"text","data":{"content":"hello"}}\n
0:{"type":"completion","data":{"content":"final"}}\n
```

> 该协议主要用于回滚/兼容，在新部署里更推荐 `POST /api/research/sse`。

---

## 5) 前端如何切换协议

通过环境变量控制：

- `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse`（默认，推荐）
- `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=legacy`（遇到 SSE 兼容性问题时使用）
- `NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=sse`（默认，推荐）
- `NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=legacy`（遇到 SSE 兼容性问题时使用）

该开关只影响前端发起 streaming 的 URL 选择，不影响：

- `/api/events/{thread_id}` 的研究过程 SSE（EventSource）
- `/api/chat/cancel/{thread_id}` 的取消行为（两种协议共用同一取消端点）

---

## 6) Research Progress Events（/api/events/{thread_id}）

Inspector 的 Progress 面板使用 EventSource 连接：

- `GET /api/events/{thread_id}`

该流用于可视化 deep research 的过程（timeline/tree/quality 更新），常见事件：

- `quality_update`
- `research_tree_update`
- `research_node_start` / `research_node_complete`
- `search`
- `error` / `done`

> 注意：EventSource 不暴露 response headers，因此 `thread_id` 必须来自 Chat/Research 的 `X-Thread-ID` header。

---

## 7) Troubleshooting（常见问题）

### SSE 卡住/不流式

可能原因：

- 反向代理对响应做了缓冲（buffering）
- 平台/网关对 `text/event-stream` 支持不完整
- 中间层超时较短导致断连

应对：

- 先临时切换 `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=legacy` 验证
- 检查代理配置：禁用 buffering、提高 read timeout

### 断连/重连

前端实现包含有限的重试与退避逻辑；如果仍频繁断连，建议在基础设施侧提高 SSE 连接可用性。

---

## 5) Evidence Inspector（Passages / Sources）

前端 Chat 右侧的 Inspector 面板（原 Artifacts）包含 **Evidence** 标签页，用于查看 evidence-first 结构化产物：

- `GET /api/sessions/{thread_id}/evidence`
- Response: `EvidenceResponse`（包含 `sources / claims / fetched_pages / passages`）

若希望看到更强的 `passages`（带 `heading_path / quote / snippet_hash`），建议在 `.env` 中启用：

- `DEEPSEARCH_ENABLE_RESEARCH_FETCHER=true`
