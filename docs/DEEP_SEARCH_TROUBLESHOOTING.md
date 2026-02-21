# Deep Search Troubleshooting

This guide helps diagnose common issues when Deep Research / Deep Search does not behave as expected.

---

## Checklist

### 1) Confirm required keys

- `TAVILY_API_KEY` (search provider)
- LLM provider key (for example `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)

### 2) Confirm mode selection

In the UI, ensure you are in **Deep** mode (or your request explicitly triggers deep research).

### 3) Check logs

Enable debug logging in `.env`:

```bash
DEBUG=true
LOG_LEVEL=DEBUG
ENABLE_FILE_LOGGING=true
```

Then inspect:

```bash
tail -f logs/weaver.log
```

### 4) Run the routing diagnostic

```bash
.venv/bin/python scripts/deep_search_routing_check.py
```

### 5) Validate contract + frontend rendering

If the backend streams events but the UI looks “stuck”, verify SSE protocol handling:

- `docs/chat-streaming.md`

---

## Operational notes

- For rollout guidance and rollback switches, see `docs/deep-research-rollout.md`.
- For benchmark smoke/regression workflows, see `docs/benchmarks/README.md`.
