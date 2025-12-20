# 后端工作流（Weaver）

本文档解释 Weaver 后端“从请求到产出”的完整链路：FastAPI 接口、LangGraph 工作流、工具执行、记忆/持久化、取消/中断、MCP、以及流式协议。

## 1. 总体架构

- Web：`web/`（Next.js 14）
- Backend：根目录（FastAPI，入口 `main.py`）
- Agent：`agent/`（LangGraph）
- Tools：`tools/`（搜索/代码执行/MCP/语音等）
- Common：`common/`（配置、日志、指标、取消等）

## 2. 核心请求链路

### 2.1 `/api/chat`（流式）

1) 前端把 `messages[]` 传给后端（Vercel AI SDK 的 useChat 兼容格式）  
2) 后端生成 `thread_id`（响应头 `X-Thread-ID`）  
3) `stream_agent_events(...)` 启动 LangGraph 事件流，并把事件转换为数据流协议输出  
4) 前端按事件增量渲染：规划/搜索/工具/正文 token/最终 done

流式输出格式在 `main.py#format_stream_event`：每行类似：

```
0:{"type":"text","data":{"content":"..."}}
```

更完整的流式/取消/中断说明见：`docs/RUN_LIFECYCLE.md`。

### 2.2 `/api/research`（研究流式）

`/api/research` 是 `/api/chat` 的轻量封装：直接把 query 送入 `stream_agent_events(query)`，用于长任务/研究模式。

## 3. LangGraph 工作流（研究图）

构建位置：`agent/graph.py#create_research_graph`。
更细的节点/状态说明见：`docs/AGENT_GRAPH.md`。

核心节点（按语义分组）：

- 路由：`router`（根据 search_mode 选择 direct/web/deep/clarify）
- 规划：`planner` / `web_plan` / `refine_plan`
- 搜索执行：`perform_parallel_search`（并发查询 + 可选爬虫补全文本）
- 写作：`writer`（汇总、可调用工具生成图表/代码）
- 质量回路（deep 模式）：`evaluator` -> `refine_plan`（迭代到通过或达到上限）
- 人审/中断：`human_review`（可接入 interrupt/resume）
- 深搜：`deepsearch`（深度搜索策略）

建议结合图看：`docs/graph_mermaid.md`。如需重新生成，可运行：

```powershell
python -c "from agent.graph import export_graph_mermaid; export_graph_mermaid('docs/graph_mermaid.md')"
```

## 4. 工具执行管线

工具系统更完整说明见：`docs/TOOLS.md`。

### 4.1 搜索

- Tavily：`tools/search.py`（在节点里调用 `tavily_search.invoke(...)`）
- 并发控制：`common/concurrency.py`（如启用）
- 可选轻量爬虫：`tools/crawler.py`

### 4.2 代码执行（E2B）

- 工具：`tools/code_executor.py#execute_python_code`
- 输出：stdout/stderr/error + 可选图片（matplotlib 等）
- 在流式阶段：`main.py` 会把代码执行产生的图片包装成 `artifact` 事件（前端可展示图表）

### 4.3 MCP 工具桥（可选）

- 初始化：`tools/mcp.py#init_mcp_tools`
- 将 MCP tools 注册到全局 registry：`tools/registry.py`
- 运行时更新：`/api/mcp/config`（GET/POST）

## 5. 记忆与持久化

### 5.1 LangGraph store（长期记忆）

在 `main.py` 启动时初始化 `store`：
- `memory_store_backend=memory`：`InMemoryStore`
- `memory_store_backend=postgres`：`PostgresStore`
- `memory_store_backend=redis`：`RedisStore`

### 5.2 Mem0（可选）与本地回退

`tools/memory_client.py`：
- `ENABLE_MEMORY=true` 且安装 `mem0`：启用语义检索记忆
- 否则回退到 `data/memory_store.json`（无语义，仅按最近）

### 5.3 Checkpointer（短期/断点）

`DATABASE_URL` 存在时，使用 `langgraph-checkpoint-postgres` 做 checkpoint；否则回退 `InMemorySaver`。

这直接影响：
- `/api/interrupt/resume` 是否能恢复（无 checkpoint 会 404）
- 多进程/重启后是否能恢复运行状态

## 6. 取消与中断

### 6.1 取消

- 取消令牌：`common/cancellation.py`
- 流式执行中会创建 token，并在关键点检查（搜索前/后、节点间等）
- API：
  - `POST /api/chat/cancel/{thread_id}`
  - `POST /api/chat/cancel-all`
  - `GET /api/tasks/active`

### 6.2 中断与恢复

`POST /api/interrupt/resume`：为 “human-in-the-loop” 场景预留。  
依赖 checkpointer（见 5.3）。

## 7. 语音能力（可选）

- ASR：`tools/asr.py`，接口 `/api/asr/*`（依赖 `DASHSCOPE_API_KEY`）
- TTS：`tools/tts.py`，接口 `/api/tts/*`（依赖 `DASHSCOPE_API_KEY`）

## 8. 指标与日志

- Prometheus（可选）：`ENABLE_PROMETHEUS=true` 后开放 `/metrics`
- 运行统计：`/api/runs`、`/api/runs/{thread_id}`
- 日志：
  - 全局日志：`logs/`
  - 线程日志（可选）：`logs/threads/{thread_id}.log`（见 `stream_agent_events`）

## 9. 与 FuFanManus（课程项目）的关键差异

FuFanManus 后端（你给的路径）采用 “后台任务队列 + Redis List/PubSub 推流” 模式：
- `/thread/{thread_id}/agent/start` 入队（Dramatiq）  
- `run_agent_background` 产出分片写 Redis List，并 publish 通知  
- `/agent-run/{agent_run_id}/stream` SSE 从 Redis 实时读增量  

Weaver 当前实现更轻量：直接在 FastAPI 请求内跑 LangGraph，并流式输出（适合单实例/开发模式）。

对 FuFanManus 的实现拆解与对照建议见：`docs/REFERENCE_FUFANMANUS_BACKEND.md`。
