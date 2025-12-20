# API 端点错误报告

测试日期: 2025-12-20

## 测试结果总览

| 端点 | 方法 | 状态 | 问题描述 |
|------|------|------|----------|
| `/` | GET | OK | - |
| `/health` | GET | OK | - |
| `/metrics` | GET | OK | Prometheus 未启用时返回提示 |
| `/api/runs` | GET | OK | - |
| `/api/runs/{id}` | GET | OK | - |
| `/api/memory/status` | GET | OK | - |
| `/api/mcp/config` | GET | OK | - |
| `/api/asr/status` | GET | OK | - |
| `/api/tts/status` | GET | OK | - |
| `/api/tts/voices` | GET | OK | - |
| `/api/chat` | POST | OK | 需指定 model 为 `deepseek-chat` |
| `/api/tasks/active` | GET | **500** | 未定义变量 `stats` |
| `/api/chat/cancel/{id}` | POST | **500** | cancellation_manager 问题 |
| `/api/chat/cancel-all` | POST | **500** | cancellation_manager 问题 |
| `/api/support/chat` | POST | **400** | 模型配置错误 |

---

## 错误详情

### 1. GET /api/tasks/active - 500 Internal Server Error

**文件位置**: `main.py:407-417`

**问题代码**:
```python
@app.get("/api/tasks/active")
async def get_active_tasks():
    """Get all active tasks."""
    active_tasks = cancellation_manager.get_active_tasks()

    return {
        "active_tasks": active_tasks,
        "stats": stats,  # <-- 变量 stats 未定义
        "stream_count": len(active_streams),
        "timestamp": datetime.now().isoformat()
    }
```

**问题分析**:
- `stats` 变量在函数作用域内未定义
- 可能是遗漏的全局变量或应该从其他地方获取

**修复建议**:
```python
@app.get("/api/tasks/active")
async def get_active_tasks():
    active_tasks = cancellation_manager.get_active_tasks()
    return {
        "active_tasks": active_tasks,
        "stream_count": len(active_streams),
        "timestamp": datetime.now().isoformat()
    }
```
或者定义 `stats` 变量收集统计信息。

---

### 2. POST /api/chat/cancel/{thread_id} - 500 Internal Server Error

**文件位置**: `main.py:350-383`

**问题代码**:
```python
@app.post("/api/chat/cancel/{thread_id}")
async def cancel_chat(thread_id: str, request: CancelRequest = None):
    reason = request.reason if request else "User requested cancellation"
    # ...
    cancelled = await cancellation_manager.cancel(thread_id, reason)
```

**问题分析**:
- 需要检查 `cancellation_manager.cancel()` 方法的实现
- 可能存在 `cancellation_manager` 初始化问题或方法签名不匹配

**需要检查**:
- `common/cancellation.py` 中的 `cancel()` 方法实现

---

### 3. POST /api/chat/cancel-all - 500 Internal Server Error

**文件位置**: `main.py:386-405`

**问题分析**:
- 与 `/api/chat/cancel/{id}` 相同，依赖 `cancellation_manager`
- 需要检查 `cancellation_manager.cancel_all()` 方法

---

### 4. POST /api/support/chat - 400 Model Not Exist

**文件位置**: `main.py:535-565`

**错误响应**:
```json
{"detail":"Error code: 400 - {'error': {'message': 'Model Not Exist', 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_request_error'}}"}
```

**问题分析**:
- `support_graph` 使用了默认模型配置 (可能是 `gpt-4o`)
- 当前 API 网关是 DeepSeek (`OPENAI_BASE_URL=https://api.deepseek.com/v1`)
- DeepSeek 不支持 `gpt-4o` 模型名称

**修复建议**:
1. 检查 `support_agent.py` 中的模型配置
2. 将默认模型改为 `deepseek-chat` 或从配置读取
3. 或在 `SupportChatRequest` 中添加 `model` 参数

---

## 配置问题

### 默认模型不匹配

当前环境配置:
- `OPENAI_BASE_URL=https://api.deepseek.com/v1`
- DeepSeek API 需要使用 `deepseek-chat` 或 `deepseek-reasoner` 模型名

代码中多处硬编码使用 `gpt-4o`:
- `ChatRequest.model` 默认值: `gpt-4o` (main.py:269)
- `support_graph` 的模型配置

**建议**:
1. 在 `.env` 中添加 `DEFAULT_MODEL=deepseek-chat`
2. 在 `common/config.py` 中读取此配置
3. 所有端点使用 `settings.default_model` 作为默认值

---

## 待检查文件

1. `common/cancellation.py` - cancellation_manager 实现
2. `support_agent.py` - support_graph 模型配置
3. `agent/graph.py` - 主 agent 模型配置

---

## 测试命令参考

```bash
# 正常工作的端点
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/api/runs
curl http://localhost:8000/api/mcp/config
curl http://localhost:8000/api/tts/voices

# 需要指定模型的聊天
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hello"}],"stream":false,"model":"deepseek-chat"}'

# 有问题的端点
curl http://localhost:8000/api/tasks/active  # 500
curl -X POST http://localhost:8000/api/chat/cancel/test  # 500
curl -X POST http://localhost:8000/api/chat/cancel-all  # 500
curl -X POST http://localhost:8000/api/support/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'  # 400 Model Not Exist
```
