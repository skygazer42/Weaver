# MCP 客户端事件化（初版）

- 新实现：`tools/core/mcp_clients.py` + `tools/mcp.py`
  - 支持 SSE 和 stdio 连接多个 MCP 服务器。
  - 远程工具注册为本地代理，命名 `mcp_{serverId}_{toolName}`。
- 执行时发事件：`tool_start`, `tool_result`, `tool_error`，payload 包含 `server` 字段，便于前端展示来源。
- 配置：`settings.mcp_servers`（JSON / env），`enable_mcp` 仍作开关。
- 接入点：`init_mcp_tools` 返回代理工具列表，可在启动时注册；关闭用 `close_mcp_tools`。
- 已接入：
  - `main.py` lifespan 启动时自动连接 MCP，关闭时断开。
  - `__thread_id__` 会注入到 mcp_servers 配置，代理工具会在注册后重写 `thread_id` 到当前会话。
- TODO：
  - 运行时重载（/api/mcp/config）已注入 thread_id，但仍需按需支持多线程隔离/拆分连接。
