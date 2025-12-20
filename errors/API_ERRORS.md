# API Endpoint Status / 已知问题

Last updated: 2025-12-20

This file tracks API endpoint status and any known issues. (No emoji to avoid Windows console encoding problems.)

## Current Status

| Endpoint | Method | Status | Notes |
|---|---:|---:|---|
| `/` | GET | OK | Health |
| `/health` | GET | OK | Detailed health |
| `/metrics` | GET | OK/404 | 404 unless `ENABLE_PROMETHEUS=true` |
| `/api/runs` | GET | OK | In-memory run metrics |
| `/api/runs/{id}` | GET | OK/404 | 404 when unknown |
| `/api/memory/status` | GET | OK | Memory backend info |
| `/api/mcp/config` | GET/POST | OK | Works even when MCP disabled |
| `/api/tasks/active` | GET | OK | Fixed: no more `stats` NameError |
| `/api/chat/cancel/{id}` | POST | OK | Fixed: `active_streams` defined |
| `/api/chat/cancel-all` | POST | OK | Fixed: `active_streams` defined |
| `/api/interrupt/resume` | POST | 404/200 | 404 if no checkpoint for `thread_id` |
| `/api/asr/status` | GET | OK | Requires `DASHSCOPE_API_KEY` for enabled=true |
| `/api/asr/upload` | POST | OK/503 | Fixed: `filename` NameError; 503 when ASR not configured |
| `/api/tts/status` | GET | OK | Requires `DASHSCOPE_API_KEY` for enabled=true |
| `/api/tts/voices` | GET | OK | Returns supported voice ids |
| `/api/tts/synthesize` | POST | OK/5xx | Upstream DashScope may return no audio; will surface as error |
| `/api/chat` | POST | OK | Model now respects request `model` (fallback to `PRIMARY_MODEL`) |
| `/api/research` | POST | OK | Streaming SSE |
| `/api/support/chat` | POST | Depends | Requires valid LLM credentials + compatible model |

## Fixes Applied (Code)

1) Cancellation endpoints no longer 500
- `main.py`: `active_streams` is now defined as a real global variable.
- `/api/tasks/active` now returns `cancellation_manager.get_stats()`.

2) ASR upload no longer throws `filename is not defined`
- `main.py`: split the comment+assignment line into a real `filename = ...` statement.

3) Interrupt resume is safer
- `main.py`: `/api/interrupt/resume` now returns 404 when no checkpoint exists for the given `thread_id` (instead of 500).

4) Model switching works end-to-end
- `agent/nodes.py`, `agent/agent_factory.py`, `agent/deepsearch.py`, `main.py`: execution now uses `configurable.model` (from request) instead of hardcoding settings.

## Quick Verification Commands

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/tasks/active
curl -X POST http://localhost:8000/api/chat/cancel/test-thread-123
curl -X POST http://localhost:8000/api/chat/cancel-all
curl -X POST http://localhost:8000/api/interrupt/resume \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"nope\",\"payload\":{}}"
```

