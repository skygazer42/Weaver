# Weaver 项目概览

Weaver 是一个 Manus 风格的通用智能体/深度研究应用：

- 后端：FastAPI + LangGraph + LangChain（根目录 `main.py`）
- 前端：Next.js 14（目录 `web/`）
- 工具：Tavily（搜索）、E2B（代码执行）、可选 MCP（多工具桥）
- 记忆：LangGraph store + 可选 Mem0（无则回退本地 JSON）
- 可选能力：Prometheus 指标、DashScope ASR/TTS

## 代码结构

```
Weaver/
  main.py              # FastAPI 入口
  agent/               # LangGraph：state / nodes / graph
  tools/               # search / crawler / code_executor / mcp / memory / asr / tts
  common/              # config / logger / metrics / cancellation 等
  web/                 # Next.js 14 前端
  docs/                # 文档（入口 docs/README.md）
  tests/               # 测试
```

## 文档入口

从这里开始：`docs/README.md`

