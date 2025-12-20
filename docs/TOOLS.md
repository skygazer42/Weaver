# 工具系统（tools/）

本文档说明 Weaver 的工具层：有哪些工具、如何被节点/LLM 调用、以及如何新增工具。

## 1. 内置工具一览

主要工具文件：

- 搜索：`tools/search.py`（Tavily）
- 代码执行：`tools/code_executor.py`（E2B code interpreter）
- 轻量爬虫：`tools/crawler.py`（可选，用于补全文本）
- 记忆：`tools/memory_client.py`（Mem0 或本地 JSON 回退）
- MCP：`tools/mcp.py` + `tools/registry.py`（多工具桥）
- 语音（可选）：`tools/asr.py`、`tools/tts.py`

## 2. 工具如何被“用起来”

Weaver 有两类使用方式：

1) 节点直接调用（确定性调用）  
   例如 `agent/nodes.py#perform_parallel_search` 直接调用 `tavily_search.invoke(...)`。

2) 作为 LLM 可调用工具（function calling）  
   例如 writer 阶段会把 `execute_python_code`（以及 MCP 注册的工具）放入工具列表，让模型按需调用。

## 3. 工具中间件与策略

位置：`agent/middleware.py`

- 重试：`retry_call(...)`
  - 开关/参数来自 `.env`：`TOOL_RETRY`、`TOOL_RETRY_MAX_ATTEMPTS`、`TOOL_RETRY_BACKOFF`
- 工具调用上限：`enforce_tool_call_limit(...)`
  - `.env`：`TOOL_CALL_LIMIT`（0 表示无限制）
- 历史裁剪（节省 token）：`STRIP_TOOL_MESSAGES`

## 4. 新增一个工具（推荐流程）

1) 在 `tools/` 新建一个 Python 文件，并用 `langchain.tools.tool` 装饰器定义函数工具  
2) 在需要的节点里把该工具加入可用工具列表（例如 `agent/nodes.py` 的 `_get_writer_tools()`）  
3) 如工具需要外部 Key，把配置项加入 `.env.example`，并在 `common/config.py` 里声明对应字段

如果你希望“运行时动态接入工具”，优先考虑 MCP（见 `tools/mcp.py` 与 `/api/mcp/config`）。

