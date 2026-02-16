# Chat Streaming Protocols (SSE vs Legacy)

Weaver 当前支持两种 Chat 流式协议，目的是在“标准化（更通用）”与“兼容性（便于回滚）”之间取得平衡：

- **SSE（推荐）**：标准 Server-Sent Events，端点为 `POST /api/chat/sse`
- **Legacy（兼容）**：Vercel AI SDK Data Stream Protocol 的简化行协议（`0:{json}\n`），端点为 `POST /api/chat`

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

## 2) Legacy Chat Stream（兼容）

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

## 3) 前端如何切换协议

通过环境变量控制：

- `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse`（默认，推荐）
- `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=legacy`（遇到 SSE 兼容性问题时使用）

该开关只影响前端发起 chat streaming 的 URL 选择，不影响：

- `/api/events/{thread_id}` 的研究过程 SSE（EventSource）
- `/api/chat/cancel/{thread_id}` 的取消行为（两种协议共用同一取消端点）

---

## 4) Troubleshooting（常见问题）

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

