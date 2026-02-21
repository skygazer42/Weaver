# Tool Reference

Weaver ships with a **tool ecosystem** designed for research + automation workflows.

> Note: The exact tools available can vary depending on optional dependencies and runtime flags (for example E2B / Playwright / MCP / desktop automation).

---

## Tool Categories (high level)

- **Search & Crawl**
  - Web search (provider-backed)
  - URL fetching / content extraction
- **Sandbox (E2B)**
  - File operations
  - Shell commands + package installs
  - Browser automation (screenshots, DOM extraction)
  - Document generation (spreadsheets, presentations)
- **Code Execution**
  - Sandboxed Python execution for analysis and plotting
- **Desktop Automation (optional)**
  - Mouse / keyboard control
  - Screenshot capture
- **MCP Bridge (optional)**
  - Connect to external MCP servers (filesystem, memory, GitHub, etc.)
- **Task Management**
  - Structured task list tools (plan / update / view)

---

## Where tools live in the codebase

- Core registry: `tools/core/registry.py`
- Tool implementations: `tools/**`
- Agent toolset assembly: `agent/workflows/agent_tools.py`, `agent/workflows/nodes.py`
- Agent profiles / enabled tools: `data/agents.json`

---

## Tips

- To understand the exact API contract between backend and frontend, use OpenAPI + generated TS types:
  - `docs/openapi-contract.md`
- For streaming protocol details (SSE vs legacy), see:
  - `docs/chat-streaming.md`
- For MCP configuration, see:
  - `docs/mcp.md`
