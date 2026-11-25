# MCP（Model Context Protocol）在 Weaver 的使用指南

Weaver 通过 **MCP（Model Context Protocol）** 将外部工具与数据源接入 Agent 工具体系（例如文档检索、GitHub、文件系统、数据库、企业内部 API 等），让模型在对话与深度研究中以统一 Schema 安全调用。

---

## 1. 支持的传输协议与标准格式

Weaver 后端作为 MCP Client，完整支持现代 MCP 生态主流协议：

| 协议 | `type` 值（可省略，自动推断） | 适用场景 | 支持字段 |
|------|-------------------------------|----------|----------|
| **Streamable HTTP（推荐远程）** | `streamable_http`（兼容 `http` / `streamable-http`） | 现代远程 MCP 服务（Context7、GitHub MCP、Notion、Linear 等） | `url`、`headers`、`timeout`、`enabled` |
| **Stdio（推荐本地）** | `stdio` | 本机通过 `npx` / `uvx` / Python 启动的 MCP 进程 | `command`、`args`、`env`、`cwd`、`timeout`、`enabled` |
| **SSE（兼容旧服务）** | `sse` | 尚未迁移到 Streamable HTTP 的传统 SSE 服务 | `url`、`headers`、`timeout`、`enabled` |

> **自动推断规则**：直接粘贴 Claude Desktop / Cursor 的标准配置时，无需手写 `type`——包含 `url` 且路径以 `/sse` 结尾自动识别为 `sse`，其余 `url` 默认识别为 `streamable_http`，包含 `command` 自动识别为 `stdio`。

---

## 2. 推荐配置方式：Web 设置页 / `config/mcp.json`

无需再把一整段 JSON 压成一行写进 `.env`。现在推荐通过以下两种方式管理 MCP：

### 方式 A：Web 设置页可视化管理（推荐）

1. 点击右上角 **设置**（或输入框上方 **MCP ▾ → 管理 MCP 服务器**）。
2. 开启 **启用 MCP**，点击 **添加服务器** 填写：
   - **Streamable HTTP**：填写端点 URL（如 `https://mcp.context7.com/mcp`）和可选请求头（如 `Authorization: Bearer ...`）。
   - **Stdio**：填写命令（如 `npx`）、参数与可选环境变量（`env`）。
3. 或者直接切换到 **导入 / JSON** 视图，粘贴任意标准的 `{ "mcpServers": { ... } }` 配置。
4. 点击保存后，后端会**自动持久化到 `config/mcp.json`**（已加入 `.gitignore`，不会误提交密钥），并实时展示每台服务器的连接状态、报错详情与发现的工具列表。

### 方式 B：直接编辑 `config/mcp.json`

支持与 Cursor / Claude Desktop 一致的 `mcpServers` 结构（带全局 `enabled` 与单台 `enabled` 开关）：

```json
{
  "enabled": true,
  "mcpServers": {
    "context7": {
      "type": "streamable_http",
      "url": "https://mcp.context7.com/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your-optional-key"
      },
      "enabled": true
    },
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/ABS/PATH/TO/ALLOW"],
      "env": {
        "NODE_ENV": "production"
      },
      "enabled": true
    }
  }
}
```

### 方式 C：容器 / 环境变量覆盖（向后兼容）

如果不存在 `config/mcp.json`，后端会自动回退读取 `.env` 中的 `ENABLE_MCP` 与 `MCP_SERVERS`（同样支持 `mcpServers` 包装或平铺 JSON），也可通过 `MCP_CONFIG_PATH` 自定义配置文件路径。

---

## 3. 运行时 API

- `GET /api/mcp/config`：返回当前 `enabled`、`servers` / `mcpServers`、`loaded_tools`、`config_path` 以及每台服务器的实时状态数组 `server_statuses`（含 `status`、`error`、`tool_count` 与具体 `tools` 清单）。
- `POST /api/mcp/config`：接收 `{ "enable": true, "mcpServers": { ... } }`（兼容旧字段 `servers`），持久化到 `config/mcp.json` 并热重载所有 MCP 连接。

---

## 4. 安全建议

- **最小目录授权**：配置 `filesystem` 类 stdio MCP 时，只传入明确的工作目录，避免开放 `/` 或用户主目录。
- **密钥隔离**：`config/mcp.json` 与 `.env` 均在 `.gitignore` 中，不要把包含 `Authorization` Header 或 `env` 密钥的配置提交进仓库。
- **只读优先**：连接数据库类 MCP 时优先使用只读凭据，高危操作可配合开启 `TOOL_APPROVAL=true`。

---

## 5. 常见问题排查

- **单台服务器状态显示 `error` / 超时**：单台连接超时默认 20 秒，不会阻塞其他正常服务器；可在设置页直接查看该服务器的具体报错信息并单独关闭或修改。
- **`command not found`**：确认 `npx`（Node.js）或 `uvx`（uv）在后端进程可访问的 `PATH` 中；`stdio` 模式传入自定义 `env` 时会自动保留系统环境，无需手动复制 `PATH`。
- **工具数为 0**：确认全局 MCP 开关及对应服务器开关均已开启，且目标 MCP Server 正常实现了 `tools/list`。
