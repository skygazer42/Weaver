# FuFanManus 后端实现笔记（参考对照）

本文档基于你提供的课程工程路径：

`F:\learning\实战项目三：“Manus”通用智能体项目开发实战\...\02_前后端源码\backend`

目标：提炼其“Manus 风格”后端的关键实现方式，并给出与 Weaver 的对照点，便于你把同类能力迁移/复用到本项目。

## 1. 入口与模块划分

FuFanManus 后端典型分层：

- `api.py`：FastAPI 应用入口（lifespan 初始化 DB/Redis/agent/sandbox/trigger）
- `agent/api.py`：Agent 相关路由（start/stream/stop/threads/agents…）
- `run_agent_background.py`：Dramatiq actor（后台执行 agent 并写入 Redis）
- `agent/run.py`：组装 ThreadManager + 工具，启动 run_agent 生成器
- `agentpress/`：核心“Manus runtime”
  - `thread_manager.py`：线程消息管理 + LLM 调用 + 工具执行调度
  - `response_processor.py`：解析模型输出、触发工具、写回事件/消息
  - `tool_registry.py` / `tool.py`：工具注册与 schema
- `services/`：Postgres / Redis / LLM（LiteLLM、部分 ADK）等基础设施
- `sandbox/`：PPIO/E2B 沙箱封装（desktop/browser/code 等多模板）

## 2. 请求到运行的生命周期（核心）

### 2.1 启动运行：HTTP 入队

入口：`agent/api.py`

- `POST /thread/{thread_id}/agent/start`
  1) 校验 thread 权限（JWT）
  2) 选择 agent（自定义 / 默认 FuFanManus / 普通默认）
  3) 插入一条 `agent_runs` 记录（status=running）
  4) 写入 Redis “活跃运行”键：`active_run:{instance_id}:{agent_run_id}`
  5) `run_agent_background.send(...)` 把任务投递到 Dramatiq worker
  6) 立即返回 `{agent_run_id, status}`

### 2.2 前端拉流：SSE + Redis 增量读取

入口：`agent/api.py`

- `GET /agent-run/{agent_run_id}/stream`
  - 使用 SSE（`text/event-stream`），每条消息：`data: {...}\n\n`
  - 关键 Redis key/channel：
    - List：`agent_run:{agent_run_id}:responses`（顺序存储所有响应）
    - PubSub：`agent_run:{agent_run_id}:new_response`（通知有新响应）
    - 控制：`agent_run:{agent_run_id}:control`（STOP/ERROR/END_STREAM）
  - 流式逻辑要点：
    1) 先 `lrange` 读已有响应（解决“先产出后订阅”的竞态）
    2) 订阅 response/control channel
    3) 收到 new 通知后按 `last_processed_index` 增量 `lrange` 拉取并 `yield`
    4) 遇到 status=completed/failed/stopped 或控制信号后结束 stream

### 2.3 Worker 执行：生成器产出 -> Redis List/PubSub

入口：`run_agent_background.py#run_agent_background`

关键点：

- 分布式锁：`agent_run_lock:{agent_run_id}`（避免多实例重复执行）
- 执行主体：`agent.run.run_agent(...)` 返回 async generator
- 每次拿到 `response`：
  - `rpush(response_list_key, json.dumps(response))`
  - `publish(response_channel, "new")`
- 结束：
  - 更新数据库 `agent_runs.status`
  - publish 全局控制信号（END_STREAM / ERROR / STOP）
  - 设置/刷新 Redis TTL，清理 active_run/run_lock 等 key

### 2.4 停止运行：控制信号广播

入口：`agent/api.py`

- `POST /agent-run/{id}/stop`
  - 更新数据库状态
  - publish STOP 到全局 control channel + 各实例 channel
  - 清理 Redis 响应列表

## 3. 工具与沙箱

### 3.1 工具注册（ToolManager）

入口：`agent/run.py#ToolManager.register_all_tools`

典型工具：
- `TaskListTool`：任务列表/计划管理
- `SandboxWebSearchTool`：沙箱内搜索/爬取
- `ComputerUseTool`：桌面/浏览器操作（依赖 sandbox）
- `SandboxBrowserTool`：浏览器能力封装

### 3.2 沙箱（PPIO/E2B，多模板）

入口：`sandbox/sandbox.py`

特点：
- 支持 `desktop` / `browser` / `code` / `base` 多类型模板
- 依赖环境变量：
  - `E2B_DOMAIN`、`E2B_API_KEY`
  - `SANDBOX_TEMPLATE_*`（不同模板 ID）

## 4. 与 Weaver 的对照（你最关心的迁移点）

Weaver 当前后端（`main.py` + LangGraph）与 FuFanManus 的关键差异：

1) 执行模型  
   - FuFanManus：任务队列 + Worker（Dramatiq）+ Redis 推流，天然多实例  
   - Weaver：请求内直接跑 LangGraph 并流式输出，更轻量但不适合多实例/超长任务

2) 推流协议  
   - FuFanManus：SSE `data: {json}\n\n`  
   - Weaver：Vercel AI SDK Data Stream Protocol（`0:{json}\n`）

3) Agent runtime  
   - FuFanManus：自研 `agentpress/`（ThreadManager/ResponseProcessor/ToolRegistry）  
   - Weaver：LangGraph（显式节点与边，便于可视化与可控迭代）

4) 沙箱能力  
   - FuFanManus：desktop/browser/code（更接近“Manus”操作系统级智能体）  
   - Weaver：当前只封装了 E2B code interpreter（代码执行 + 产图）

如果你要把 FuFanManus 的“队列化 + Redis 推流”迁移到 Weaver，优先改造点通常是：

- 把 `stream_agent_events(...)` 的执行从“请求内”拆到后台 worker（Celery/RQ/Dramatiq 均可）
- 复用 FuFanManus 的 Redis List + PubSub 增量推流模式
- 将 `thread_id`/`run_id` 作为强标识写入持久化存储，避免仅靠内存结构

