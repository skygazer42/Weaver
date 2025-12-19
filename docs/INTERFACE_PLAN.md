# CLI/HTTP alignment (step20)
- Add CLI entrypoint (scripts/cli_research.py) to call /api/research and stream SSE for debugging (todo).
- Validate input schema in ChatRequest: enforce non-empty messages; clamp images list; default search_mode=direct.
- Add FastAPI dependency for rate limiting when production.
