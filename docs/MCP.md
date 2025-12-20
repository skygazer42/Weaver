# MCP（Multi-Server MCP Client）

Weaver 支持通过 MCP 动态接入外部工具，并把这些工具注册到 LangChain/LLM 的可调用工具列表中。

## 1. 启用方式

方式 A：环境变量（启动时加载）

- `.env`：
  - `ENABLE_MCP=true`
  - `MCP_SERVERS={...}`（JSON）

方式 B：运行时配置（热更新）

- `POST /api/mcp/config`
- `GET /api/mcp/config`

## 2. MCP_SERVERS 格式

`MCP_SERVERS` 期望是 JSON mapping（server name -> transport config）。

示例（仅示意，按你的 MCP server 实际参数调整）：

```json
{
  "math": {
    "transport": "stdio",
    "command": "python",
    "args": ["path/to/mcp_math_server.py"]
  }
}
```

## 3. 工具注册链路

- 加载：`tools/mcp.py#init_mcp_tools`
- 注册：`tools/registry.py#set_registered_tools`
- 使用：`agent/nodes.py#_get_writer_tools` 会把注册工具合并进 writer 的工具列表

如果 MCP 未启用或配置为空，系统会继续运行，只是不会加载额外工具。

