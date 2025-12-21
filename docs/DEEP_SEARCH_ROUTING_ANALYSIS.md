# Deep Search 路由问题分析

## 🔍 问题描述
用户选择了 deep search 模式，但实际执行时没有走 deepsearch 路径。

## 📋 路由流程分析

### 1. 前端 → 后端 (main.py)

**请求格式**:
```json
{
  "messages": [...],
  "search_mode": {
    "useWebSearch": false,
    "useAgent": true,
    "useDeepSearch": true
  }
}
```

或者字符串格式：
```json
{
  "search_mode": "deep"
}
```

### 2. `_normalize_search_mode()` 处理

**main.py:571-613**

```python
def _normalize_search_mode(search_mode):
    # 处理不同输入格式
    if isinstance(search_mode, dict):
        use_web = bool(search_mode.get("useWebSearch"))
        use_agent = bool(search_mode.get("useAgent"))
        use_deep = bool(search_mode.get("useDeepSearch"))
    elif isinstance(search_mode, str):
        lowered = search_mode.lower().strip()
        use_web = lowered in {"web", "search", "tavily"}
        use_agent = lowered in {"agent", "deep", "deep_agent", "deep-agent", "ultra"}
        use_deep = lowered in {"deep", "deep_agent", "deep-agent", "ultra"}

    # ⚠️ 关键逻辑：必须同时 use_agent=True 和 use_deep=True
    if use_deep and not use_agent:
        use_deep = False  # 如果没有 agent，deep 会被重置

    # 确定 mode
    if use_agent:
        mode = "deep" if use_deep else "agent"  # ✅ 这里会设置为 "deep"
    elif use_web:
        mode = "web"
    else:
        mode = "direct"

    return {
        "use_web": use_web,
        "use_agent": use_agent,
        "use_deep": use_deep,
        "mode": mode,  # ✅ mode 字段设置正确
        "use_deep_prompt": use_deep,
    }
```

**返回示例**:
```python
{
    "use_web": False,
    "use_agent": True,
    "use_deep": True,
    "mode": "deep",  # ✅ 正确
    "use_deep_prompt": True
}
```

### 3. Config 传递

**main.py:819-832**

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "model": model,
        "search_mode": mode_info,  # ✅ 包含 mode="deep"
        ...
    },
    "recursion_limit": 50
}
```

### 4. Router Node 处理

**agent/nodes.py:367-409**

```python
def route_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    configurable = _configurable(config)
    mode_info = configurable.get("search_mode", {}) or {}
    override_mode = mode_info.get("mode")  # ✅ 获取 "deep"

    # 调用 smart_route
    result = smart_route(
        query=state.get("input", ""),
        images=state.get("images"),
        config=config,
        override_mode=override_mode,  # ✅ 传递 "deep"
    )

    route = result.get("route", "direct")  # ✅ 应该是 "deep"
    logger.info(f"Routing decision: {route} (confidence: ...)")

    return result  # ✅ 返回 {"route": "deep", ...}
```

### 5. Smart Route 处理

**agent/smart_router.py:261-308**

```python
def smart_route(
    query: str,
    override_mode: Optional[str] = None,
) -> Dict[str, Any]:
    # 检查覆盖模式
    if override_mode:
        logger.info(f"[smart_route] using override mode: {override_mode}")
        return {
            "route": override_mode,  # ✅ 返回 "deep"
            "routing_reasoning": f"Mode override: {override_mode}",
            "routing_confidence": 1.0,
        }

    # ... LLM 路由逻辑（不会执行，因为有 override_mode）
```

### 6. 图的路由决策

**agent/graph.py:60-76**

```python
def route_decision(state: AgentState) -> str:
    route = state.get("route", "direct")  # ✅ 从 state 获取 "deep"
    if route == "deep":
        return "deepsearch"  # ✅ 应该返回 "deepsearch"
    if route == "agent":
        return "agent"
    if route == "web":
        return "web_plan"
    if route == "direct":
        return "direct_answer"
    return "clarify"

