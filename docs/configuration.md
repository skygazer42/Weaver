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

硅基流动 SiliconFlow（开箱即用，默认 `deepseek-ai/DeepSeek-V4.1-Flash` 并自动暴露模型目录）：

```bash
SILICONFLOW_API_KEY=sk-...
```

OpenAI：

```bash
OPENAI_API_KEY=sk-...
```

DeepSeek（OpenAI 兼容）：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
PRIMARY_MODEL=deepseek-chat
REASONING_MODEL=deepseek-chat
```

Anthropic（Claude）：

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### 搜索（Deep/Web 模式常用）

```bash
TAVILY_API_KEY=tvly-...
```

### 代码执行沙盒（二选一，均可选）

方式 A：E2B 云端沙盒：

```bash
E2B_API_KEY=e2b_...
```

方式 B：本地免费 Docker 沙盒（**默认关闭**，开启后无需 E2B 即可复用 `execute_python_code`、`sandbox_files`、`sandbox_shell`）：

1. 启动本机 Docker Desktop / Docker Engine，并拉取默认镜像：

```bash
docker info
docker pull python:3.12-slim
```

2. 在根目录 `.env` 中开启（也可通过 `SANDBOX_MODE=docker` 开启）：

```bash
ENABLE_DOCKER_SANDBOX=true
DOCKER_SANDBOX_IMAGE=python:3.12-slim
DOCKER_SANDBOX_CPUS=1.0
DOCKER_SANDBOX_MEMORY=512m
DOCKER_SANDBOX_PIDS_LIMIT=128
DOCKER_SANDBOX_NETWORK_ENABLED=false
DOCKER_SANDBOX_TIMEOUT_SECONDS=60
# 可选：自定义宿主机工作区根目录（留空则使用系统临时目录）
# DOCKER_SANDBOX_WORK_ROOT=
```

> 安全默认：本地 Docker 沙盒默认关闭网络（`--network none`）、移除所有 Linux Capabilities（`--cap-drop ALL`）、禁止提权（`--security-opt no-new-privileges`），按线程挂载独立 `/workspace` 目录并在后端退出时自动清理容器。如需容器内预装 `pandas`/`matplotlib` 进行离线数据分析与出图，将 `DOCKER_SANDBOX_IMAGE` 替换为自定义镜像即可。

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

---

## 高阶环境变量速查（均有内置默认值）

根目录 `.env.example` 只保留高频起步项；如需深度调优，可按需在 `.env` 中覆盖以下参数（完整字段与类型定义见 `common/config.py`）：

| 分组 | 常用环境变量 | 说明 |
|------|--------------|------|
| 模型与工具策略 | `OPENAI_TIMEOUT`、`OPENAI_EXTRA_BODY`、`PROMPT_STYLE`、`AGENT_NATIVE_TOOL_CALLING`、`AGENT_XML_TOOL_CALLING`、`AGENT_TOOL_EXECUTION_STRATEGY` | 超时、提示词风格与工具调用策略 |
| 多引擎聚合搜索 | `SEARCH_ENGINES`、`SEARCH_STRATEGY`、`SERPER_API_KEY`、`BRAVE_API_KEY`、`EXA_API_KEY`、`FIRECRAWL_API_KEY`、`SEARCH_CACHE_TTL_SECONDS` | 搜索降级/并发策略、多引擎密钥与缓存 |
| 深度研究与门禁 | `DEEPSEARCH_MAX_EPOCHS`、`DEEPSEARCH_QUERY_NUM`、`DEEPSEARCH_RESULTS_PER_QUERY`、`DEEPSEARCH_REPORT_SOURCES_LIMIT`、`CITATION_GATE_MIN_COVERAGE`、`MAX_REVISIONS` | 深搜迭代轮次、引用覆盖率门禁与修订次数 |
| 网页正文抓取 | `READER_FALLBACK_MODE`、`READER_PUBLIC_BASE`、`RESEARCH_FETCH_TIMEOUT_S`、`RESEARCH_FETCH_CONCURRENCY`、`RESEARCH_FETCH_RENDER_MODE` | 证据抓取超时、并发与 Reader 兜底 |
| 上下文与记忆 | `TRIM_MESSAGES`、`SUMMARY_MESSAGES`、`MEMORY_STORE_BACKEND`、`MEMORY_STORE_URL`、`MEMORY_TOP_K` | 长对话截断摘要与长期记忆存储 |
| 日志与可观测性 | `LOG_LEVEL`、`LOG_FILE`、`ENABLE_FILE_LOGGING`、`ENABLE_JSON_LOGGING`、`ENABLE_PROMETHEUS` | 日志轮转、JSON 日志与 Prometheus `/metrics` |
| 安全与限流 | `APP_ENV`、`WEAVER_INTERNAL_API_KEY`、`WEAVER_AUTH_USER_HEADER`、`RATE_LIMIT_ENABLED`、`RATE_LIMIT_CHAT_PER_MINUTE` | 内网鉴权头、用户隔离与限流策略 |
