# Backend Optimization (20 Tasks) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Weaver’s FastAPI backend more reliable, more debuggable, and easier to run locally/CI (especially streaming + browser live view), while keeping frontend ↔ backend contract aligned.

**Architecture:** Keep the current FastAPI monolith (`main.py`) but improve the “edges” first: dev server ergonomics, streaming robustness (SSE/WS), sandbox/browser diagnostics, safe config defaults, and verification automation. Avoid large refactors unless a change pays for itself with measurable stability.

**Tech Stack:** FastAPI/Starlette + Uvicorn, httpx, Prometheus client, Playwright (CDP), E2B sandbox, Next.js frontend, Playwright e2e.

---

## References (web research)

These projects/papers are used as “what good looks like” for research-agent backends:

- GPT-Researcher: https://github.com/assafelovic/gpt-researcher
- Open Deep Research: https://github.com/langchain-ai/open_deep_research
- LangGraph Deep Research (full-stack app): https://github.com/foreveryh/langgraph-deep-research
- Agent Service Toolkit (LangGraph + FastAPI service template): https://github.com/JoshuaC215/agent-service-toolkit
- DeepResearchAgent: https://github.com/SkyworkAI/DeepResearchAgent
- DeerFlow: https://github.com/bytedance/deer-flow
- MiroThinker: https://github.com/MiroMindAI/MiroThinker

Streaming best practices we align with:

- MDN: Using server-sent events (SSE): https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- Starlette/FastAPI: detect disconnect via `request.is_disconnected()`: https://stackoverflow.com/questions/61181083/fastapi-detect-when-connection-is-lost-for-asyncio-task

---

## Phase A — Dev Server Reliability (Tasks 1–5)

### Task 1: Fix `scripts/dev.sh` reload watch-limit crash

**Files:**
- Modify: `scripts/dev.sh`
- Reference: `main.py` (reload strategy)

**Step 1: Write a regression check (manual)**

Run: `./scripts/dev.sh`
Expected: backend + frontend start without crashing with “OS file watch limit reached”.

**Step 2: Implement**
- Default to **no reload** (or safe reload dirs) for backend.
- Add an opt-in for reload (env `WEAVER_RELOAD=1`) that avoids watching `web/node_modules`.

**Step 3: Verify**
- Start/stop once.
- Confirm backend port printed matches `.env` `PORT`.

**Step 4: Commit**
- `git commit -m "fix(dev): make scripts/dev.sh robust (no watchfiles crash)"`

---

### Task 2: Make `python main.py` hot-reload safe when opt-in

**Files:**
- Modify: `main.py` (uvicorn.run call in `__main__`)
- Test: `pytest -q` (smoke)

**Step 1: Write failing unit test**
- Add a small helper (new module) that returns safe `reload_dirs` for uvicorn.
- Test that `web/node_modules` is never included.

**Step 2: Implement helper + wire it**
- When `WEAVER_RELOAD=1`, pass `reload_dirs=[agent, common, tools, triggers, tests?]` (no `web/`).

**Step 3: Verify**
Run: `WEAVER_RELOAD=1 DEBUG=true python main.py`
Expected: starts without watch limit errors.

**Step 4: Commit**
- `git commit -m "fix(dev): constrain uvicorn reload dirs"`

---

### Task 3: Update port guidance docs (avoid conflicting “60006” advice)

**Files:**
- Modify: `docs/configuration.md`
- Modify (optional): `.env.example`

**Step 1: Update docs**
- Keep default `8001`.
- Recommend choosing a free port (examples: `18080`, `28001`) instead of hardcoding `60006`.
- Document `WEAVER_RELOAD=1` behavior.

**Step 2: Verify**
- `rg -n \"60006\" docs/configuration.md` should not recommend it as a default.

**Step 3: Commit**
- `git commit -m "docs: clarify port + reload configuration"`

---

### Task 4: Add Makefile targets for full local verification

**Files:**
- Modify: `Makefile`

**Step 1: Add targets**
- `make dev` (backend only, no reload)
- `make verify` (pytest + OpenAPI drift + live API smoke + web e2e headless)

**Step 2: Verify**
- `make verify` exits 0 in a configured env.

**Step 3: Commit**
- `git commit -m "chore(make): add dev + verify targets"`

---

### Task 5: Add a single script for “real” full-stack verification

