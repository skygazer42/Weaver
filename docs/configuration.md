# 配置说明

本页汇总 Weaver 常用配置入口：

- 后端：根目录 `.env`（参考 `.env.example`）
- 前端：`web/.env.local`（参考 `web/.env.local.example`）
- Agent 配置：`data/agents.json`
- 触发器：代码/API（视你的接入方式）
- MCP：`ENABLE_MCP` + `MCP_SERVERS`（详见 `docs/mcp.md`）

---

## 后端 `.env`

### 端口（可选）

后端默认监听 `8001`。如端口冲突，可在根目录 `.env` 中设置：

```bash
# 选一个你机器上没被占用的端口即可（示例：18080 / 28001）
PORT=18080
```

> 建议：避免使用你环境里常见“容易被占用”的端口（例如 `8000`）。
> 你可以用 `lsof -i :<port>`（macOS/Linux）或 `netstat -ano | findstr :<port>`（Windows）
> 先确认端口空闲。

### 热重载（可选）

在这个仓库里，前端依赖树（`web/node_modules`）非常大，`uvicorn --reload` 很容易触发
`OS file watch limit reached` 之类的崩溃。因此：

- `python main.py` 默认 **不启用** 热重载（更稳定）
- 需要热重载时，建议显式开启（推荐写进 `.env`，避免每次敲命令）：

```bash
# in .env
DEBUG=true
WEAVER_RELOAD=true
```

或临时用 shell env：

```bash
DEBUG=true WEAVER_RELOAD=1 python main.py
```

### LLM Provider（择一）

OpenAI：

```bash
OPENAI_API_KEY=sk-...
```

DeepSeek（OpenAI 兼容）：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

Anthropic（Claude）：

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### 搜索（Deep/Web 模式常用）

```bash
TAVILY_API_KEY=tvly-...
```

### 代码执行（推荐）

```bash
E2B_API_KEY=e2b_...
```

### MCP（可选）

```bash
ENABLE_MCP=true
MCP_SERVERS={"filesystem":{"type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/ABS/PATH/TO/ALLOW"]},"memory":{"type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-memory"]}}
```

更多 MCP 配置与最佳实践：`docs/mcp.md`。

---

## 前端 `web/.env.local`

```bash
# 需要和后端 `.env` 中的 PORT 对齐（默认 8001）
NEXT_PUBLIC_API_URL=http://127.0.0.1:8001
NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse
NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=sse
```

如果你的部署平台/反代对 SSE 支持不佳，可临时切到 legacy；说明见 `docs/chat-streaming.md`。

---

## Agent 配置（类 GPTs）

在 `data/agents.json` 中配置自定义 Agent（示例）：

```json
{
  "id": "research_assistant",
  "name": "研究助手",
  "description": "专注于学术研究的 AI 助手",
  "system_prompt": "你是一位专业的学术研究助手，擅长文献检索、数据分析和报告撰写...",
  "model": "gpt-4o",
  "enabled_tools": {
    "web_search": true,
    "rag": false,
    "crawl": true,
    "python": true,
    "sandbox_browser": true,
    "sandbox_sheets": true,
    "sandbox_presentation": true,
    "mcp": false,
    "computer_use": false
  },
  "metadata": {
    "author": "Your Name",
    "version": "1.0.0"
  }
}
```

其中 `rag` 需要同时满足：

- 后端 `.env` 配置 `RAG_ENABLED=true`（或 `rag_enabled=true`）
- 当前 agent 的 `enabled_tools.rag=true`

---

## 触发器配置（示意）

定时任务示例（每天早上 9 点生成日报）：

```python
from triggers import TriggerManager, ScheduledTrigger

manager = TriggerManager()

trigger = ScheduledTrigger(
    name="daily_report",
    description="每日新闻摘要",
    schedule="0 9 * * *",
    agent_id="research_assistant",
    task="生成今日科技新闻摘要，包括 AI、芯片、新能源三个领域",
    timezone="Asia/Shanghai",
    run_immediately=False,
)

await manager.add_trigger(trigger)
```

Webhook 示例（接收 GitHub 事件）：

```python
webhook = WebhookTrigger(
    name="github_webhook",
    description="GitHub 事件通知",
    agent_id="default",
    task="分析 GitHub 事件: {payload.action}",
    http_methods=["POST"],
    require_auth=True,
    rate_limit=100,
)
```

---

## Deep Research 相关配置

Deep Research 的细节与“上线/回滚”建议见：

- `docs/deep-research-rollout.md`
- `docs/benchmarks/README.md`
