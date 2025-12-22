# OpenManus 项目要点速记（/data/temp39/OpenManus/app）

## 架构/模块
- `agent`：基类 + 多个具体 Agent（manus、browser、swe、sandbox_agent、data_analysis），基于自研循环，不依赖 LangGraph。
- `tool`：ToolCollection 聚合器；本地工具（PythonExecute、BrowserUseTool、AskHuman、StrReplaceEditor、bash、file ops、crawl4ai、planning、chart_visualization 等）+ MCP 客户端工具（SSE/stdio）。
- `mcp`：内置 MCP server scaffold；客户端在 `tool/mcp.py` 通过 `MCPClients` 管理多服务器连接和工具注入。
- `sandbox`：Daytona 远程沙盒支持（config + README），带 VNC 访问与端口暴露；还有通用 sandbox client。
- `prompt`：多套提示词（manus、browser、planning、visualization、swe、toolcall），简洁可扩展。
- `config.py`：完整的配置模型（LLM、搜索、浏览器、沙盒、Daytona、MCP、Runflow），TOML/JSON 读取；支持多 LLM 条目和搜索回退链。
- `schema.py`：消息/记忆/状态等 Pydantic 模型（Memory, Message, AgentState）。
- `llm.py`：统一 LLM 封装（多配置名、max_input_tokens 控制）。
- `flow/`：runflow 集成（可选数据分析流程）。

## 可借鉴优势
1. **ToolCollection 聚合器**：统一管理/动态增删工具，执行返回 ToolResult/ToolFailure。
2. **MCP 客户端**：SSE & stdio 双通道，动态列出/注入远程工具，并可按 server_id 清理。
3. **Daytona 沙盒**：配置完整（镜像、entrypoint、VNC 密码、区域），支持浏览器可视化操作。
4. **浏览器上下文辅助**：BrowserContextHelper 根据近期消息调整 next_step_prompt，提升多步浏览操作体验。
5. **多引擎搜索回退**：主/备搜索引擎列表、语言/国家、重试间隔、最大重试配置。
6. **HITL / 交互工具**：AskHuman 工具用于人类在环；StrReplaceEditor 做快速文本/文件编辑。
7. **规划/可视化/数据分析工具**：planning、chart_visualization、data_analysis agent 等模块可直接复用。
8. **配置清晰**：TOML + JSON（mcp.json）双通道加载，便于环境切换。
9. **Bash & 文件操作**：带安全封装的 bash、file ops 工具，可与沙盒结合。
10. **简洁 Toolcall Prompt**：toolcall 系列 prompt 轻量易替换。

## 与 Weaver 的差距/结合点
- Weaver 依赖 LangGraph 流程；OpenManus 是自研循环 → 需将核心工具/能力迁移并包装成 LangGraph 工具节点。
- Weaver 已有 E2B 沙盒、Playwright 浏览器；可新增 Daytona 作为可选后端，BrowserContextHelper 逻辑可直接挂在节点前后。
- Weaver 工具注册器存在但无聚合/动态远程工具管理 → 引入 ToolCollection + MCPClients。
- 搜索当前仅 Tavily → 补充多引擎回退与语言/国家配置。
- HITL 能力弱 → 移植 AskHuman/terminate 流程并在 LangGraph 人审节点触发。

## 需要重写/适配到 LangGraph 的部分
- Agent 循环（BaseAgent/ToolCallAgent 等）需改写为 LangGraph 节点/中间件。
- ToolCollection/MCPClients 的生命周期与 LangGraph registry 对接（注册/注销）。
- BrowserContextHelper 融入现有 `tools.browser_*` 节点前/后处理，或在 middleware 中插入。
- Daytona sandbox 客户端需改造成 Weaver sandbox 工具实现/会话管理，与事件流对接。
- 配置加载：将 OpenManus `config.py` 的模型合入 `common/config.py` 并兼容 .env/TOML。

## 后续阅读入口
- `agent/manus.py`：MCP + 多工具的主 Agent 逻辑。
- `tool/mcp.py`：MCPClients 连接/工具注入实现。
- `tool/browser_use_tool.py`：浏览器控制细节与上下文辅助调用点。
- `sandbox/` & `daytona/`：远程沙盒封装、VNC 说明。
- `config.py` & `schema.py`：数据/配置模型定义。
