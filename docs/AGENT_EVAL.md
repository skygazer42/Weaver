# Agent/SUPPORT evaluation
- agent.graph uses StateGraph with router->clarify/planner/web_plan/deepsearch etc; checkpoints via DB or in-memory.
- support_agent graph (Mem0) is simple; could migrate to LangGraph for consistency and share middleware.
- Gaps: tool approval/human_review already optional; need persisted metrics and interrupts wiring (metrics added in main, not in graph nodes yet).
- Recommendation: extract router/config normalization into separate module; add langgraph-api export endpoint; align support agent to reuse AgentState trimmed subset.
