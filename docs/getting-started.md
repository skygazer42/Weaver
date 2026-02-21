# 快速开始（本地运行）

这份文档提供比根目录 `README.md` 更完整的本地运行步骤与常见配置说明。

---

## 前置要求

- Python 3.11+
- Node.js 18+（推荐配合 `pnpm`）
- Docker & Docker Compose（可选：用于 PostgreSQL/Redis）
- 至少 1 个 LLM API Key（OpenAI / DeepSeek / Claude 等）

> 仅本地自用：通常只需要把「模型 + 搜索」相关的 key 配好即可；鉴权/多用户隔离/限流属于可选加固项（不影响开发体验）。

---

## 1) 克隆仓库

```bash
git clone https://github.com/skygazer42/weaver.git
cd weaver
```

---

## 2) 配置环境变量

### 后端（根目录 `.env`）

```bash
cp .env.example .env
```

**最小可用配置**（在 `.env` 里填写）：

```bash
# 任选其一：OpenAI / DeepSeek（OpenAI 兼容）/ Anthropic
OPENAI_API_KEY=sk-...
# 或（DeepSeek 兼容 OpenAI 协议）
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.deepseek.com/v1
# 或（Claude）
# ANTHROPIC_API_KEY=sk-ant-...

# 搜索服务（Deep Research / Web 模式会用到）
TAVILY_API_KEY=tvly-...
```

**可选但推荐**：

```bash
# 代码执行（推荐）
E2B_API_KEY=e2b_...

# MCP 工具桥（更多示例见 docs/mcp.md）
ENABLE_MCP=true
MCP_SERVERS={"filesystem":{"type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/ABS/PATH/TO/ALLOW"]},"memory":{"type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-memory"]}}
```

> 安全提示：`server-filesystem` 一定要显式传入“允许访问的目录”，不要直接给根目录。

### 前端（`web/.env.local`）

```bash
cp web/.env.local.example web/.env.local
```

常用配置项：

```bash
# 后端 API 地址（浏览器可访问的地址）
NEXT_PUBLIC_API_URL=http://127.0.0.1:8001

# Chat / Research 流式协议（默认 sse；遇到代理/平台不兼容可切换 legacy）
NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse
NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=sse
```

更多流式协议说明见 `docs/chat-streaming.md`。

---

## 3) 安装依赖

### 后端

```bash
# 创建 .venv 并安装核心 + 开发依赖
make setup

#（可选）安装“重依赖”工具（桌面自动化 / Office 文档 / 爬虫等）
make setup-full
```

### 前端

```bash
pnpm -C web install --frozen-lockfile
```

### Playwright（可选）

如果需要浏览器自动化，安装 Chromium：

```bash
playwright install chromium
```

---

## 4) 启动服务

```bash
# 终端 1：启动后端
.venv/bin/python main.py

# 终端 2：启动前端（默认端口 3100）
pnpm -C web dev
```

访问入口：

- 前端界面：http://localhost:3100
- 后端 API：http://localhost:8001
- OpenAPI 文档：http://localhost:8001/docs
- Metrics：http://localhost:8001/metrics

---

## 5) 常用开发命令

```bash
# 后端：测试 / Lint / 全量检查
make test
make lint
make check

# OpenAPI 合约对齐（后端 ↔ 前端 types，不允许漂移）
make openapi-types

# 前端：测试 / Lint / 构建
pnpm -C web test
pnpm -C web lint
pnpm -C web build
```

OpenAPI 合约对齐说明见 `docs/openapi-contract.md`。
