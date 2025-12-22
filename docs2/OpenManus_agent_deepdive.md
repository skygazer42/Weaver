# OpenManus Agent 深度拆解（/data/temp39/OpenManus/app）

## 核心抽象
- BaseAgent：管理状态/记忆/循环（run→think/act），带 stuck 检测与自动提示增强、状态上下文管理、最大步数终止、统一 cleanup。
- ReActAgent：分离 think/act，保持 ReAct 结构。
- ToolCallAgent：面向函数调用的 ReAct 扩展，封装 LLM ask_tool、工具选择模式（auto/required/none），支持多个 tool_calls、ToolFailure 处理、特例工具触发结束、最大观察截断、工具执行后写 memory（含 base64 图片）。
- Manus Agent：通用多工具代理，内置 MCP 客户端聚合、BrowserContextHelper、特种工具名单；启动时自动连接 MCP；支持浏览上下文注入 next_step_prompt；支持动态工具增删与清理。
- 其他 Agent：
  - browser.py：聚焦浏览场景，复用 BrowserUseTool。
  - sandbox_agent.py：结合 Daytona/沙盒工具执行。
  - data_analysis.py：数据分析专用流程。
  - swe.py：面向软件工程任务的组合。

## 工具与执行体系
- ToolCollection：可动态增删工具，工具按 name 查找执行，统一 ToolResult/ToolFailure；便于将远程工具或动态加载的工具拼装给 LLM。
- MCPClients：
  - 支持 SSE 与 stdio 两种连接；每个 server_id 对应 AsyncExitStack。
  - list_tools 后按 server_id+name 生成本地可用工具（前缀 mcp_{server}_{tool}）。
  - disconnect 会移除对应工具并清理会话。
- 浏览器链路：BrowserUseTool + BrowserContextHelper
  - 封装 browser_use 库，自动创建浏览器/上下文，支持代理、头less/安全开关、CDP/WSS、extra args。
  - DomService + context.get_current_page 获取元素索引，支持截图/内容抽取等动作；web_search action 内嵌。
  - BrowserContextHelper 根据最近消息更新 next_step_prompt，避免重复信息。
- 其他工具：AskHuman、StrReplaceEditor、PythonExecute、Bash、File operators、Crawl4AI、Planning、Chart Visualization、Terminate、CreateChatCompletion（直接 call LLM）、WebSearch（多引擎）。

## 配置体系
- config.py 定义 AppConfig：LLMSettings（多模型）、BrowserSettings（代理/安全/实例/CDP/WSS）、SearchSettings（主/备引擎、语言/国家、重试）、SandboxSettings、DaytonaSettings（镜像、entrypoint、区域、VNC 密码）、MCPSettings（多 server 配置，mcp.json 解析）、RunflowSettings。
- TOML/JSON 加载，支持多 LLM 命名配置，工具可按名称选择 LLM。

## 运行/沙盒
- Daytona 集成：配置 + README 指引获取 API key、镜像、entrypoint、VNC 访问，工具能在远程沙盒运行并提供可视化。
- sandbox 客户端：通用执行/端口暴露。

## 设计亮点（可移植到 Weaver）
1) **动态工具聚合**：ToolCollection + MCPClients 让工具集合在运行期可增删并暴露给 LLM。
2) **远程工具获取**：MCP list_tools → 本地代理工具，自动命名去重，disconnect 时清理。
3) **多引擎搜索回退**：主/备搜索、语言/国家、重试节奏。
4) **浏览上下文提示**：根据当前浏览状态调整 next_step_prompt，提升多步操作成功率。
5) **HITL 工具链**：AskHuman + terminate 流程，支持人工介入和安全结束。
6) **沙盒多后端**：Daytona 远程可视化沙盒，含 VNC/HTTP 端口。
7) **规划/可视化/数据分析工具**：丰富的任务侧工具可直接搬运。
8) **stuck 检测**：记忆中重复回答计数，自动调整提示，减少循环。

## LangGraph 化建议
- 将 BaseAgent/ToolCallAgent 的循环映射为 LangGraph 节点：router/think（LLM 选择工具）→ act（工具执行）→ writer/evaluator；stuck 检测放在 middleware/evaluator。
- ToolCollection/MCPClients 注册到 Weaver Tool Registry，并在 graph startup/teardown 中 connect/disconnect。
- BrowserContextHelper 作为前置/后置 hook（或 LangGraph middleware）装饰浏览器节点，写入 state 的 prompt augmentation。
- Daytona client 封装为工具节点（创建/获取/清理 session），事件流输出 VNC/HTTP 链接。
- 搜索回退链放在 web_search node 内部或作为独立 node，输出统一 SearchResult。
