# Research API Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 打通前端 `/research` 指令与后端 Research 流式接口，让 Research 与 Chat 一样具备一致的流式协议、`X-Thread-ID`、取消能力，并通过 `.env` 可配置协议（SSE vs legacy）。

**Architecture:** 后端新增 `POST /api/research/sse`（标准 SSE）作为“翻译层”：复用现有 `stream_agent_events()` 产出的 legacy `0:{json}\n` 行协议，再翻译成标准 SSE `event/data` 帧；同时保留 `POST /api/research`（legacy）但补齐 `thread_id` 生成与 `X-Thread-ID` header。前端新增 Research stream 配置与 `processResearch()`，并在 Chat UI 支持 `/research <query>` 路由到 Research 流。

**Tech Stack:** Python 3.11, FastAPI, StreamingResponse, pytest + httpx(ASGITransport); Next.js 16, TypeScript, pnpm, eslint, openapi-typescript.

---

## Milestone Commit Policy (≤ 5)

- **Milestone 1 (plan/docs):** 本计划文档 + `.env` 示例更新
- **Milestone 2 (backend):** `/api/research` header + `/api/research/sse` + tests
- **Milestone 3 (frontend):** `/research` 指令 + stream consumer + command palette + build/lint
- **Milestone 4 (contract):** OpenAPI TS types regenerate + drift guard
- **Milestone 5 (polish):** 文档与边界条件修正（可选）

---

## Phase 0 — Baseline

### Task 1: Verify backend tests are runnable

**Files:** none

**Step 1: Run a fast sanity subset**

Run: `pytest -q tests/test_chat_sse_headers.py`  
Expected: PASS

**Step 2: Run web lint (fast)**

Run: `pnpm -C web lint`  
Expected: PASS

---

## Phase 1 — Backend Research SSE + Thread Header

### Task 2: Add failing test for `/api/research/sse` thread header (RED)

**Files:**
- Create: `tests/test_research_sse_headers.py`

