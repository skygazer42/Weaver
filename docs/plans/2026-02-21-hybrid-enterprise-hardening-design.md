# Hybrid Enterprise Hardening (C) Design

> Date: 2026-02-21  
> Scope: Weaver Backend (FastAPI) + Frontend (Next.js) contract alignment  
> Mode: **Hybrid** — default open/dev; when enabled, enforce internal auth + per-user isolation.

## Goal

Weaver should support two deployment modes without code forks:

1. **Default (internal auth disabled)**  
   - Keep the current OSS / local-dev experience: start the backend + web UI and use it directly.
   - No extra headers/tokens needed from the browser.

2. **Enterprise Internal (internal auth enabled)**  
   - Protect all `/api/*` endpoints (except `/api/webhook/*`) behind an internal API key.
   - Enable **per-user isolation** for thread-scoped resources (sessions, events, export, browser streams, interrupts, etc.).
   - Achieve backend↔frontend contract alignment via **FastAPI OpenAPI → generated TypeScript types**.

Non-goals (for this phase):
- Building a full public multi-tenant login/RBAC product (OIDC/OAuth, user DB, billing, orgs).
- Hardening against an attacker who can bypass the reverse proxy and directly call backend with the internal key (that key must remain private at the gateway).

---

## Configuration (Environment)

Add two optional env vars (documented in `.env.example`):

- `WEAVER_INTERNAL_API_KEY` (string)
  - When non-empty, all `/api/*` are protected (except `/api/webhook/*`).
  - Supports: `Authorization: Bearer <key>` or `X-API-Key: <key>`.

- `WEAVER_AUTH_USER_HEADER` (string, default `X-Weaver-User`)
  - Trusted user identity header injected by an authenticated reverse proxy.
  - Used for per-user isolation of sessions/runs/thread-scoped endpoints.

Operational guidance:
- **Never** expose `WEAVER_INTERNAL_API_KEY` to browser code.
- Inject both the API key and the user header at the proxy layer after auth.

---

## Request Principal Model

When `WEAVER_INTERNAL_API_KEY` is enabled:

1. Authenticate: validate the internal API key.
2. Resolve principal: read `WEAVER_AUTH_USER_HEADER` from the request.
3. Attach to request context: `request.state.principal_id`.

Notes:
- The principal header is only meaningful behind a trusted proxy.
- For “single-user internal” deployments, the header may be omitted and a fallback principal may be used.

---

## Thread Ownership & Authorization

Problem: thread IDs are sensitive; without guards, users could:
- cancel others’ runs
- read others’ SSE events
- export others’ reports
- watch others’ browser sessions

Design: enforce best-effort ownership at the API boundary when internal auth is enabled:

### Ownership Sources (best-effort)

1. **In-memory registry** (process-local)
   - Bind `thread_id -> principal_id` when threads are created via chat/research endpoints.
   - Works for most live interactions, fast, no DB dependency.

2. **Persisted state via checkpointer** (authoritative when available)
   - Read session state and compare `state.user_id` to the principal.
   - Important for restarts/multi-worker deployments.

### Enforcement

Create a helper like `_require_thread_owner(request, thread_id)` and call it on:
- `/api/events/{thread_id}`
- `/api/export/{thread_id}`
- `/api/browser/{thread_id}/*` (HTTP endpoints)
- `/api/browser/{thread_id}/stream` (WebSocket)
- `/api/interrupt/*` and resume endpoints
- session endpoints referencing `thread_id`

Return:
- `403 Forbidden` when principal exists but does not match owner.

---

## List Filtering (avoid metadata leaks)

When internal auth is enabled:

- `/api/sessions`: filter by principal (`state.user_id`)
- `/api/runs`: filter by thread owner
- triggers: ensure user-scoped CRUD

This prevents one user from learning other users’ thread IDs via lists.

---

## Rate Limiting

Keep simple in-process token bucket (good enough for single instance). When internal auth is enabled:
- identity = `principal_id` (authorized requests)
Else:
- identity = client IP

Attach standard-ish response headers:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

Return `429` with `Retry-After` when exceeded.

---

## Backend ↔ Frontend Contract Alignment

Single source of truth: **FastAPI OpenAPI**.

Workflow:
1. Export OpenAPI JSON (`python scripts/export_openapi.py`)
2. Generate TypeScript types (`pnpm -C web exec openapi-typescript ...`)
3. Drift guard (`bash scripts/check_openapi_ts_types.sh`) must be clean.

Frontend uses generated types in `web/lib/api-types.ts`.

---

## Reference Projects (ideas-only, do not vendor)

We may clone these repos locally for comparison (not committed to Weaver):
- LangChain `open_deep_research`
- `gpt-researcher`
- Stanford OVAL `storm`

Focus areas to borrow:
- evidence organization (passages/quotes)
- quality gates and evaluation loops
- robust retry/fallback for web research providers

