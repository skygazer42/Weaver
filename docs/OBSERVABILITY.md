# 可观测性（日志 / 指标 / 运行统计）

本文档说明 Weaver 后端的可观测性能力：日志、Prometheus 指标、以及内置的运行统计。

## 1. 日志

实现：`common/logger.py`

相关配置（`.env` / `common/config.py`）：

- `LOG_LEVEL`：`DEBUG/INFO/WARNING/ERROR/CRITICAL`
- `LOG_FILE`：默认 `logs/weaver.log`
- `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT`：轮转策略
- `ENABLE_FILE_LOGGING`：是否写文件
- `ENABLE_JSON_LOGGING`：是否输出 JSON 日志

线程级日志（可选）：

`main.py#stream_agent_events` 会为每个 `thread_id` 追加一个文件 handler：

- `logs/threads/{thread_id}.log`

## 2. Prometheus 指标

开关：`ENABLE_PROMETHEUS=true`

- 启用后：`GET /metrics`
- 未启用：可能返回 404（属于预期）

`main.py` 中会注册一些基础指标（请求计数、并发请求数等）。

## 3. 运行统计（轻量）

实现：`common/metrics.py`

- `GET /api/runs`：列出所有 run 的统计
- `GET /api/runs/{thread_id}`：查看单个 run 的统计

统计字段包含：开始/结束时间、耗时、事件数、节点执行计数、是否取消、错误列表等。

