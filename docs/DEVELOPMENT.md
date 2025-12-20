# 开发指南（后端为主）

本文档面向需要二次开发 Weaver 的同学，重点覆盖后端运行方式、代码结构、调试与常见改动点。

## 常用命令

后端（PowerShell）：

```powershell
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```powershell
cd web
npm run dev
```

测试：

```powershell
pytest -q
```

## 目录结构（实际代码）

```
Weaver/
  main.py              # FastAPI 入口（SSE、取消、中断、MCP、ASR/TTS）
  agent/               # LangGraph 工作流（state / nodes / graph）
  tools/               # 工具封装（Tavily、E2B、MCP、ASR/TTS、crawler）
  common/              # 配置、日志、指标、取消等通用模块
  tests/               # 后端测试
  web/                 # Next.js 前端
  docs/                # 文档
```

## 关键代码入口

- 后端应用：`main.py`
  - `/api/chat`：主对话入口（支持流式）
  - `/api/research`：研究模式入口（流式）
  - `/api/chat/cancel/{thread_id}`：取消单任务
  - `/api/interrupt/resume`：中断后恢复（LangGraph checkpoint）
  - `/api/mcp/config`：运行时配置 MCP servers
  - `/api/asr/*`、`/api/tts/*`：语音服务（可选）
- LangGraph：`agent/graph.py`
  - `create_research_graph(...)`：组装 router/planner/search/writer/evaluator 等节点
- 节点实现：`agent/nodes.py`
  - 搜索并发、writer 汇总、evaluator-optimizer 迭代、deepsearch 等逻辑都在这里
- 配置：`common/config.py`
  - Pydantic Settings 从 `.env` 读取（默认 `case_sensitive=False`）

## 本地调试建议

- 日志：默认写入 `logs/`，并可按 `thread_id` 追加写入 `logs/threads/{thread_id}.log`（见 `main.py` 的流式逻辑）。
- 复现问题：优先用 `tests/test_smoke_api.py` 或直接 `curl` 触发对应接口。
- 模型切换：`/api/chat` 支持在请求里传 `model`，并在 LangGraph `configurable.model` 中下发到节点/工具调用。

## 常见改动点

- 增加/修改工作流节点：改 `agent/nodes.py` 并在 `agent/graph.py` 接入边/条件路由。
- 增加工具：
  1) 在 `tools/` 新建工具（推荐用 `langchain.tools.tool` 装饰器）
  2) 在节点里把工具加入可用列表（例如 writer 的 `_get_writer_tools()`）
  3) 如需 MCP：配置 `ENABLE_MCP=true` + `MCP_SERVERS`，或走 `/api/mcp/config`

更多“后端工作流与接口时序”请看：`docs/BACKEND_WORKFLOW.md`。

