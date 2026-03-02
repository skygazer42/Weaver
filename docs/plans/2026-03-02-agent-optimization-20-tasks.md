# Weaver Agent Optimization (Backend) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Weaver’s agent backend feel “production-real”: tools are discoverable/inspectable, enhanced tools are actually usable, search providers are observable, and browser live stream behaves like a real browser (smooth + resilient), with full front/back OpenAPI contract alignment and real end-to-end verification.

**Architecture:** Keep the current FastAPI + LangGraph orchestration intact. Improve the **tooling substrate** (ToolRegistry discovery + introspection), add **provider observability** for multi-search, wire **RAG** into agent tools behind a feature flag, and harden the **browser WS stream** protocol (keepalive/backpressure/retry) so the UI shows continuous frames.

**Tech Stack:** FastAPI, LangGraph/LangChain tools, Pydantic Settings, Playwright (sandbox CDP), Prometheus metrics (optional), OpenAPI → TypeScript typegen, Playwright e2e.

---

### Task 1: Fix `code_executor_enhanced.py` indentation / syntax trap

**Files:**
- Modify: `tools/code/code_executor_enhanced.py`
- Test: `tests/test_python_compiles.py` (new)

**Step 1: Write failing test**

Add a test that imports/compiles the module (it currently gets swallowed by a try/except import).

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_python_compiles.py -v`
Expected: FAIL (SyntaxError / indentation / compile failure)

**Step 3: Fix implementation**

Move the `try:` block out of the `if not code` branch and ensure the `except` matches the correct `try`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_python_compiles.py -v`
Expected: PASS

**Step 5: Commit**

Run:
- `git add tools/code/code_executor_enhanced.py tests/test_python_compiles.py`
- `git commit -m "fix(tools): repair enhanced code executor importability"`

---

### Task 2: Add a repo-wide Python compile gate to `make verify`

**Files:**
- Create: `scripts/check_python_compiles.py`
- Modify: `Makefile`

**Steps:**
- Add a small script that runs `py_compile` across the repo (exclude `web/node_modules`, `.venv`, etc.).
- Wire into `make verify` so we never ship swallowed syntax errors again.

**Commit:** `git commit -m "test(verify): add python compile gate"`

---

### Task 3: Teach ToolRegistry to recognize LangChain BaseTool-bound callables

**Files:**
- Modify: `tools/core/registry.py`
- Test: `tests/tools/test_tool_registry_discovery.py` (new)

**Implementation notes:**
- In `_detect_tool_type`, treat callables whose `__self__` is a `BaseTool` as `langchain`.

**Commit:** `git commit -m "feat(tools): detect langchain bound tools in registry"`

---

### Task 4: Discover and register module-level LangChain BaseTool objects

**Files:**
- Modify: `tools/core/registry.py`
- Test: `tests/tools/test_tool_registry_discovery.py`

**Implementation notes:**
- In `discover_from_module`, scan for `BaseTool` instances at module scope and register them.
- Use `args_schema` to populate `parameters` (Pydantic v2: `model_json_schema()`).

**Commit:** `git commit -m "feat(tools): auto-discover module BaseTool instances"`

---

### Task 5: Make enhanced tool discovery actually scan subpackages (safe defaults)

**Files:**
- Modify: `agent/workflows/nodes.py` (`initialize_enhanced_tools`)
- Modify: `common/config.py` (new settings toggles)

**Implementation notes:**
- Add settings:
  - `enhanced_tool_discovery_enabled` (bool, default true in dev)
  - `enhanced_tool_discovery_recursive` (bool, default true)
  - `enhanced_tool_discovery_exclude_dirs` (csv string, default includes `web/node_modules`, `__pycache__`)
- Use `recursive=True` and excludes to avoid slow imports.

**Commit:** `git commit -m "feat(tools): enable recursive enhanced tool discovery"`

---

### Task 6: Add ToolRegistry introspection endpoints

**Files:**
- Modify: `main.py`
- Modify: `sdk/typescript/src/openapi-types.ts` (regen)
- Modify: `web/lib/api-types.ts` (regen)

**Endpoints:**
- `GET /api/tools/registry` → registry stats + tool list
- `POST /api/tools/registry/refresh` → re-run discovery (dev/internal)

**Commit:** `git commit -m "feat(api): expose tool registry introspection"`

---

### Task 7: Add MultiSearch provider stats endpoint (health + reliability snapshots)

**Files:**
- Modify: `main.py`
- Modify: `tools/search/multi_search.py` (export small helper if needed)

**Endpoint:**
- `GET /api/search/providers/stats`

Payload should include:
- current `search_strategy`
- configured `SEARCH_ENGINES`
- `provider_stats` (orchestrator)
- `reliability` snapshots per provider

**Commit:** `git commit -m "feat(api): expose multi-search provider stats"`

