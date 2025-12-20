# 记忆与持久化

本文档聚焦 Weaver 的“记忆”和“持久化”两条线：

- LangGraph 的 store（长期记忆/检索）
- Mem0（可选的长期记忆服务）与本地 JSON 回退
- LangGraph checkpointer（短期断点/可恢复执行）

## 1. LangGraph store（长期记忆）

初始化位置：`main.py`（启动时调用 `_init_store()`）。

配置项（`.env` / `common/config.py`）：

- `MEMORY_STORE_BACKEND`：`memory` / `postgres` / `redis`
- `MEMORY_STORE_URL`：对应后端的连接串

行为：

- `memory`：`InMemoryStore()`（进程内，重启即丢）
- `postgres`：`PostgresStore.from_conn_string(...)`（持久化，可共享）
- `redis`：`RedisStore.from_conn_string(...)`（持久化，可共享，适合高频 KV）

## 2. Mem0（可选）与本地回退

实现：`tools/memory_client.py`

配置项：

- `ENABLE_MEMORY`：是否启用 Mem0
- `MEM0_API_KEY`：Mem0 Key
- `MEMORY_MAX_ENTRIES`：回退 JSON 的最大条目
- `MEMORY_TOP_K`：召回数量

行为：

- 如果 `ENABLE_MEMORY=true` 且安装了 `mem0`：走 Mem0 的 add/search
- 否则：回退到 `data/memory_store.json`（不做语义检索，只取最近）

## 3. Checkpointer（短期断点/恢复）

初始化：`main.py` 根据 `DATABASE_URL` 决定：

- 有 `DATABASE_URL`：`langgraph-checkpoint-postgres`（可恢复、适合长任务）
- 无 `DATABASE_URL`：`InMemorySaver()`（仅进程内，重启即失效）

影响点：

- `/api/interrupt/resume` 是否能恢复
- 多进程/重启场景下的可恢复性

