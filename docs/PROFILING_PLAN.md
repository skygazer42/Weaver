# Profiling plan (step18)
- Add simple timing middleware around stream_agent_events; already logs duration and event count.
- Use cProfile on main endpoints via scripts/profile_api.sh (todo); consider async-profiler equivalent.
- Measure tavily/batch sizes vs latency; adjust settings.search_batch_size.
