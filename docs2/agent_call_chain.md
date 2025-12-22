# Agent 调用链与工具事件标准（当前版）

## 现状（Weaver + LangGraph）
- `agent_node` 通过 LangChain `create_agent`/`build_tool_agent` 让模型决定工具。
- 工具清单由 `agent/workflows/agent_tools.py` 根据 agent_profile 组装。
- 事件流（SSE）已有框架，但工具调用未统一上报 start/result/error。

## 本轮改动
1. **ToolCollection 层**：新增 `tools/core/collection.py`，为后续动态增删/白名单提供基础。
2. **事件包装器**：新增 `tools/core/wrappers.py` 的 `EventedTool`/`wrap_tools_with_events`，对工具执行发出标准事件：
   - `tool_start`: {tool, args}
   - `tool_result`: {tool, result, success, duration_ms}
   - `tool_error`: {tool, error, duration_ms}
   事件由 `agent.core.events` 的 emitter 推送，前端可实时显示执行进度。
3. **接入点**：`build_agent_tools` 默认对组装后的工具进行事件包装（可通过 `agent_profile.emit_tool_events` 关闭）。

## 调用链（逻辑）
```
router → agent_node
  ├─ build_agent_tools(config)
  │    ├─ 收集工具（web_search/crawl/browser/sandbox/.../mcp）
  │    ├─ 去重
  │    └─ wrap_tools_with_events(thread_id)
  ├─ LangChain agent 选择工具（tool_calls）
  └─ EventedTool 执行
        ↳ emitter.emit(tool_start/result/error)
```

## 前端可视化要点
- 监听 `/api/events/{thread_id}`，展示 `tool_start/result/error`，可配合截图/文本渲染。
- 浏览器类工具将被包装，因此每次点击/导航都会有 start/result 事件；后续可在 BrowserUse 内部追加 `tool_screenshot`。

## 下一步
- 将 BrowserUse / sandbox / MCP 等特定工具内部细粒度事件（screenshot/progress）也接入统一事件协议。
- 在 evaluator 中利用事件数据做 stuck 检测与提示。 
