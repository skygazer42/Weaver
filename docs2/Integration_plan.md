# OpenManus → Weaver 集成任务（新版 20 步）

目标：在保持 LangGraph 流程的前提下，吸收 OpenManus 的 agent/工具/配置优势；非 LangGraph 部分需改写成节点或 middleware。环境已就绪，按先后顺序推进。

1. **依赖锁定与冲突清理**：确认 langgraph/langchain-core 版本与项目一致，移除 0.x 残留，重新锁定 requirements。
2. **配置扩展（TOML/JSON）**：把 OpenManus AppConfig 模型并入 `common/config.py`，支持多 LLM/搜索/浏览器/沙盒/Daytona/MCP/Runflow；保留 .env 兼容。
3. **ToolCollection 聚合器引入**：实现 Weaver 版 ToolCollection，封装注册/查找/动态增删，成为 LangGraph tool registry 的前置层。
4. **MCP 客户端（SSE/stdio）**：移植 `tool/mcp.py` → `tools/core/mcp_clients.py`，提供 connect/list/disconnect，工具名加 server_id 前缀，接入 ToolCollection。
5. **MCP 配置加载**：支持 `config/mcp.json`（OpenManus 结构）自动连接；主进程启动/关闭时完成连接与清理。
6. **搜索回退链**：实现多引擎搜索（主/备、语言/国家、重试），封装为 `tools/search/fallback_search.py`，在 router/web_search/deepsearch 节点切换。
7. **BrowserUseTool 适配**：移植 browser_use 驱动，支持代理/headless/安全/CDP/WSS/extra args；统一事件流与截图接口。
8. **BrowserContextHelper Hook**：将浏览上下文提示逻辑植入 LangGraph（浏览节点前后 middleware），可写入 state.next_step_prompt 或提示变量。
9. **Daytona Sandbox 客户端**：实现 `tools/sandbox/daytona_client.py`（创建/复用/销毁、VNC/HTTP 链接），在工具注册时可选启用。
10. **沙盒选择策略**：新增配置/路由，线程级 session：E2B 本地、Daytona 远程、禁用沙盒三模式切换。
11. **AskHuman 工具/HITL**：移植并接入 LangGraph 人审节点；支持取消、结果写入事件流。
12. **StrReplaceEditor 工具**：移植文本/文件替换，兼容 sandbox/local 文件系统。
13. **Bash/Command 工具**：移植 bash 工具，增加工作目录/超时/危险命令过滤，支持 sandbox 执行。
14. **Crawl4AI 工具**：移植网页抓取工具，供 deepsearch/报告使用。
15. **Chart Visualization 工具**：移植图表生成模块，输出文件路径并在事件流/报告中引用。
16. **Planning 工具/Prompt**：移植规划工具与 `prompt/planning.py`，作为 LangGraph 辅助计划节点或前置 step。
17. **Stuck 检测 middleware**：参考 BaseAgent 重复检测逻辑，放入 LangGraph evaluator/middleware，自动调整提示或触发 AskHuman。
18. **工具选择策略扩展**：支持工具白名单/必选/禁用（对应 ToolChoice AUTO/REQUIRED/NONE），在 ToolCollection + LangGraph config 中暴露。
19. **文档与示例**：在 `docs2/` 添加配置样例（TOML、mcp.json、Daytona）、调用示例（浏览上下文、MCP 连接、AskHuman）、迁移指南。
20. **测试与冒烟**：添加最小集成测试：MCP mock、搜索回退、浏览器上下文 hook、Daytona fake client、ToolCollection 动态增删；CI 增加无沙盒/有沙盒两套冒烟。

优先建议：先完成 2/3/4/5/6/8/10 形成可运行骨架，再并行移植工具（11–15）和体验/质量项（17–20）。

进度快照（当前迭代）：
- 已完成：搜索回退链、工具事件包装、工具白/黑名单、浏览器截图事件、沙盒浏览器 progress 事件、Daytona 配置与工具、HITL/编辑/Bash 工具、crawl4ai/chart_viz 工具、MCP 事件化客户端与代理工具（含 thread_id 注入）、沙盒模式配置。
- 待做（高优先）：BrowserUse/Playwright 细粒度事件、Daytona 生命周期绑定 thread/shutdown、Planning 工具接入、stuck middleware 应用、测试/冒烟。 
