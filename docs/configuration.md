# 配置说明

本页汇总 Weaver 常用配置入口：

- 后端：根目录 `.env`（参考 `.env.example`）
- 前端：`web/.env.local`（参考 `web/.env.local.example`）
- Agent 配置：`data/agents.json`
- 触发器：代码/API（视你的接入方式）
- MCP：`ENABLE_MCP` + `MCP_SERVERS`（详见 `docs/mcp.md`）

---

## 后端 `.env`

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
