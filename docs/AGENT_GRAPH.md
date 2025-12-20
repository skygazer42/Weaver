# LangGraph 工作流说明（agent/）

本文档聚焦 `agent/` 目录：研究图（graph）、状态（state）与节点（nodes）的职责拆分，以及不同模式（direct/web/deep）的路由逻辑。

## 1. 图在哪里定义

- 组装入口：`agent/graph.py#create_research_graph`
- 状态类型：`agent/state.py#AgentState`
- 节点实现：`agent/nodes.py`

项目运行时在 `main.py` 初始化并持有：
- `research_graph = create_research_graph(...)`
- `support_graph = create_support_graph(...)`

## 2. 路由模式（direct / web / agent / deep / clarify）

`router` 节点会根据请求携带的 `search_mode`（见 `main.py#_normalize_search_mode`）设置 `state["route"]`：

- `direct`：直接回答（`direct_answer`）
- `agent`：Agent 工具调用模式（`agent` -> `human_review`）
- `web`：Web 检索链路（`web_plan` -> `perform_parallel_search` -> `writer`）
- `deep`：深度研究链路（`deepsearch` 或 `planner` -> ... -> `evaluator` 迭代）
- `clarify`：需要澄清（`clarify` -> `human_review` 或回到 `planner`）

## 3. AgentState（短期状态）关键字段

定义：`agent/state.py#AgentState`

必须理解的字段（后端会在 `main.py#stream_agent_events` 初始化）：

- `input`：用户输入
- `images`：可选图片（base64）
- `messages`：LLM 上下文消息（带聚合与裁剪，见 `capped_add_messages`）
- `research_plan` / `current_step`：计划与进度
- `scraped_content`：搜索/抓取到的材料（`operator.add` 聚合）
- `final_report` / `draft_report`：产出与草稿（供 evaluator loop）
- `evaluation` / `verdict`：评估反馈与结论（pass/revise）
- `tool_call_count`：工具调用计数（可用于限流/熔断）
- 取消相关：`cancel_token_id` / `is_cancelled`

消息裁剪/摘要策略：
- 开关：`TRIM_MESSAGES`、`SUMMARY_MESSAGES`
- 保留策略：`TRIM_MESSAGES_KEEP_FIRST` / `TRIM_MESSAGES_KEEP_LAST`
- 摘要阈值：`SUMMARY_MESSAGES_TRIGGER`

## 4. 节点职责（按执行顺序理解）

下面是“理解链路”所需的最小集合（完整实现见 `agent/nodes.py`）：

- `router`：决定 route
- `direct_answer`：直接生成回答
- `agent`：工具调用型 Agent（可用 Tavily/MCP/浏览器/爬虫等工具）
- `web_plan` / `planner` / `refine_plan`：生成检索计划、必要时迭代修订
- `perform_parallel_search`：并发执行每条 query（调用 `tools/search.py`，可选 crawler）
- `writer`：汇总材料产出报告，可调用工具（例如 `execute_python_code` 产图）
- `evaluator`：deep 模式下评估草稿，输出 `verdict`
- `human_review`：人审/中断点（可与 `/api/interrupt/resume` 配合）
- `deepsearch`：深度搜索策略（更重的 research loop）

## 5. configurable（运行时配置下发）

Weaver 在 `stream_agent_events` 里通过 `config = {"configurable": {...}}` 下发运行参数，典型包括：

- `thread_id`：用于 checkpoint/日志/取消标识
- `model`：节点中选择的实际模型（优先取请求中的 `model`）
- `search_mode`：direct/web/deep
- `user_id`：用于记忆 namespace
- `tool_approval`：是否开启工具审批

节点内部通过 `RunnableConfig` 读取并据此选择模型/工具或走不同分支。