**Files:**
- Create: `scripts/verify_fullstack.sh`

**Step 1: Implement**
- Runs:
  - `pytest -q`
  - `bash scripts/check_openapi_ts_types.sh`
  - `python scripts/live_api_smoke.py --ws --timeout 30`
  - `pnpm -C web e2e`
  - `xvfb-run -a pnpm -C web e2e:headed`
- Strips proxy env vars for subprocesses (determinism).

**Step 2: Verify**
Run: `bash scripts/verify_fullstack.sh`
Expected: exit code 0.

**Step 3: Commit**
- `git commit -m "test: add one-command full-stack verification"`

---

## Phase B — Streaming + Browser Live View (Tasks 6–14)

### Task 6: Add a reusable “abort on disconnect” SSE wrapper

**Files:**
- Modify: `common/sse.py`
- Test: `tests/test_sse_disconnect_abort.py` (new)

**Step 1: Write failing test**
- A source generator that never ends.
- A fake `is_disconnected()` that flips true.
- Expect the wrapper to stop iteration promptly (no hang).

**Step 2: Implement**
- Add `iter_abort_on_disconnect(source, is_disconnected, check_interval_s=...)`.

**Step 3: Commit**
- `git commit -m "feat(sse): stop generators on client disconnect"`

---

### Task 7: Wire disconnect abort into `/api/chat/sse` and `/api/research/sse`

**Files:**
- Modify: `main.py` (`chat_sse`, `research_sse`)
- Test: `pytest -q` (existing SSE header/keepalive tests)

**Step 1: Write failing test (unit-level)**
- Patch `stream_agent_events` to block.
- Patch `request.is_disconnected()` to return true.
- Expect the endpoint generator to stop.

**Step 2: Implement**
- Wrap the generator with `iter_abort_on_disconnect`.

**Step 3: Commit**
- `git commit -m \"fix(sse): cancel streams on disconnect\"`

---

### Task 8: Emit an SSE `retry:` frame at stream start (standards-friendly)

**Files:**
- Modify: `common/sse.py`
- Modify: `main.py` (SSE endpoints)
- Test: `tests/test_sse_retry.py` (new)

**Step 1: Write failing test**
- `format_sse_retry(2000)` renders `retry: 2000\\n\\n`.

**Step 2: Implement + wire**
- `chat_sse`/`research_sse` yield retry frame first.

**Step 3: Commit**
- `git commit -m \"feat(sse): add retry hint for reconnect\"`

---

### Task 9: Improve WS live stream status transparency

**Files:**
- Modify: `main.py` (`/api/browser/{thread_id}/stream`)
- Test: `tests/test_browser_ws_status_payload.py` (new unit test)

**Step 1: Write failing test**
- Ensure the first `status` message includes:
  - `thread_id`
  - chosen capture mode (`e2b`)
  - whether CDP screencast is running

**Step 2: Implement**
- Send richer `status` payloads (no breaking changes for existing fields).

**Step 3: Commit**
- `git commit -m \"feat(ws): enrich browser stream status messages\"`

---

### Task 10: Add sandbox/browser diagnostics endpoint (fast path)

**Files:**
- Modify: `main.py` (new endpoint)
- Test: `tests/test_sandbox_diagnose.py`

**Step 1: Write failing test**
- No `E2B_API_KEY` configured → endpoint returns `ready=false` and actionable `missing=["E2B_API_KEY"]`.

**Step 2: Implement**
- `GET /api/sandbox/browser/diagnose`:
  - validates required env/config
  - does NOT cold-start E2B

**Step 3: Commit**
- `git commit -m \"feat(sandbox): add browser diagnose endpoint\"`

---

### Task 11: Add sandbox/browser diagnostics endpoint (deep path, opt-in)

**Files:**
- Modify: `main.py`
- Modify: `tools/sandbox/sandbox_browser_session.py` (optional helper)

**Step 1: Implement**
- `GET /api/sandbox/browser/diagnose?deep=1` best-effort:
  - create sandbox
  - connect CDP
  - capture one frame
  - returns latency + error category if fails

**Step 2: Verify (manual)**
- Run once with real env; confirm it returns a screenshot byte size or frame_id.

**Step 3: Commit**
- `git commit -m \"feat(sandbox): add deep browser self-test\"`

---

### Task 12: Make WS stream fall back to clearer errors when sandbox not ready

