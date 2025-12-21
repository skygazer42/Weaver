# Deep Search 路由问题 - 诊断和修复指南

## 📋 问题描述

选择了 deep search 模式，但实际执行时没有走 deepsearch 路径。

## 🔧 已完成的修复

### 1. 添加详细日志 ✅

已在以下关键位置添加诊断日志：

#### main.py (1126-1133行)
```python
logger.info("Chat request received")
logger.info(f"  Model: {model}")
logger.info(f"  Raw search_mode: {request.search_mode}")  # ✅ 新增
logger.info(f"  Normalized mode_info: {mode_info}")      # ✅ 新增
logger.info(f"  Final mode: {mode_info.get('mode')}")    # ✅ 新增
logger.info(f"  Stream: {request.stream}")
```

#### agent/nodes.py (404-407行)
```python
logger.info(f"[route_node] Routing decision: {route} (confidence: {confidence:.2f})")
logger.info(f"[route_node] search_mode from config: {mode_info}")  # ✅ 新增
logger.info(f"[route_node] override_mode: {override_mode}")         # ✅ 新增
logger.info(f"[route_node] Returning result with route='{route}'")  # ✅ 新增
```

#### agent/graph.py (61-78行)
```python
def route_decision(state: AgentState) -> str:
    route = state.get("route", "direct")
    logger.info(f"[route_decision] state['route'] = '{route}'")  # ✅ 新增

    if route == "deep":
        logger.info("[route_decision] → Routing to 'deepsearch' node")  # ✅ 新增
        return "deepsearch"
    # ... 其他路由
```

### 2. 创建诊断工具 ✅

**测试脚本**: `scripts/test_deep_search_routing.py`
- 测试字符串格式: `search_mode: "deep"`
- 测试对象格式: `search_mode: {useAgent: true, useDeepSearch: true}`
- 提供详细的诊断说明

**分析文档**: `docs/DEEP_SEARCH_ROUTING_ANALYSIS.md`
- 完整的路由流程分析
- 可能的问题点列表
- 修复建议

## 🚀 诊断步骤

### 步骤1: 启动服务器（开启详细日志）

```bash
cd F:\pythonproject\Weaver
python main.py
```

服务器启动后会显示日志级别和配置信息。

### 步骤2: 运行诊断脚本

在**新的终端**中运行：

```bash
cd F:\pythonproject\Weaver
python scripts/test_deep_search_routing.py
```

### 步骤3: 检查服务器日志

在服务器终端中查找以下关键日志：

#### ✅ 正常流程日志（按顺序）

```
1️⃣ 请求接收（main.py）
   Chat request received
     Raw search_mode: deep
     Normalized mode_info: {'use_web': False, 'use_agent': True, 'use_deep': True, 'mode': 'deep', ...}
     Final mode: deep  ✅

2️⃣ Smart Router（smart_router.py）
   [smart_route] using override mode: deep  ✅

3️⃣ Route Node（nodes.py）
   [route_node] Routing decision: deep (confidence: 1.0)
   [route_node] search_mode from config: {...'mode': 'deep'...}
   [route_node] override_mode: deep
   [route_node] Returning result with route='deep'  ✅

4️⃣ Route Decision（graph.py）
   [route_decision] state['route'] = 'deep'
   [route_decision] → Routing to 'deepsearch' node  ✅

5️⃣ Deepsearch 执行（deepsearch.py）
   Executing deepsearch node
   [deepsearch] topic='...' epochs=3
   [deepsearch] 开始优化版深度搜索
   [deepsearch] ===== Epoch 1/3 =====  ✅
```

#### ❌ 如果缺少第4步或第5步

说明路由逻辑有问题，继续下面的排查。

## 🔍 问题排查清单

### 问题1: mode 字段不是 'deep'

**症状**: 日志显示 `Final mode: agent` 或其他值

**原因**: `_normalize_search_mode` 没有正确识别

**检查**:
```python
# main.py:571-613
# search_mode 必须是以下之一：
# 1. 字符串: "deep"
# 2. 对象: {"useAgent": true, "useDeepSearch": true}
```

**修复**: 确保前端发送正确格式

### 问题2: route_decision 没有收到 'deep'

**症状**: 日志显示 `[route_decision] state['route'] = 'agent'` 或其他值

**原因**: route_node 返回的 result 没有正确合并到 state

**检查**:
```python
# agent/nodes.py:412
# route_node 应该返回: {"route": "deep", ...}
```

**调试**:
1. 在 route_node 最后添加断点
2. 检查返回的 result 字典
3. 确认 result["route"] == "deep"

### 问题3: 路由到了其他节点

**症状**: 没有看到 deepsearch_node 执行

**原因**: 图的条件边配置可能有问题

