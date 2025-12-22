# BrowserUse 集成（新）

- 工具：`browser_use`（基于 Playwright + browser-use），支持跳转、点击、输入、滚动、截图等。
- 启用方式：
  - 环境变量：`enable_browser_use=true`
  - Agent profile：`enabled_tools.browser_use=true`
- 事件：自动通过 `tool_start/tool_error/tool_screenshot` 上报，前端可订阅 `/api/events/{thread_id}`。
- 提示辅助：`browser_context_helper` 会把当前 lightweight/sandbox 浏览器上下文注入到系统提示，提高多步浏览成功率。可通过 `enable_browser_context_helper=true` 或 agent_profile 配置开启。

注意：首次使用需安装 Playwright 浏览器（`python -m playwright install chromium`）；`browser-use` 依赖较大，建议在需要时再启用。*** End Patch】----
