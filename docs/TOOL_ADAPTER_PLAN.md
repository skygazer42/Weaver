# Tool adapter plan
- Define BaseToolConfig dataclass (name, description, schema) to normalize custom tools.
- Provide registry helpers: register_tool(obj: BaseTool), load_from_entrypoints, enable/disable by env.
- For MCP tools: wrap MultiServerMCPClient results into LangChain tool objects and register via tools.registry.
- For local tools (code_executor, tavily_search), expose metadata and throttle settings.
- Future: add OpenTelemetry spans around tool invocations.
