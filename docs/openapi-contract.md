# OpenAPI Contract (Backend ↔ Frontend)

Weaver uses **FastAPI OpenAPI** as the single source of truth for the API contract.

The frontend consumes generated TypeScript types in `web/lib/api-types.ts` (generated via `openapi-typescript`).
The internal TypeScript SDK consumes generated types in `sdk/typescript/src/openapi-types.ts`.
To prevent “silent drift” between backend responses and frontend assumptions, CI enforces that the generated types are up-to-date.

---

## Key Rules

1. **Backend changes must be reflected in OpenAPI**
   - Prefer `response_model=...` (and typed request bodies) for high-traffic endpoints.
   - Avoid returning untyped `dict` shapes for contract-critical endpoints.
2. **Frontend must not hand-maintain API shapes**
   - Treat `web/lib/api-types.ts` as generated output.
3. **No drift allowed**
   - If backend OpenAPI changes, re-generate and commit `web/lib/api-types.ts`.

---

## Local Workflow

### 1) Export OpenAPI JSON (offline, no server required)

```bash
python scripts/export_openapi.py --output /tmp/weaver-openapi.json
```

### 2) Generate frontend TS types from OpenAPI

```bash
pnpm -C web api:types
```

This writes:

- `web/lib/api-types.ts`
- `sdk/typescript/src/openapi-types.ts`

### 3) Verify drift guard (must be clean)

```bash
bash scripts/check_openapi_ts_types.sh
```

Expected: exit code 0 and no `git diff` for `web/lib/api-types.ts` or `sdk/typescript/src/openapi-types.ts`.

---

## CI Drift Guard

CI runs the drift guard automatically:

- Test job exports the OpenAPI spec as an artifact.
- Frontend job downloads it and re-generates `web/lib/api-types.ts`.
- CI fails if generation changes the committed file.

If CI fails:

1. Run `pnpm -C web api:types` locally
2. Commit the updated `web/lib/api-types.ts`

---

## Common Failure Modes

### “Why did OpenAPI change but types didn’t?”

- A backend endpoint changed shape but did not use `response_model=...`.
- The endpoint returns a raw `dict` with “hidden” fields.

Fix:

- Add/adjust Pydantic models and `response_model=...`
- Re-generate TS types and commit.

### “openapi export fails (missing imports / deps)”

- `scripts/export_openapi.py` imports `main` and requires backend dependencies installed.

Fix:

- Run `make setup` first (or install requirements).
