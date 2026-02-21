# Hybrid Enterprise Hardening (C) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Weaver “enterprise-internal ready” via optional internal auth + per-user isolation, while keeping default dev flow unchanged, and keep backend↔frontend API contract aligned via OpenAPI-generated TS types.

**Architecture:** Implement an internal-auth gate in HTTP middleware, resolve a trusted principal header for isolation, enforce thread ownership on thread-scoped endpoints, filter list endpoints, and validate drift via OpenAPI type generation.

**Tech Stack:** FastAPI, Pydantic Settings, LangGraph checkpointer, Next.js (generated OpenAPI TS types), pytest.

---

### Task 1: Add internal auth env vars template

**Files:**
- Modify: `.env.example`

**Steps:**
1. Add `WEAVER_INTERNAL_API_KEY` and `WEAVER_AUTH_USER_HEADER` with comments.
2. Verify `rg WEAVER_INTERNAL_API_KEY .env.example` shows the new section.

---

### Task 2: Load settings fields for internal auth

**Files:**
- Modify: `common/config.py`

**Steps:**
1. Add `internal_api_key` + `auth_user_header` to Settings with env aliases.
2. Run: `make test`
3. Expected: PASS

---

### Task 3: Implement internal auth + rate limit in middleware

**Files:**
- Modify: `main.py` (HTTP middleware)

**Steps:**
1. Authenticate `/api/*` requests when internal auth enabled (except `/api/webhook/*`).
2. Resolve principal from `WEAVER_AUTH_USER_HEADER` into `request.state.principal_id`.
3. Apply token-bucket rate limiting and attach `X-RateLimit-*` headers.
4. Run: `make test`

---

### Task 4: Add thread ownership registry (best-effort)

**Files:**
- Create: `common/thread_ownership.py`
- Modify: `main.py` (set owner on thread creation)

**Steps:**
1. Add an in-memory mapping `thread_id -> owner_id` with TTL pruning.
2. Bind owner when chat/research threads are created.
3. Run: `make test`

---

### Task 5: Enforce thread ownership on thread-scoped endpoints

**Files:**
- Modify: `main.py` (add `_require_thread_owner(...)` and call sites)

**Steps:**
1. Create `_require_thread_owner(request, thread_id)`:
   - no-op when internal auth disabled
   - 403 when principal mismatches owner (in-memory and persisted state if available)
2. Apply it to endpoints that read/write thread scoped data.
3. Add/adjust tests for representative endpoints.

---

### Task 6: Filter sessions list by principal (internal auth enabled)

**Files:**
- Modify: `common/session_manager.py`
- Modify: `main.py` (`/api/sessions`)

**Steps:**
1. Add optional `user_id_filter` in session manager list.
2. Pass principal filter when internal auth enabled.
3. Add unit test for filtering.

---

### Task 7: Add internal auth regression tests

**Files:**
- Create: `tests/test_internal_api_auth.py`
- Create: `tests/test_*auth*.py` (thread-scoped enforcement)

**Steps:**
1. Assert 401 when internal key enabled but missing auth header.
2. Assert 403 when thread owner mismatch on a representative endpoint.
3. Run: `make test`

---

### Task 8: Verify OpenAPI drift guard

**Files:**
- Modify: `web/lib/api-types.ts` (generated) (only if drift exists)
- Modify: `sdk/typescript/src/openapi-types.ts` (generated) (only if drift exists)

**Steps:**
1. Run: `make openapi-types`
2. Expected: exit 0 and clean diff.

---

### Task 9: Clone reference repos locally (ignored)

**Files:**
- Modify: `.gitignore` (if needed)
- Create: local dir `third_party/research_refs/` (git-ignored)

**Steps:**
1. Clone reference projects with `--depth 1` into an ignored folder.
2. Do not commit third-party code.

---

### Task 10: Update README with enterprise internal auth docs

**Files:**
- Modify: `README.md`

**Steps:**
1. Document new env vars and recommended reverse proxy injection pattern.
2. Mention rate limit headers and expected 401/403/429 behaviors.
3. Link to `docs/openapi-contract.md` and `docs/mcp.md`.

---

### Task 11: Final verification

**Steps:**
1. Run: `make check`
2. Run: `make openapi-types`
3. (Optional) Run: `pnpm -C web lint` and `pnpm -C web build`

Expected: no failures.

---

### Task 12: Cleanup (delete plan docs)

**Files:**
- Delete: `docs/plans/2026-02-21-hybrid-enterprise-hardening-design.md`
- Delete: `docs/plans/2026-02-21-hybrid-enterprise-hardening.md`
- Delete: `docs/plans/` (if empty)

**Steps:**
1. Remove plan docs after completion, per project preference.