**Files:**
- Modify: `main.py`

**Step 1: Implement**
- If `E2B_API_KEY` missing/placeholder, return a user-facing error:
  - “E2B is required for live browser stream; set E2B_API_KEY and SANDBOX_TEMPLATE_BROWSER”.

**Step 2: Commit**
- `git commit -m \"fix(ws): actionable errors for sandbox misconfig\"`

---

### Task 13: Add metrics for active SSE/WS connections (observability)

**Files:**
- Modify: `main.py`
- Test: `tests/test_metrics_includes_stream_gauges.py` (new)

**Step 1: Write failing test**
- `/metrics` output contains gauge names for SSE/WS counts (when enabled).

**Step 2: Implement**
- Track counts with Prometheus `Gauge`.

**Step 3: Commit**
- `git commit -m \"feat(metrics): track streaming connection gauges\"`

---

### Task 14: Add a tiny “public config” endpoint for frontend bootstrapping

**Files:**
- Modify: `main.py`
- Test: `tests/test_public_config_endpoint.py`

**Step 1: Implement**
- `GET /api/config/public` returns safe, non-secret config:
  - `stream_protocols` (chat/research)
  - `features` (mcp enabled, sandbox mode)
  - `defaults` (port, models)

**Step 2: Commit**
- `git commit -m \"feat(api): add public config endpoint\"`

---

## Phase C — Backend Performance/Footguns (Tasks 15–20)

### Task 15: Bound in-memory rate-limit buckets to avoid unbounded growth

**Files:**
- Modify: `main.py` (rate limit bucket structure)
- Modify: `common/config.py` (new setting `RATE_LIMIT_MAX_BUCKETS`)
- Test: `tests/test_rate_limit_bucket_eviction.py`

**Step 1: Write failing test**
- Force creating > max buckets, expect dict size is capped.

**Step 2: Implement**
- Use an `OrderedDict` LRU or periodic eviction.

**Step 3: Commit**
- `git commit -m \"fix(rate-limit): cap bucket memory usage\"`

---

### Task 16: Reuse httpx client in `BrowserSession` (less overhead)

**Files:**
- Modify: `tools/browser/browser_session.py`
- Test: `tests/test_browser_session_reuses_httpx_client.py` (new)

**Step 1: Write failing test**
- Patch `httpx.Client` to count instantiations; expect only 1 per session across navigations.

**Step 2: Implement**
- Keep a session-level `httpx.Client` and close it on reset.

**Step 3: Commit**
- `git commit -m \"perf(browser): reuse httpx client in BrowserSession\"`

---

### Task 17: Add endpoints to introspect and clear search cache

**Files:**
- Modify: `main.py`
- Test: `tests/test_search_cache_endpoints.py` (new)

**Step 1: Implement**
- `GET /api/search/cache/stats`
- `POST /api/search/cache/clear`

**Step 2: Commit**
- `git commit -m \"feat(search): add cache stats + clear endpoints\"`

---

### Task 18: Improve OpenAPI coverage for new endpoints + keep TS types in sync

**Files:**
- Modify: `main.py` (response_model where helpful)
- Modify (generated): `web/lib/api-types.ts`, `sdk/typescript/src/openapi-types.ts`
- Test: `bash scripts/check_openapi_ts_types.sh`

**Step 1: Implement**
- Add Pydantic models for new endpoints (public config, sandbox diagnose, cache stats).

**Step 2: Verify**
Run: `make openapi-types`
Expected: no drift.

**Step 3: Commit**
- `git commit -m \"chore(openapi): model new backend endpoints\"`

---

### Task 19: Extend live API smoke to cover new endpoints (real HTTP)

**Files:**
- Modify: `scripts/live_api_smoke.py`

**Step 1: Implement**
- Add probes for:
  - `/api/config/public`
  - `/api/sandbox/browser/diagnose`
  - `/api/search/cache/stats`

**Step 2: Verify**
Run: `python scripts/live_api_smoke.py --timeout 30`
Expected: all new checks pass.

**Step 3: Commit**
- `git commit -m \"test(smoke): cover new backend diagnostics endpoints\"`

---

### Task 20: Final verification + push

**Files:**
- Modify: (whatever changed above)

**Step 1: Run full verification**
Run: `bash scripts/verify_fullstack.sh`
Expected: exit code 0.

**Step 2: Push**
Run: `git push`