**检查**:
```python
# agent/graph.py:60-76
def route_decision(state: AgentState) -> str:
    route = state.get("route", "direct")
    if route == "deep":
        return "deepsearch"  # 确保这行存在
```

### 问题4: override_mode 是 None

**症状**: 日志显示 `override_mode: None`

**原因**: config 中的 search_mode 没有正确传递

**检查**:
```python
# main.py:823
"search_mode": mode_info,  # 应该包含 "mode": "deep"
```

## 🎯 直接测试方法

### 方法1: 使用 curl

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "研究AI的发展历史"}],
    "stream": false,
    "search_mode": "deep"
  }'
```

### 方法2: 使用 Python 脚本

```python
import requests

response = requests.post(
    "http://localhost:8000/api/chat",
    json={
        "messages": [{"role": "user", "content": "研究AI的发展历史"}],
        "stream": False,
        "search_mode": "deep"
    },
    timeout=120
)

print(response.status_code)
print(response.json())
```

### 方法3: 使用诊断脚本

```bash
python scripts/test_deep_search_routing.py
```

## 📊 预期行为

### 正确的 deep search 执行特征

1. **执行时间**: 通常需要30秒-2分钟（取决于查询复杂度）
2. **多轮搜索**: 会看到 "Epoch 1/3", "Epoch 2/3" 等日志
3. **详细报告**: 返回的内容通常较长，包含多个来源的综合信息
4. **日志量大**: deepsearch 会产生大量日志

### 对比其他模式

| 模式 | 执行时间 | 日志特征 | 返回内容 |
|------|---------|---------|---------|
| **direct** | <5秒 | `direct_answer_node` | 简短回答 |
| **agent** | 5-30秒 | `agent_node`, tool calls | 工具调用结果 |
| **web** | 10-20秒 | `web_plan`, search | 搜索结果摘要 |
| **deep** | 30-120秒 | `deepsearch`, multiple epochs | 深度研究报告 |

## 🆘 如果问题仍然存在

### 1. 收集完整日志

```bash
# 启动服务器并保存日志
python main.py > server.log 2>&1

# 在另一个终端运行测试
python scripts/test_deep_search_routing.py

# 检查日志
grep -E "\[route|deepsearch\]" server.log
```

### 2. 检查 AgentState 定义

```python
# agent/state.py
# 确保 route 字段在 AgentState 中定义
class AgentState(TypedDict):
    route: str  # 这个字段必须存在
    # ...
```

### 3. 验证图配置

```python
# 在 agent/graph.py 中添加调试代码
print("Graph nodes:", workflow._nodes.keys())
print("Graph edges:", workflow._edges)
```

### 4. 简化测试

创建最小测试用例：

```python
from agent import create_research_graph
from agent.state import AgentState

graph = create_research_graph()

initial_state: AgentState = {
    "input": "测试查询",
    "route": "deep",  # 直接设置 route
    # ... 其他必需字段
}

config = {"configurable": {"thread_id": "test"}}

result = graph.invoke(initial_state, config)
print(result)
```

## 📝 常见解决方案

### 方案1: 重启服务器

有时候代码更改需要重启才能生效：

```bash
# 停止服务器 (Ctrl+C)
# 重新启动
python main.py
```

### 方案2: 清除缓存

```bash
# 删除 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete

# 重启服务器
python main.py
```

### 方案3: 检查依赖版本

```bash
pip list | grep -E "langchain|langgraph"

# 确保版本匹配：
# langchain-core>=0.1.0
# langgraph>=0.0.30
```

## ✅ 成功标志

当一切正常工作时，你会看到：

```
Chat request received
  Raw search_mode: deep
  Normalized mode_info: {'mode': 'deep', 'use_deep': True, ...}
  Final mode: deep

[smart_route] using override mode: deep

[route_node] Routing decision: deep (confidence: 1.0)
[route_node] override_mode: deep
[route_node] Returning result with route='deep'

[route_decision] state['route'] = 'deep'
[route_decision] → Routing to 'deepsearch' node

Executing deepsearch node
[deepsearch] topic='...' epochs=3
[deepsearch] 开始优化版深度搜索
[deepsearch] ===== Epoch 1/3 =====
[deepsearch] Epoch 1: 生成 5 个查询
[deepsearch] Epoch 1: 搜索到 25 个结果
...
```

## 📚 相关文档

- **路由分析**: `docs/DEEP_SEARCH_ROUTING_ANALYSIS.md`
- **测试脚本**: `scripts/test_deep_search_routing.py`
- **图配置**: `agent/graph.py`
- **路由节点**: `agent/nodes.py` (route_node)
- **Deep Search**: `agent/deepsearch.py`

---

**更新时间**: 2025-12-21
**版本**: 1.0
**状态**: ✅ 已添加详细日志和诊断工具
