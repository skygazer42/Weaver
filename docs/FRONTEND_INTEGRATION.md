# Frontend Integration Guide

This document explains how the Next.js frontend connects to the FastAPI backend, with an emphasis on **streaming** and **contract alignment**.

---

## 1) Configure frontend env

Create `web/.env.local`:

```bash
cp web/.env.local.example web/.env.local
```

Minimum config:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8001
NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse
NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=sse
```

---

## 2) Streaming protocols

Weaver supports:

- **SSE (recommended)**: `POST /api/chat/sse`, `POST /api/research/sse`
- **Legacy line protocol (rollback/compat)**: `POST /api/chat`, `POST /api/research`

Protocol details and rollout guidance:

- `docs/chat-streaming.md`

---

## 3) API contract alignment (no drift)

The frontend consumes generated types from OpenAPI.

Local workflow:

```bash
make openapi-types
```

More details:

- `docs/openapi-contract.md`