workflow.add_conditional_edges(
    "router",
    route_decision,
    ["direct_answer", "agent", "web_plan", "clarify", "deepsearch"]
)
```

### 7. Deepsearch Node

**agent/graph.py:55**

```python
workflow.add_node("deepsearch", deepsearch_node)
```

**agent/graph.py:172**

```python
workflow.add_edge("deepsearch", "human_review")
```

## 🐛 可能的问题点

### 问题1: State 的 route 字段没有被设置

**route_node 返回的结果需要正确合并到 state 中**。

检查 graph.py 中 router 节点的定义：

```python
workflow.add_node("router", route_node)
```

route_node 返回的字典会自动合并到 state，所以 `state["route"]` 应该被设置为 "deep"。

### 问题2: 日志检查

需要在运行时检查以下日志：

1. **_normalize_search_mode 输出**:
   ```
   mode_info = {
       "use_web": False,
       "use_agent": True,
       "use_deep": True,
       "mode": "deep",
       ...
   }
   ```

2. **smart_route 日志**:
   ```
   [smart_route] using override mode: deep
   ```

3. **route_node 日志**:
   ```
   Routing decision: deep (confidence: 1.0)
   ```

4. **route_decision 调用**:
   应该返回 "deepsearch" 字符串

5. **deepsearch_node 执行**:
   ```
   Executing deepsearch node
   [deepsearch] topic='...' epochs=3
   ```

## 🔧 诊断步骤

### 1. 添加详细日志

在 `agent/graph.py` 的 `route_decision` 函数中添加日志：

```python
def route_decision(state: AgentState) -> str:
    route = state.get("route", "direct")
    logger.info(f"[route_decision] state['route'] = {route}")  # ✅ 添加这行

    if route == "deep":
        logger.info("[route_decision] Routing to deepsearch")  # ✅ 添加这行
        return "deepsearch"
    # ...
```

### 2. 检查前端请求

前端必须发送正确的格式：

**选项1: 对象格式**
```json
{
  "search_mode": {
    "useWebSearch": false,
    "useAgent": true,
    "useDeepSearch": true
  }
}
```

**选项2: 字符串格式**
```json
{
  "search_mode": "deep"
}
```

### 3. 测试请求

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "研究AI的发展历史"}],
    "stream": false,
    "search_mode": "deep"
  }'
```

查看日志输出，确认：
- ✅ mode_info["mode"] = "deep"
- ✅ smart_route 返回 "deep"
- ✅ route_decision 收到 "deep"
- ✅ deepsearch_node 被执行

## 🎯 可能的根本原因

### 原因1: route_node 没有正确返回

检查 route_node 是否正确返回了包含 "route" 字段的字典。

### 原因2: State 合并问题

LangGraph 的状态合并可能有问题。确保 AgentState 中 "route" 字段的定义正确。

### 原因3: 条件边配置错误

检查 graph.py 中的条件边配置是否正确。

## ✅ 修复建议

### 建议1: 增强日志

在关键点添加日志：

```python
# agent/nodes.py - route_node
def route_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    # ... 现有代码 ...

    result = smart_route(...)
    route = result.get("route", "direct")

    logger.info(f"[route_node] Routing to: {route}")  # ✅ 添加
    logger.info(f"[route_node] Returning: {result}")  # ✅ 添加

    return result
```

```python
# agent/graph.py - route_decision
def route_decision(state: AgentState) -> str:
    route = state.get("route", "direct")

    logger.info(f"[route_decision] Input state route: {route}")  # ✅ 添加

    if route == "deep":
        logger.info("[route_decision] → deepsearch")  # ✅ 添加
        return "deepsearch"
    # ...
```

### 建议2: 添加断言

```python
def route_decision(state: AgentState) -> str:
    route = state.get("route", "direct")

    # 断言检查
    assert route in ["direct", "agent", "web", "deep", "clarify"], \
        f"Invalid route: {route}"

    if route == "deep":
        return "deepsearch"
    # ...
```

### 建议3: 测试端点

创建专门的测试端点来验证路由：

```python
@app.post("/api/test/route")
async def test_route(request: ChatRequest):
    """测试路由逻辑"""
    mode_info = _normalize_search_mode(request.search_mode)

    return {
        "normalized_mode": mode_info,
        "expected_route": mode_info.get("mode"),
        "test_passed": mode_info.get("mode") == "deep" if request.search_mode == "deep" else True
    }
```

## 📝 总结

理论上，如果前端正确发送 `search_mode: "deep"` 或 `{useAgent: true, useDeepSearch: true}`，应该会：

1. ✅ `_normalize_search_mode` → `{"mode": "deep"}`
2. ✅ `smart_route` → `{"route": "deep"}`
3. ✅ `route_node` → 返回 `{"route": "deep"}` 到 state
4. ✅ `route_decision` → 读取 `state["route"] = "deep"` → 返回 `"deepsearch"`
5. ✅ 图执行 `deepsearch_node`

**如果没有执行，需要添加日志逐步排查哪一步出了问题**。