---

### Task 8: Add provider reset endpoint (dev/internal)

**Files:**
- Modify: `main.py`

**Endpoint:**
- `POST /api/search/providers/reset`

**Commit:** `git commit -m "feat(api): add multi-search provider reset endpoint"`

---

### Task 9: Expand `scripts/live_api_smoke.py` to cover new endpoints (real HTTP)

**Files:**
- Modify: `scripts/live_api_smoke.py`

**Steps:**
- Add GET probes for `/api/tools/registry` and `/api/search/providers/stats`
- If internal auth enabled, use existing auth header mechanism.

**Commit:** `git commit -m "test(smoke): probe tool registry + provider stats"`

---

### Task 10: Add RAG tool to agent toolset behind profile flag

**Files:**
- Modify: `agent/workflows/agent_tools.py`
- Modify: `common/config.py` (document tool key in comments, if needed)
- Test: `tests/agent/test_agent_tools_rag.py` (new)

**Implementation notes:**
- New tool key: `rag` (disabled by default)
- If `rag_enabled` and `enabled_tools.rag` is true → add `tools.rag.rag_tool.rag_search`

**Commit:** `git commit -m "feat(agent): enable rag_search tool when configured"`

---

### Task 11: Improve WS browser stream “real browser feel”: frame source + keepalive

**Files:**
- Modify: `main.py` (`/api/browser/{thread_id}/stream`)
- Modify: `web/hooks/useBrowserStream.ts` (handle keepalive + show source)

**Protocol changes:**
- Frames include `source: "cdp" | "screenshot"`
- Server sends `{"type":"ping"}` every ~15s; client ignores or replies.

**Commit:** `git commit -m "feat(ws): add browser stream keepalive + frame source"`

---

### Task 12: Add WS stream backpressure + timeout send (drop frames, don’t stall)

**Files:**
- Modify: `main.py`

**Implementation notes:**
- Wrap `send_json` with `asyncio.wait_for(..., timeout=...)`
- On timeout: drop the frame and continue (do not stop the stream)

**Commit:** `git commit -m "perf(ws): drop frames under backpressure"`

---

### Task 13: Make WS stream resilient to transient capture errors (retry)

**Files:**
- Modify: `main.py`

**Implementation notes:**
- On capture error: emit an error event but keep streaming with exponential backoff; only stop after N consecutive failures.

**Commit:** `git commit -m "fix(ws): retry transient browser capture failures"`

---

### Task 14: Add metrics for search providers + tool registry refresh (optional)

**Files:**
- Modify: `main.py`

**Notes:**
- If Prometheus enabled: expose gauges/counters for provider calls, failures, and active stream mode (`cdp` vs `screenshot`).

**Commit:** `git commit -m "feat(metrics): add provider + browser stream metrics"`

---

### Task 15: OpenAPI contract + TS types drift guard

**Files:**
- Modify: `scripts/check_openapi_ts_types.sh` (if needed)
- Modify: `web/lib/api-types.ts` (regen)
- Modify: `sdk/typescript/src/openapi-types.ts` (regen)

**Steps:**
- Run: `bash scripts/check_openapi_ts_types.sh`
- Ensure no diff after regeneration.

**Commit:** `git commit -m "chore(openapi): update types for agent optimization endpoints"`

---

### Task 16: Add docs for new endpoints + agent tool key

**Files:**
- Modify: `docs/api.md`
- Modify: `docs/configuration.md`

**Commit:** `git commit -m "docs: document tool registry, provider stats, rag tool"`

---

### Task 17: Add/extend e2e assertions for browser stream continuity

**Files:**
- Modify: `web/e2e/fullstack.spec.ts`

**Steps:**
- Assert that at least 3 distinct frames arrive within a short window after LIVE starts.

**Commit:** `git commit -m "test(e2e): assert browser live stream updates continuously"`

---

### Task 18: Add a backend-only “agent health” endpoint (quick self-check)

**Files:**
- Modify: `main.py`

**Endpoint:**
- `GET /api/health/agent` returning:
  - loaded agent profiles count
  - enabled tool keys
  - search providers available
  - rag enabled/disabled

**Commit:** `git commit -m "feat(api): add agent health endpoint"`

---

### Task 19: Wire new health endpoints into `scripts/verify_fullstack.sh`

**Files:**
- Modify: `scripts/verify_fullstack.sh`

**Commit:** `git commit -m "test(verify): include agent health in fullstack verify"`

---

### Task 20: Final verification + push

**Commands (run fresh):**
- `pytest -q`
- `bash scripts/check_openapi_ts_types.sh`
- `python scripts/live_api_smoke.py --ws --timeout 30`
- `pnpm -C web e2e`
- `xvfb-run -a pnpm -C web e2e:headed`

**Commit/push:**
- `git status` must be clean
- `git push`

