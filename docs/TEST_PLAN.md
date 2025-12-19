# Integration tests plan (step19)
- Add pytest-asyncio plugin and mark async tests appropriately.
- Scenarios: stream_chat happy path, cancellation flow, deepsearch with mock tavily, MCP tool listing, support_chat memory reuse.
- Add snapshot of SSE events for stream_agent_events using httpx AsyncClient.
