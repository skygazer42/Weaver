# 搜索回退链（新增）
- 新工具：`tools.search.fallback_search`，按引擎顺序尝试，默认使用 `settings.search_engines`（逗号分隔，默认 `tavily`）。
- 若配置多个引擎（>1），`agent_tools.build_agent_tools` 会自动把 web_search 换为 `fallback_search`；否则继续用原 `tavily_search`。
- 事件：工具经事件包装器后会发出 `tool_start/result/error`，便于前端显示“正在搜索”。
- 配置：`search_engines="tavily,bing,..."`；尚未接入其它引擎处理器，未来可在 `_ENGINE_HANDLERS` 增加。
