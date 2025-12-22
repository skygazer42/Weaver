# 冒烟与测试计划（草案）

## 冒烟（无沙盒）
- start server, call `/api/research` with simple query，确保返回且事件流有 tool_start/result（搜索）。
- fallback_search：配置多引擎，验证首个成功引擎返回非空。
- MCP mock：使用假 mcp_servers（比如指向本地 SSE mock）确保注册与事件输出。
- ask_human：触发并观察事件 tool_start/result。
- browser_screenshot：返回 base64，事件 tool_screenshot。
- daytona_create/stop：在未配置与已配置场景下，验证事件与返回 payload。

## 冒烟（沙盒=none）
- 配置 sandbox_mode=none（预留），确认 sandbox_* 工具不注册。

## 沙盒/Daytona（待实现后）
- 创建 sandbox，返回 VNC/HTTP 链接事件；reset/stop 清理。

## 单元/集成（建议）
- Tool event wrapper：断言 start/result/error 事件结构。
- whitelist/blacklist：启用过滤后工具数量/名称符合预期。
- MCP 客户端：mock session 返回工具列表，验证代理命名与事件。
- browser_tools：search/click/back 等事件触发；screenshot 事件存在。
- chart_visualize：返回 base64 PNG，事件 result。
- safe_bash：黑名单命令被拒绝；超时被截断。
- str_replace：文件替换正确，事件 result。
