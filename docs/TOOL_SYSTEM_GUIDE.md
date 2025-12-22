# Weaver 工具系统完整指南

**版本**: v1.0
**日期**: 2024-12-21
**状态**: ✅ Phase 1 完成

---

## 📋 目录

1. [概述](#概述)
2. [核心概念](#核心概念)
3. [快速开始](#快速开始)
4. [详细文档](#详细文档)
5. [最佳实践](#最佳实践)
6. [迁移指南](#迁移指南)
7. [故障排除](#故障排除)

---

## 概述

Weaver 工具系统提供了一个统一的框架来创建和管理 AI Agent 工具。基于 Manus AgentPress 的设计理念，结合 LangChain 生态系统的优势。

### 核心优势

✅ **声明式定义** - 使用 `@tool_schema` 装饰器，schema 与实现紧密耦合
✅ **统一结果格式** - `ToolResult` 提供一致的成功/失败处理
✅ **自动注册** - 工具方法自动扫描和注册
✅ **LangChain 兼容** - 无缝集成现有 LangChain 工作流
✅ **丰富元数据** - 支持调试、日志和性能分析
✅ **易于测试** - 清晰的接口和模拟支持

---

## 核心概念

### 1. ToolResult - 统一结果容器

所有工具返回统一的 `ToolResult` 格式：

```python
@dataclass
class ToolResult:
    success: bool           # 执行状态
    output: str            # 文本输出（给 LLM）
    metadata: Dict         # 结构化元数据
    error: Optional[str]   # 错误信息（如果失败）
```

**示例**:
```python
# 成功结果
ToolResult(
    success=True,
    output='{"results": [...]  , "count": 5}',
    metadata={"execution_time_ms": 250}
)

# 失败结果
ToolResult(
    success=False,
    output="Error: API key not found",
    error="API key not found",
    metadata={"error_type": "ConfigError"}
)
```

### 2. WeaverTool - 工具基类

所有工具继承自 `WeaverTool`：

```python
class MyTool(WeaverTool):
    def __init__(self, api_key: str):
        self.api_key = api_key
        super().__init__()  # 必须调用！

    @tool_schema(
        name="my_function",
        description="Does something useful",
        parameters={
            "type": "object",
            "properties": {
                "arg": {"type": "string", "description": "..."}
            },
            "required": ["arg"]
        }
    )
    def my_function(self, arg: str) -> ToolResult:
        try:
            result = self._do_something(arg)
            return self.success_response(result)
        except Exception as e:
            return self.fail_response(str(e))
```

### 3. tool_schema 装饰器

声明式定义工具 schema：

```python
@tool_schema(
    name="tool_name",              # 工具名称（OpenAI function calling 格式）
    description="...",             # 工具描述（给 LLM 看）
    parameters={                   # JSON Schema 格式参数定义
        "type": "object",
        "properties": {...},
        "required": [...]
    }
)
def method_name(self, ...) -> ToolResult:
    pass
```

---

## 快速开始

### 步骤 1: 创建工具类

```python
# my_custom_tool.py
from tools.core.base import WeaverTool, ToolResult, tool_schema
import logging

logger = logging.getLogger(__name__)


class WeatherTool(WeaverTool):
    """获取天气信息的工具"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        super().__init__()

    @tool_schema(
        name="get_weather",
        description="Get current weather for a city",
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name"
                },
                "units": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "default": "celsius"
                }
            },
            "required": ["city"]
        }
    )
    def get_weather(self, city: str, units: str = "celsius") -> ToolResult:
        """获取城市天气"""
        try:
            # 实际调用天气 API
            weather_data = self._fetch_weather(city, units)

            return self.success_response(
                {
                    "city": city,
                    "temperature": weather_data["temp"],
                    "condition": weather_data["condition"],
                    "units": units
                },
                metadata={
                    "api_version": "v2",
                    "timestamp": weather_data["timestamp"]
                }
            )

        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            return self.fail_response(
                f"Failed to get weather: {str(e)}",
                metadata={"city": city, "error_type": type(e).__name__}
            )

    def _fetch_weather(self, city, units):
        """实际 API 调用（简化示例）"""
        # 实现省略
        pass
```

### 步骤 2: 转换为 LangChain 工具

```python
from tools.core.langchain_adapter import weaver_tool_to_langchain

# 创建工具实例
weather_tool = WeatherTool(api_key="your-api-key")

# 转换为 LangChain 工具
langchain_tools = weaver_tool_to_langchain(weather_tool)

# 现在可以在 LangChain agent 中使用
from langchain.agents import create_agent

agent = create_agent(
    llm=my_llm,
    tools=langchain_tools,
    ...
)
```

### 步骤 3: 直接使用

```python
# 也可以直接调用（不通过 LangChain）
weather_tool = WeatherTool(api_key="your-api-key")
result = weather_tool.get_weather("Beijing", units="celsius")

if result.success:
    print(f"Output: {result.output}")
    print(f"Metadata: {result.metadata}")
else:
    print(f"Error: {result.error}")
```

---

## 详细文档

### 响应助手方法

`WeaverTool` 提供三种响应助手方法：

#### 1. success_response()

```python
def success_response(
    self,
    data: Any,
    metadata: Optional[Dict[str, Any]] = None
) -> ToolResult:
    """创建成功响应"""
```

**用法**:
```python
# 传递字典（自动 JSON 序列化）
return self.success_response(
    {"results": [...], "count": 5},
    metadata={"api_version": "v2"}
)

# 传递字符串
return self.success_response(
    "Operation completed successfully"
)

# 传递列表
return self.success_response(
    [{"id": 1}, {"id": 2}]
)
```

#### 2. fail_response()

```python
def fail_response(
    self,
    error_msg: str,
    metadata: Optional[Dict[str, Any]] = None
) -> ToolResult:
    """创建失败响应"""
```

**用法**:
```python
return self.fail_response(
    "API request failed: timeout",
    metadata={
        "error_type": "TimeoutError",
        "retry_count": 3
    }
)
```

#### 3. partial_response()

```python
def partial_response(
    self,
    data: Any,
    warning: str,
    metadata: Optional[Dict[str, Any]] = None
) -> ToolResult:
    """创建部分成功响应（有警告）"""
```

**用法**:
```python
# 示例：只找到部分结果
return self.partial_response(
    {"results": found_results, "count": len(found_results)},
    f"Only found {len(found_results)} out of {requested_count} results",
    metadata={"requested": requested_count, "found": len(found_results)}
)
```

### 工具发现和管理

#### 列出所有方法

```python
tool = MyTool()
methods = tool.list_methods()
# ['method1', 'method2', ...]
```

#### 获取 Schemas

```python
schemas = tool.get_schemas()
# {
#   'method1': {
#     'name': 'method1',
#     'description': '...',
#     'parameters': {...}
#   },
#   ...
# }
```

#### 获取特定方法

```python
method = tool.get_method("method1")
if method:
    result = method(arg1="value")
```

---

## 最佳实践

### 1. 错误处理

**✅ 推荐**:
```python
@tool_schema(...)
def my_method(self, arg: str) -> ToolResult:
    try:
        # 主逻辑
        result = self._do_something(arg)
        return self.success_response(result)

    except ValueError as e:
        # 特定错误
        return self.fail_response(
            f"Invalid input: {str(e)}",
            metadata={"error_type": "ValueError", "arg": arg}
        )

    except Exception as e:
        # 通用错误
        logger.error(f"Unexpected error: {e}")
        return self.fail_response(
            f"Operation failed: {str(e)}",
            metadata={"error_type": type(e).__name__}
        )
```

**❌ 不推荐**:
```python
def my_method(self, arg: str) -> ToolResult:
    # 不捕获异常 - 可能导致崩溃
    result = self._do_something(arg)
    return self.success_response(result)
```

### 2. 元数据使用

**✅ 推荐**: 添加有用的调试信息
```python
return self.success_response(
    data,
    metadata={
        "api_version": "v2.0",
        "execution_time_ms": 250,
        "cache_hit": False,
        "data_source": "live_api",
        "request_id": uuid.uuid4().hex
    }
)
```

**❌ 不推荐**: 元数据为空或无意义
```python
return self.success_response(data, metadata={})
```

### 3. 参数验证

**✅ 推荐**: 早期验证参数
```python
@tool_schema(...)
def search(self, query: str, max_results: int = 5) -> ToolResult:
    # 验证参数
    if not query or not query.strip():
        return self.fail_response(
            "Query cannot be empty",
            metadata={"error_type": "ValidationError"}
        )

    if max_results < 1 or max_results > 100:
        return self.fail_response(
            "max_results must be between 1 and 100",
            metadata={"error_type": "ValidationError", "value": max_results}
        )

    # 继续执行
    ...
```

### 4. 日志记录

**✅ 推荐**: 关键操作记录日志
```python
import logging
logger = logging.getLogger(__name__)

@tool_schema(...)
def my_method(self, arg: str) -> ToolResult:
    logger.info(f"Starting operation with arg={arg}")

    try:
        result = self._do_something(arg)
        logger.info(f"Operation completed successfully")
        return self.success_response(result)

    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        return self.fail_response(str(e))
```

### 5. 配置管理

**✅ 推荐**: 使用 settings 管理配置
```python
from common.config import settings

class APITool(WeaverTool):
    def __init__(self, api_key: Optional[str] = None):
        # 优先使用传入的 key，否则从 settings 获取
        self.api_key = api_key or settings.my_api_key

        if not self.api_key:
            logger.warning("API key not configured")

        super().__init__()
```

---

## 迁移指南

### 从 LangChain @tool 迁移

**旧代码** (LangChain):
```python
from langchain.tools import tool

@tool
def tavily_search(query: str, max_results: int = 5) -> str:
    """Search the web using Tavily."""
    # 实现
    return json.dumps(results)
```

**新代码** (WeaverTool):
```python
from tools.core.base import WeaverTool, ToolResult, tool_schema

class TavilySearchTool(WeaverTool):
    def __init__(self, api_key: str):
        self.api_key = api_key
        super().__init__()

    @tool_schema(
        name="tavily_search",
        description="Search the web using Tavily.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    )
    def search(self, query: str, max_results: int = 5) -> ToolResult:
        try:
            # 实现
            return self.success_response(results)
        except Exception as e:
            return self.fail_response(str(e))
```

**向后兼容包装器**:
```python
# 保留原函数签名以兼容现有代码
def tavily_search(query: str, max_results: int = 5) -> str:
    """Legacy wrapper for backward compatibility."""
    tool = TavilySearchTool(api_key=settings.tavily_api_key)
    result = tool.search(query, max_results)

    if result.success:
        return result.output
    else:
        logger.error(f"Search failed: {result.error}")
        return json.dumps([])
```

### 示例：已迁移的工具

✅ **TavilySearchTool** - `tools/search_enhanced.py`
- 深度网页搜索
- 内容摘要
- 多查询支持

✅ **CodeExecutorTool** - `tools/code_executor_enhanced.py`
- Python 代码执行（E2B 沙箱）
- 图表生成
- 输出捕获

---

## 故障排除

### 常见问题

#### 1. Schema 未注册

**症状**: `tool.get_schemas()` 返回空字典

**原因**: 忘记调用 `super().__init__()`

**解决方案**:
```python
class MyTool(WeaverTool):
    def __init__(self):
        # ... 初始化逻辑 ...
        super().__init__()  # 必须调用！
```

#### 2. LangChain 转换失败

**症状**: `weaver_tool_to_langchain()` 报错

**原因**: Schema 参数格式不正确

**解决方案**: 确保参数遵循 JSON Schema 规范
```python
parameters={
    "type": "object",  # 必须
    "properties": {...},  # 必须
    "required": [...]  # 可选
}
```

#### 3. 方法未被发现

**症状**: 方法存在但未在 `list_methods()` 中

**原因**:
- 忘记添加 `@tool_schema` 装饰器
- 方法名以 `_` 开头（私有方法）

**解决方案**: 确保使用装饰器
```python
@tool_schema(...)  # 必须有！
def my_method(self) -> ToolResult:
    pass
```

#### 4. 序列化错误

**症状**: `json.dumps()` 失败

**原因**: 数据包含不可序列化对象

**解决方案**: 使用 `success_response()` 自动处理
```python
# 自动序列化
return self.success_response({"date": datetime.now()})

# 或手动转换
return self.success_response({
    "date": datetime.now().isoformat()
})
```

---

## 附录

### A. 完整示例

参见:
- `tools/example_enhanced_tool.py` - 完整示例工具
- `tools/search_enhanced.py` - 真实 Tavily 搜索工具
- `tools/code_executor_enhanced.py` - 代码执行工具

### B. 测试

运行测试:
```bash
# 单元测试
pytest tests/test_tool_base.py -v

# 集成测试
pytest tests/test_langchain_adapter.py -v

# 所有测试
pytest tests/ -v
```

### C. API 参考

详见源码注释：
- `tools/base.py` - 核心类和装饰器
- `tools/langchain_adapter.py` - LangChain 集成

---

## 下一步

- [ ] 阅读 [实施计划](./MANUS_IMPLEMENTATION_PLAN.md) 了解 Phase 2-6
- [ ] 查看 [进度报告](./PROGRESS_REPORT.md) 了解当前状态
- [ ] 尝试创建自己的工具
- [ ] 参与 Phase 2: XML 工具调用支持

---

**文档版本**: v1.0
**最后更新**: 2024-12-21
**维护者**: Weaver Team
