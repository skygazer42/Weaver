# Config review notes
- .env.example present; .env loaded via pydantic-settings (common/config.py). Keys: OpenAI, Tavily, E2B, Anthropic, DashScope, mem0, MCP, DB URL.
- CORS origins from env; recommend adding ENV profile switch (DEV/PROD) and ensure no secrets in repo.
- Logging writes to logs/weaver.log; ensure path exists in prod (Dockerfile mounts volume?).
- Suggest adding per-environment config files or env prefix WEAVER_* to avoid collisions.
- Add check: if enable_file_logging, ensure writable dir; otherwise default to console.