**Step 1: Write failing test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_research_sse_sets_thread_header_even_on_error(monkeypatch):
    # Force deterministic error path like /api/chat/sse
    monkeypatch.setattr(main.settings, "openai_api_key", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/research/sse", json={"query": "hi"})
        assert resp.status_code == 200
        assert resp.headers.get("X-Thread-ID")
```

**Step 2: Run test**

Run: `pytest -q tests/test_research_sse_headers.py`  
Expected: FAIL (404 / endpoint missing)

---

### Task 3: Implement `POST /api/research/sse` endpoint (GREEN)

**Files:**
- Modify: `main.py`
- Test: `tests/test_research_sse_headers.py`

**Step 1: Add request model**

Add a `ResearchRequest` model similar to `ChatRequest`:
- `query: str`
- `model/search_mode/agent_id/user_id/images` (optional)

**Step 2: Add endpoint**

Add:
- `@app.post("/api/research/sse")`
- Generate `thread_id = f"thread_{uuid.uuid4().hex}"`
- If no `OPENAI_API_KEY` configured:
  - emit SSE `error` then `done` (no graph run)
- Else:
  - call `stream_agent_events(query, thread_id=..., model=..., search_mode=..., agent_id=..., images=..., user_id=...)`
  - wrap with `iter_with_sse_keepalive(...)`
  - translate each `0:` line via `translate_legacy_line_to_sse(...)`
- Always set response header `X-Thread-ID` to the generated thread id.

**Step 3: Run test**

Run: `pytest -q tests/test_research_sse_headers.py`  
Expected: PASS

---

### Task 4: Add `X-Thread-ID` + unique thread id to legacy `POST /api/research`

**Files:**
- Modify: `main.py`

**Step 1: Add thread id generation**

In the existing `/api/research` endpoint:
- generate `thread_id = f"thread_{uuid.uuid4().hex}"`
- call `stream_agent_events(query, thread_id=thread_id, ...)`
- include headers like `/api/chat` (`Cache-Control`, `Connection`, `X-Accel-Buffering`, `X-Thread-ID`)

**Step 2: Verify quickly (manual)**

Run: `pytest -q tests/test_smoke_api.py::test_cancel_endpoints_smoke`  
Expected: PASS

---

## Phase 2 — Frontend `/research` Command + Stream Consumer

### Task 5: Add web env var for research protocol

**Files:**
- Modify: `web/.env.local.example`

**Step 1: Add config**

Add:
- `NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=sse` (or `legacy`)

**Step 2: Verify**

Run: `cat web/.env.local.example`  
Expected: contains the new variable and comments.

---

### Task 6: Add `getResearchStreamProtocol/getResearchStreamUrl` (RED→GREEN)

**Files:**
- Modify: `web/lib/api.ts`

**Step 1: Add types**

Add:
- `export type ResearchStreamProtocol = 'sse' | 'legacy'`
- `export function getResearchStreamProtocol(): ResearchStreamProtocol`
- `export function getResearchStreamUrl(query?: string): string`

Rules:
- `legacy` → `/api/research?query=...`
- `sse` → `/api/research/sse`

**Step 2: Verify build**

Run: `pnpm -C web build`  
Expected: PASS

---

### Task 7: Implement `processResearch()` in `useChatStream` + reuse stream consumer

**Files:**
- Modify: `web/hooks/useChatStream.ts`

**Step 1: Add shared `consumeStream(response, protocol)` helper**

Support:
- `legacy`: parse `0:{json}\n` line protocol
- `sse`: parse `event:`/`data:` frames
- Extract and store `X-Thread-ID` (both chat + research)

**Step 2: Add `processResearch(query, images?)`**

Behavior:
- If query empty → append assistant error message `Usage: /research <query>`
- Start loading, attempt stream with retry/backoff similar to chat
- Call `consumeStream(...)`

**Step 3: Verify**

Run: `pnpm -C web lint`  
Expected: PASS

---

### Task 8: Route `/research <query>` in Chat submit/edit path

**Files:**
- Modify: `web/components/chat/Chat.tsx`

**Step 1: Update submit handler**

If user input matches `/research ...`:
- still append user message to chat
- call `processResearch(query, imagePayloads)` instead of `processChat(...)`

**Step 2: Update edit handler**

If edited user message becomes `/research ...`, rerun research stream.

**Step 3: Verify**

Run: `pnpm -C web build`  
Expected: PASS

---

### Task 9: Add “Research” to Command Palette + template

**Files:**
- Modify: `web/components/chat/input/CommandPalette.tsx`
- Modify: `web/components/chat/input/command-templates.ts`

**Step 1: Add command entry**

Add:
- `{ id: 'research', label: 'Research', icon: Search, desc: 'Run a research job (SSE)' }`

**Step 2: Add template**

Add:
- `case 'research': return '/research '`

**Step 3: Verify**

Run: `pnpm -C web lint`  
Expected: PASS

---

## Phase 3 — Contract / Types

### Task 10: Regenerate OpenAPI TS types + drift guard

**Files:**
- Modify (generated): `web/lib/api-types.ts`
- Modify (generated): `sdk/typescript/src/openapi-types.ts`

**Step 1: Run generator**

Run: `bash scripts/check_openapi_ts_types.sh`  
Expected: exits 0 and no git diff for the generated files.

---

## Phase 4 — Verification + Milestone Commit

### Task 11: Run verification commands

Run:
- `pytest -q tests/test_research_sse_headers.py`
- `pnpm -C web lint`
- `pnpm -C web build`

Expected: all PASS

---

### Task 12: Commit milestones (≤ 5)

**Milestone 1 (docs + env example):**

```bash
git add docs/plans/2026-02-20-research-api-alignment-plan.md web/.env.local.example
git commit -m "docs(plan): research api alignment"
```

**Milestone 2–4:** follow the policy above; avoid micro-commits.

