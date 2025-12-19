# Error handling & rollback (step16)
- Keep cancellation checks; add circuit breaker for tavily/code execution; include safe fallbacks for writer.
- Add human_review interrupt gating already present; consider timeout guard for deepsearch epochs.
- Provide user-friendly error surfaces in StreamingResponse error events.
