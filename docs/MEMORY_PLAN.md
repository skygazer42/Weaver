# Memory plan (step12)
- Keep InMemoryStore default; expose env to choose postgres/redis.
- Add graceful fallback logging (already) plus health check endpoint (/api/memory/status) pending.
- Consider caching Mem0 results and write-behind to store.
- Add _store_add/_store_search to tools/memory_client for reuse.
