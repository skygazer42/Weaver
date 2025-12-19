# Module map (quick index)
- main.py: FastAPI entry; routes /api/chat, /api/research, ASR/TTS, MCP config; wires research_graph/support_graph.
- agent/: graph.py (StateGraph), nodes.py (planner/clarify/perform_parallel_search/writer/evaluator/refine/human_review), state.py (AgentState, message capping), deepsearch.py (iterative deep search), agent_factory.py (middleware agent), middleware.py (retry/limits), message_utils.py.
- tools/: tavily search wrapper, code_executor (E2B), mcp, crawler, memory_client, registry, tts/asr.
- common/: config, cancellation manager, concurrency, logger, metrics (new).
- web/: Next.js frontend.
- prompts/: template sets for deepsearch/optimizer; prompts/__init__.py.
- support_agent.py: simpler Mem0-based support chat graph.
- docs/: checklists and quickstart.
