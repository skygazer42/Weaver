# 浏览器工具事件化

- 轻量浏览器工具（`tools/browser/browser_tools.py`）
  - 所有工具经 EventedTool 包装发 `tool_start/result/error`。
  - `browser_screenshot` 额外发 `tool_screenshot`，payload: `{tool, url, image(base64)}`。
  - `tool_progress`：search/navigate/click 会发 progress（action+info），便于前端显示步骤。
- 沙盒浏览器工具（`tools/sandbox/sandbox_browser_tools.py`）原生支持 screenshot 事件和存盘；继续沿用。
- 线程隔离：thread_id 透传到 emitter，前端订阅 `/api/events/{thread_id}`。
- 后续可在 navigate/click 等内部加 `tool_progress`/`tool_screenshot`，按需扩展。

- 沙盒浏览器工具现在在 navigate/click/type/press/scroll/screenshot/reset 阶段发出 `tool_progress`，便于前端显示浏览步骤。
