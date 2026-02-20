# Weaver Internal SDKs (TypeScript + Python)

Internal-only SDKs for calling Weaver from scripts/services (no npm/PyPI publishing).

## What you get

- **Research-core coverage**: chat streaming, research stream, sessions, evidence, export
- **Protocol support**
  - Chat: standard **SSE** via `POST /api/chat/sse`
  - Research: standard **SSE** via `POST /api/research/sse` (recommended), legacy via `POST /api/research` (Vercel AI “0:{json}\\n”)
- **Contract alignment**: TypeScript SDK types are generated from FastAPI OpenAPI
  - Drift guard: `bash scripts/check_openapi_ts_types.sh`

## Environment

- Server keys/config live in `.env` (copy from `.env.example`)
- SDK examples read `WEAVER_BASE_URL` (defaults to `http://127.0.0.1:8001`)

## TypeScript SDK

- Path: `sdk/typescript/`
- Example:

```bash
WEAVER_BASE_URL=http://127.0.0.1:8001 node sdk/typescript/examples/research.mjs
```

- Build (`dist/` is committed for internal consumption):

```bash
bash sdk/typescript/scripts/build.sh
```

## Python SDK

- Path: `sdk/python/`
- Install (editable, from repo root):

```bash
pip install -e ./sdk/python
```

- Example:

```bash
WEAVER_BASE_URL=http://127.0.0.1:8001 python sdk/python/examples/research.py
```

## When you change backend APIs

1. Regenerate OpenAPI TypeScript outputs:

```bash
bash scripts/check_openapi_ts_types.sh
```

2. Rebuild the TypeScript SDK dist (so Node can consume it directly):

```bash
bash sdk/typescript/scripts/build.sh
```
