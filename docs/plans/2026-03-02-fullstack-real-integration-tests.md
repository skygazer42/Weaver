# Full-Stack Real Integration Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make backend + frontend run reliably on a predictable port and run real (non-mocked) API + UI end-to-end tests (including Browser WebSocket live stream), then commit + push fixes.

**Architecture:** Use the existing real-HTTP smoke test (`scripts/live_api_smoke.py`) and the existing Playwright full-stack e2e (`web/e2e/fullstack.spec.ts`). Fix environment precedence (PORT selection) and proxy leakage so local shells and CI are deterministic.

**Tech Stack:** FastAPI + Uvicorn (Python), httpx/websockets (smoke tests), Next.js (web), Playwright (e2e), OpenAPI (type generation).

---

### Task 1: Lock backend port via `.env` (local-only)

**Files:**
- Modify (local, not committed): `.env`
- Reference: `.env.example`

**Step 1: Update `.env` to include a stable port**

- Add:
  - `PORT=8001`
  - `WEAVER_BASE_URL=http://127.0.0.1:8001`

**Step 2: Verify backend uses the port**

Run: `python -c "from common.config import settings; print(settings.port)"`
Expected: prints `8001`

---

### Task 2: Make Playwright e2e port selection deterministic

**Files:**
- Modify: `web/playwright.config.ts`
- Test: `pnpm -C web e2e`

**Step 1: Fix backend port precedence**

- Prefer repo `.env` `PORT` over `process.env.PORT` to avoid stale shell vars hijacking e2e runs.

**Step 2: Sanitize proxy env for e2e web servers**

- Ensure `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` (and lowercase variants) do not leak into:
  - backend uvicorn webServer
  - Next dev webServer

**Step 3: Verify e2e passes (headless)**

Run: `pnpm -C web e2e`
Expected: `web/e2e/fullstack.spec.ts` passes

---

### Task 3: Make live API smoke test exercise SSE endpoints with valid payloads

**Files:**
- Modify: `scripts/live_api_smoke.py`
- Test: `python scripts/live_api_smoke.py --ws --timeout 30`

**Step 1: Ensure server env does not inherit proxies**

- Clear proxy env vars in the server subprocess environment in `_env_for_server()`.

**Step 2: Cover SSE endpoints with real payloads**

- For OpenAPI sweep:
  - `/api/chat/sse` should be requested with a minimal valid `ChatRequest` and treated as a streaming endpoint.
  - `/api/research/sse` should be requested with a minimal valid `ResearchRequest` and treated as a streaming endpoint.

**Step 3: Run the smoke test**

Run: `python scripts/live_api_smoke.py --ws --timeout 30 --out /tmp/weaver-live-api-smoke.json`
Expected: exit code `0` and `fail=0`

---

### Task 4: Run backend unit tests and OpenAPI type drift checks

**Files:**
- Modify (if drift): `web/lib/api-types.ts`
- Modify (if drift): `sdk/typescript/src/openapi-types.ts`
- Test: `pytest`, `bash scripts/check_openapi_ts_types.sh`

**Step 1: Run pytest**

Run: `pytest -q`
Expected: exit code `0`

**Step 2: Verify OpenAPI TypeScript types are in sync**

Run: `bash scripts/check_openapi_ts_types.sh`
Expected: `git diff` clean for generated TS files

---

### Task 5: E2E headed run (visual) for parity

**Files:**
- Test: `pnpm -C web e2e:headed`

**Step 1: Run headed e2e**

Run: `pnpm -C web e2e:headed`
Expected: `web/e2e/fullstack.spec.ts` passes in headed mode

---

### Task 6: Commit + push

**Files:**
- Modify: (whatever changed above)

**Step 1: Ensure runtime artifacts are not staged**

Run: `git status --porcelain`
Expected: only source files / docs are modified (no `data/`, no `screenshots/`, no `.env`)

**Step 2: Commit**

Run: `git add -A && git commit -m "test(e2e): stabilize real full-stack integration tests"`

**Step 3: Push**

Run: `git push`

