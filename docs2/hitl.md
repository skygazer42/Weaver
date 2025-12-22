# HITL / AskHuman 工具
- 新增工具：`tools.automation.ask_human_tool.ask_human`（LangChain tool），默认在 agent_tools 中启用（可通过 agent_profile.ask_human=false 关闭）。
- 作用：向前端请求人工输入；前端应拦截此 tool 调用并提示用户，返回结果再写回对话。
- 事件：仍经 EventedTool 包装，发 `tool_start/result/error`，便于前端显示“等待人工输入”。
