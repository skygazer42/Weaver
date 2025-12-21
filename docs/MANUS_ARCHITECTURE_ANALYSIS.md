# Manus 核心架构深度分析 - 完整报告

**版本**: v2.0
**日期**: 2024-12-21
**分析范围**: Manus AgentPress 核心框架（~10,000+ 行代码）

---

## 📋 目录

1. [核心架构概览](#1-核心架构概览)
2. [核心组件深度解析](#2-核心组件深度解析)
3. [与 Weaver 的对比分析](#3-与-weaver-的对比分析)
4. [可借鉴的设计要点](#4-可借鉴的设计要点)
5. [具体实施建议](#5-具体实施建议)
6. [代码示例](#6-代码示例)
7. [实施路线图](#7-实施路线图)

---

## 1. 核心架构概览

### 1.1 Manus AgentPress 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      ThreadManager (线程管理器)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ ToolRegistry │  │ResponseProc  │  │Context       │      │
│  │ (工具注册表) │  │(响应处理器)   │  │Manager       │      │
│  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘      │
│          │                  │                  │              │
│          ↓                  ↓                  ↓              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │        LLM API 调用 & 流式响应处理                  │    │
│  └─────────────────────────────────────────────────────┘    │
│          ↓                                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  XML Parser → Tool Execution → Result Injection    │    │
│  └─────────────────────────────────────────────────────┘    │
│          ↓                                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │     Auto-Continue (自动续写) → 多轮工具调用        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计理念

| 设计理念 | 说明 | 优势 |
|----------|------|------|
| **工具驱动** | 以工具为核心构建对话流程 | 解耦工具定义与执行逻辑 |
| **装饰器注册** | 使用装饰器声明工具 schema | 元数据与实现紧密耦合 |
| **双模式调用** | 支持 XML 和 Native 两种格式 | 兼容更多 LLM 模型 |
| **流式处理** | 实时解析和执行工具调用 | 更好的用户体验 |
| **自动续写** | finish_reason=tool_calls 自动继续 | 无需手动循环管理 |
| **配置驱动** | 所有行为可通过配置控制 | 灵活切换策略 |

---

## 2. 核心组件深度解析

### 2.1 Tool 工具基类 ⭐⭐⭐

**文件**: `agentpress/tool.py`

#### 关键设计：装饰器 + 抽象基类

```python
class Tool(ABC):
    """
    核心思想：
    1. 装饰器声明 schema
    2. 自动扫描和注册
    3. 统一结果容器 ToolResult
    """

    def __init__(self):
        self._schemas: Dict[str, List[ToolSchema]] = {}
        self._register_schemas()  # 自动注册所有带装饰器的方法
```

#### 装饰器示例

```python
@openapi_schema({
    "name": "search_web",
    "description": "Search the web for current information",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 5
            }
        },
        "required": ["query"]
    }
})
def search_web(self, query: str, max_results: int = 5) -> ToolResult:
    """实际执行搜索"""
    try:
        results = self._perform_search(query, max_results)
        return self.success_response({
            "results": results,
            "query": query
        })
    except Exception as e:
        return self.fail_response(f"Search failed: {str(e)}")
```

#### 统一结果容器

```python
@dataclass
class ToolResult:
    """统一的工具结果格式"""
    success: bool
    output: str  # 文本输出（给 LLM 看）
    metadata: Dict[str, Any] = None  # 额外元数据
```

**优势**:
- ✅ **声明式定义**: Schema 与实现在一起，易于维护
- ✅ **统一错误处理**: success_response / fail_response
- ✅ **自动注册**: 无需手动管理工具列表

---

### 2.2 ToolRegistry 工具注册表 ⭐⭐⭐

**文件**: `agentpress/tool_registry.py`

#### 核心机制：动态方法扫描

```python
class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register_tool(
        self,
        tool_class: Type[Tool],
        function_names: Optional[List[str]] = None,  # 选择性启用
        **kwargs  # 传递给工具构造函数
    ):
        """
        关键设计：
        1. 实例化工具类
        2. 遍历所有方法
        3. 过滤掉私有方法
        4. 支持选择性注册
        """
        tool_instance = tool_class(**kwargs)

        for method_name in dir(tool_instance):
            # 跳过私有和内部方法
            if method_name.startswith('_'):
                continue
            if method_name in ['get_schemas', 'success_response']:
                continue

            method = getattr(tool_instance, method_name)
            if not callable(method):
                continue

            # 选择性注册
            if function_names is None or method_name in function_names:
                self.tools[method_name] = {
                    "instance": tool_instance,
                    "method": method,
                    "tool_class": tool_class.__name__
                }
```

#### 使用示例

```python
# 注册整个工具类
registry.register_tool(BrowserTool)

# 只注册部分方法
registry.register_tool(
    BrowserTool,
    function_names=["navigate", "click", "screenshot"]
)

# 传递初始化参数
registry.register_tool(
    E2BSandboxTool,
    project_id="proj_123",
    sandbox_id="sandbox_456"
)
```

**优势**:
- ✅ **零配置发现**: 自动扫描方法
- ✅ **精细控制**: 可选择性启用方法
- ✅ **参数传递**: 支持工具初始化配置

---

### 2.3 XMLToolParser XML 工具解析器 ⭐⭐⭐⭐

**文件**: `agentpress/xml_tool_parser.py`

#### Claude 风格的 XML 格式

```xml
<function_calls>
<invoke name="search_web">
<parameter name="query">Python async programming</parameter>
<parameter name="max_results">10</parameter>
</invoke>
<invoke name="execute_code">
<parameter name="language">python</parameter>
<parameter name="code">
import asyncio
print("Hello async")
</parameter>
</invoke>
</function_calls>
```

#### 三层解析逻辑

```python
class XMLToolParser:
    # 第一层：提取 <function_calls> 块
    FUNCTION_CALLS_PATTERN = re.compile(
        r'<function_calls>(.*?)</function_calls>',
        re.DOTALL | re.IGNORECASE
    )

    # 第二层：提取 <invoke> 块
    INVOKE_PATTERN = re.compile(
        r'<invoke\s+name=["\']([^"\']+)["\']>(.*?)</invoke>',
        re.DOTALL | re.IGNORECASE
    )

    # 第三层：提取 <parameter> 块
    PARAMETER_PATTERN = re.compile(
        r'<parameter\s+name=["\']([^"\']+)["\']>(.*?)</parameter>',
        re.DOTALL | re.IGNORECASE
    )

    def parse_content(self, content: str) -> List[XMLToolCall]:
        """三层递归解析"""
        tool_calls = []

        # Layer 1: function_calls
        for fc_content in self.FUNCTION_CALLS_PATTERN.findall(content):
            # Layer 2: invoke
            for function_name, invoke_content in self.INVOKE_PATTERN.findall(fc_content):
                parameters = {}

                # Layer 3: parameter
                for param_name, param_value in self.PARAMETER_PATTERN.findall(invoke_content):
                    parameters[param_name] = self._parse_parameter_value(param_value.strip())

                tool_calls.append(XMLToolCall(
                    function_name=function_name,
                    parameters=parameters,
                    raw_xml=invoke_content
                ))

        return tool_calls
```

#### 智能类型推断

```python
def _parse_parameter_value(self, value: str) -> Any:
    """
    自动识别参数类型：
    - JSON 对象/数组
    - 布尔值 (true/false)
    - 数字 (整数/浮点)
    - 字符串 (fallback)
    """
    value = value.strip()

    # 1. JSON
    if value.startswith(('{', '[')):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # 2. Boolean
    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'

    # 3. Number
    try:
        return float(value) if '.' in value else int(value)
    except ValueError:
        pass

    # 4. String (default)
    return value
```

**优势**:
- ✅ **容错性强**: 使用正则而非严格 XML 解析器
- ✅ **类型智能**: 自动识别 JSON/布尔/数字/字符串
- ✅ **调试友好**: 保留原始 XML 和解析详情

**为什么 XML 格式对 Claude 更友好**:
1. Claude 在预训练时更多接触 XML 格式
2. XML 的层次结构更清晰
3. 参数名明确，不易混淆
4. 支持多行文本（代码块）更自然

---

### 2.4 ResponseProcessor 响应处理器 ⭐⭐⭐⭐⭐

**文件**: `agentpress/response_processor.py` (2327 行)

#### 配置驱动的处理策略

```python
@dataclass
class ProcessorConfig:
    """所有行为通过配置控制"""

    # 工具调用模式
    xml_tool_calling: bool = True          # 启用 XML 工具调用
    native_tool_calling: bool = True       # 启用原生工具调用 (OpenAI 格式)

    # 执行策略
    execute_tools: bool = True             # 是否自动执行工具
    execute_on_stream: bool = False        # 流式执行 vs 等待完整响应
    tool_execution_strategy: Literal[
        "sequential",  # 串行执行
        "parallel"     # 并行执行
    ] = "sequential"

    # 结果注入策略
    xml_adding_strategy: Literal[
        "user_message",       # 工具结果作为用户消息
        "assistant_message",  # 工具结果作为助手消息
        "inline_edit"         # 直接编辑助手消息
    ] = "assistant_message"

    # 限制
    max_xml_tool_calls: int = 0  # 单轮最大工具调用次数（0=无限制）
```

#### 流式处理核心流程

```python
async def process_streaming_response(
    self,
    llm_response: AsyncGenerator,
    thread_id: str,
    config: ProcessorConfig,
    auto_continue_count: int = 0
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    核心流程：
    1. 逐块接收 LLM 响应
    2. 实时累积文本内容
    3. 检测 XML 工具调用
    4. 解析并执行工具
    5. 将结果注入对话流
    """

    accumulated_content = ""
    xml_buffer = ""
    tool_calls_buffer = []

    async for chunk in llm_response:
        # 1. 提取文本内容
        if content := self._extract_content(chunk):
            accumulated_content += content
            xml_buffer += content

            # 2. 实时 yield 给前端
            yield {
                "type": "assistant_delta",
                "content": content,
                "metadata": {"stream_status": "delta"}
            }

        # 3. 检测 XML 工具调用
        if config.xml_tool_calling and "<function_calls>" in xml_buffer:
            tool_calls = self.xml_parser.parse_content(xml_buffer)

            if config.execute_tools:
                # 4. 执行工具
                if config.tool_execution_strategy == "parallel":
                    # 并行执行
                    results = await asyncio.gather(*[
                        self._execute_tool(tc) for tc in tool_calls
                    ])
                else:
                    # 串行执行
                    results = []
                    for tc in tool_calls:
                        result = await self._execute_tool(tc)
                        results.append(result)

                # 5. 注入工具结果
                for tool_call, result in zip(tool_calls, results):
                    yield {
                        "type": "tool_result",
                        "tool_name": tool_call.function_name,
                        "result": result.output,
                        "success": result.success,
                        "metadata": {...}
                    }

        # 6. 检测原生工具调用 (tool_calls)
        if config.native_tool_calling:
            if native_calls := self._extract_native_tool_calls(chunk):
                # 类似流程...
                pass
```

#### 自动续写机制（Auto-Continue）

```python
async def run_thread_with_auto_continue(
    self,
    thread_id: str,
    system_prompt: Dict,
    native_max_auto_continues: int = 25,
    **kwargs
) -> AsyncGenerator:
    """
    核心思想：当 finish_reason=tool_calls 时自动续写

    流程：
    1. 调用 LLM
    2. 检查 finish_reason
    3. 如果是 tool_calls：
       a. 执行所有工具
       b. 将工具结果加入对话历史
       c. 自动调用 LLM 继续生成（auto_continue_count++）
    4. 如果是 stop：正常结束
    5. 重复直到 stop 或达到最大次数
    """
    auto_continue_count = 0
    continuous_state = {'accumulated_content': ''}

    while auto_continue_count < native_max_auto_continues:
        # 调用 LLM
        async for chunk in self.process_streaming_response(
            llm_response,
            thread_id,
            config,
            auto_continue_count=auto_continue_count,
            continuous_state=continuous_state
        ):
            yield chunk

        # 检查 finish_reason
        if finish_reason == "tool_calls":
            logger.info(f"Auto-continue #{auto_continue_count + 1}")
            auto_continue_count += 1
            # 继续下一轮（工具结果已注入对话历史）
        elif finish_reason == "stop":
            logger.info("Normal completion")
            break
        else:
            logger.warning(f"Unexpected finish_reason: {finish_reason}")
            break
```

**设计精髓**:
- ✅ **配置驱动**: 所有策略可切换，无需改代码
- ✅ **流式 + 批量**: 支持两种执行模式
- ✅ **智能状态管理**: continuous_state 跨轮保持上下文
- ✅ **并行执行**: 支持多个工具同时执行

---

### 2.5 ThreadManager 线程管理器 ⭐⭐⭐

**文件**: `agentpress/thread_manager.py` (1000+ 行)

#### 核心职责矩阵

| 功能 | 说明 | 对应方法 |
|------|------|---------|
| **线程管理** | 创建对话线程 | `create_thread()` |
| **消息持久化** | 保存消息到数据库 | `add_message()` |
| **历史获取** | 从 events 表获取对话历史 | `get_llm_messages()` |
| **工具注册** | 动态注册工具 | `add_tool()` |
| **LLM 编排** | 执行 LLM 调用和工具编排 | `run_thread()` |
| **上下文管理** | Token 计数和压缩 | 集成 ContextManager |

#### 消息持久化设计

```python
async def add_message(
    self,
    thread_id: str,
    type: str,  # "assistant" | "user" | "tool" | "status"
    content: Union[Dict, List, str],
    is_llm_message: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    统一消息格式存储到 PostgreSQL

    表结构：messages
    - message_id (PK)
    - thread_id (FK)
    - type (VARCHAR)
    - content (JSONB)  ← 灵活存储各种格式
    - is_llm_message (BOOLEAN)
    - metadata (JSONB)
    - created_at (TIMESTAMP)
    """
    result = await self.db.client.table('messages').insert({
        'thread_id': thread_id,
        'type': type,
        'content': content,  # JSONB 自动序列化
        'is_llm_message': is_llm_message,
        'metadata': metadata or {},
        **kwargs
    }).execute()

    return result.data[0]
```

#### LLM 调用编排

```python
async def run_thread(
    self,
    thread_id: str,
    system_prompt: Dict[str, Any],
    stream: bool = True,
    llm_model: str = "deepseek-chat",
    processor_config: Optional[ProcessorConfig] = None,
    tool_choice: Literal["auto", "required", "none"] = "auto",
    enable_context_manager: bool = True,
    **kwargs
) -> AsyncGenerator:
    """
    完整编排流程：

    1. 获取对话历史
    2. Token 计数和上下文管理
    3. 准备 LLM 消息
    4. 调用 LLM API
    5. 流式处理响应
    6. 工具执行和结果注入
    7. 自动续写（如需要）
    """

    # Step 1: 获取历史消息
    messages = await self.get_llm_messages(thread_id)

    # Step 2: Token 管理
    if enable_context_manager:
        token_count = self.context_manager.count_tokens(messages)

        if token_count > self.context_manager.threshold:
            logger.info(f"Triggering context compression ({token_count} tokens)")
            messages = await self.context_manager.summarize_messages(
                messages,
                model=llm_model
            )

    # Step 3: 准备消息
    prepared_messages = [system_prompt] + messages

    # Step 4: 调用 LLM
    llm_response = await self.llm_client.chat_completion(
        model=llm_model,
        messages=prepared_messages,
        stream=stream,
        tools=self.tool_registry.get_openapi_schemas(),
        tool_choice=tool_choice
    )

    # Step 5-7: 流式处理（ResponseProcessor）
    async for chunk in self.response_processor.process_streaming_response(
        llm_response,
        thread_id,
        prepared_messages,
        llm_model,
        processor_config or ProcessorConfig()
    ):
        yield chunk
```

**架构优势**:
- ✅ **关注点分离**: 数据持久化、工具管理、响应处理各司其职
- ✅ **依赖注入**: ResponseProcessor 通过回调访问 add_message
- ✅ **可观测性**: 集成 Langfuse trace
- ✅ **灵活配置**: 支持流式/非流式、多种工具选择策略

---

## 3. 与 Weaver 的对比分析

### 3.1 架构模式对比

| 维度 | **Manus AgentPress** | **Weaver** |
|------|---------------------|------------|
| **核心框架** | 自研工具驱动框架 | LangChain + LangGraph |
| **工作流编排** | 循环驱动 + 自动续写 | 图驱动 + 条件路由 |
| **工具系统** | 装饰器 + 动态注册 | BaseTool 继承 + registry |
| **状态管理** | ThreadManager + DB | StateGraph + Checkpointer |
| **工具调用** | XML + Native 双模式 | 仅 Native (OpenAI 格式) |
| **流式处理** | ResponseProcessor | LangGraph streaming |
| **中间件** | 响应处理器内嵌 | LangChain Middleware 栈 |

### 3.2 Weaver 当前实现

#### 工具定义方式

```python
# Weaver: tools/tavily_search.py
from langchain_core.tools import tool

@tool
def tavily_search(query: str, max_results: int = 5) -> str:
    """Search the web using Tavily."""
    # 实现
    return json.dumps(results)
```

#### Agent 构建方式

```python
# Weaver: agent/agent_factory.py
def build_tool_agent(model: str, tools: List, temperature: float = 0.7):
    """
    构建方式：
    1. LangChain 中间件栈
       - LLMToolSelectorMiddleware
       - ToolRetryMiddleware
       - ToolCallLimitMiddleware
       - HumanInTheLoopMiddleware

    2. 创建 Agent
       agent = create_agent(llm, tools, middleware=middlewares)
    """
    middlewares = [
        LLMToolSelectorMiddleware(),
        ToolRetryMiddleware(max_retries=3),
        ToolCallLimitMiddleware(max_calls=10),
        HumanInTheLoopMiddleware() if settings.tool_approval else None
    ]

    agent = create_agent(
        _build_llm(model, temperature),
        tools,
        middleware=[m for m in middlewares if m]
    )

    return agent
```

#### LangGraph 工作流

```python
# Weaver: agent/graph.py
def create_research_graph():
    """
    图驱动工作流：

    START
      ↓
    [router] 智能路由
      ├─ direct → [direct_answer] → [human_review] → END
      ├─ agent → [agent] → [human_review] → END
      ├─ web → [web_plan] → [parallel_search] → [writer] → END
      └─ deep → [planner] → [parallel_search] → [writer] → [evaluator] → ...
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("router", route_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("perform_parallel_search", perform_parallel_search)
    workflow.add_node("writer", writer_node)
    workflow.add_node("evaluator", evaluator_node)

    # 条件路由
    workflow.add_conditional_edges("router", route_decision, [...])
    workflow.add_conditional_edges("evaluator", after_evaluator, [...])

    return workflow.compile(checkpointer=PostgresSaver(conn))
```

### 3.3 核心差异总结

| 特性 | Manus 优势 | Weaver 优势 |
|------|-----------|-------------|
| **工具系统** | • 装饰器声明，元数据紧密耦合<br>• 统一 ToolResult 容器<br>• 动态注册和选择性启用 | • LangChain 生态兼容<br>• 强大的中间件栈<br>• MCP 工具支持 |
| **工具调用** | • XML + Native 双模式<br>• Claude 友好<br>• 流式检测和执行 | • OpenAI 标准格式<br>• 与 LangChain 深度集成 |
| **工作流** | • 自动续写机制<br>• 简单的循环逻辑 | • LangGraph 可视化<br>• 复杂路由和条件跳转<br>• 并行执行原生支持 |
| **流式处理** | • ResponseProcessor 统一处理<br>• 配置驱动的策略 | • LangGraph streaming<br>• 事件驱动系统 |
| **状态管理** | • ThreadManager + DB<br>• 消息持久化 | • StateGraph + Checkpointer<br>• 状态快照和恢复 |

---

## 4. 可借鉴的设计要点

### 4.1 工具系统增强 ⭐⭐⭐⭐⭐

#### 建议实现：统一工具基类

```python
# 新增 tools/base.py
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import json
import inspect

@dataclass
class ToolResult:
    """统一的工具结果容器"""
    success: bool
    output: str
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "metadata": self.metadata or {}
        }

class WeaverTool(ABC):
    """Weaver 工具基类"""

    def __init__(self):
        self._schemas: Dict[str, Any] = {}
        self._register_schemas()

    def _register_schemas(self):
        """自动注册装饰器标记的方法"""
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if hasattr(method, 'tool_schema'):
                self._schemas[name] = method.tool_schema

    def success_response(self, data: Any) -> ToolResult:
        return ToolResult(success=True, output=json.dumps(data, ensure_ascii=False))

    def fail_response(self, msg: str) -> ToolResult:
        return ToolResult(success=False, output=msg)

# 装饰器
def tool_schema(**schema):
    def decorator(func):
        func.tool_schema = schema
        return func
    return decorator
```

#### 使用示例

```python
# tools/search_tool.py
from tools.base import WeaverTool, tool_schema, ToolResult

class SearchTool(WeaverTool):
    def __init__(self, api_key: str):
        self.api_key = api_key
        super().__init__()

    @tool_schema(
        name="search_web",
        description="Search the web for current information",
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
            results = self._perform_search(query, max_results)
            return self.success_response({"results": results})
        except Exception as e:
            return self.fail_response(f"Search failed: {e}")
```

**优势**:
- ✅ 统一错误处理
- ✅ 元数据与实现紧密耦合
- ✅ 便于测试和 mock

---

### 4.2 XML 工具调用支持 ⭐⭐⭐⭐

#### 为什么需要 XML 格式？

1. **Claude 模型友好**: Claude 在预训练时接触更多 XML 格式
2. **多行文本友好**: 代码块、长文本更自然
3. **参数清晰**: 嵌套结构更易理解
4. **调试友好**: 可读性强

#### 建议实现

```python
# 新增 agent/xml_tool_support.py
from agent.xml_parser import XMLToolParser
from typing import AsyncGenerator, Dict, Any

class EnhancedResponseProcessor:
    def __init__(self):
        self.xml_parser = XMLToolParser()

    async def process_stream_with_xml(
        self,
        response_stream: AsyncGenerator,
        enable_xml: bool = True,
        enable_native: bool = True
    ) -> AsyncGenerator:
        """
        增强的流式处理，支持 XML 和 Native 工具调用
        """
        accumulated = ""

        async for chunk in response_stream:
            text = chunk.content
            accumulated += text

            # 1. 检测 XML 工具调用
            if enable_xml and "<function_calls>" in accumulated:
                xml_calls = self.xml_parser.parse_content(accumulated)

                for call in xml_calls:
                    yield {
                        "type": "tool_call_detected",
                        "format": "xml",
                        "tool_name": call.function_name,
                        "parameters": call.parameters
                    }

                    # 执行工具
                    result = await self.execute_tool(call)

                    yield {
                        "type": "tool_result",
                        "tool_name": call.function_name,
                        "result": result.output,
                        "success": result.success
                    }

            # 2. 检测 Native 工具调用（OpenAI 格式）
            if enable_native and hasattr(chunk, "tool_calls"):
                for tc in chunk.tool_calls:
                    yield {
                        "type": "tool_call_detected",
                        "format": "native",
                        "tool_name": tc.name,
                        "parameters": tc.arguments
                    }

            # 3. 正常文本
            yield {
                "type": "text_delta",
                "content": text
            }
```

---

### 4.3 自动续写机制 ⭐⭐⭐⭐

#### 场景示例

```
User: "分析这个 CSV 文件并生成图表"

Round 1:
  LLM: <function_calls><invoke name="read_file">...</invoke></function_calls>
  Result: [文件内容]
  finish_reason: tool_calls
  → 自动续写

Round 2:
  LLM: <function_calls><invoke name="execute_python_code">...</invoke></function_calls>
  Result: [分析结果 + 图表]
  finish_reason: tool_calls
  → 自动续写

Round 3:
  LLM: "根据分析结果，我发现..."
  finish_reason: stop
  → 正常结束
```

#### 建议实现

```python
# 增强 agent/nodes.py
async def agent_node_with_auto_continue(
    state: AgentState,
    config: RunnableConfig,
    max_continues: int = 25
) -> Dict[str, Any]:
    """
    支持自动续写的 agent 节点
    """
    continue_count = 0
    accumulated_output = ""

    while continue_count < max_continues:
        # 调用 LLM
        response = await agent.invoke({
            "messages": state["messages"]
        }, config)

        accumulated_output += response["output"]

        # 检查 finish_reason
        finish_reason = response.get("metadata", {}).get("finish_reason")

        if finish_reason == "tool_calls":
            logger.info(f"Auto-continue #{continue_count + 1}")

            # 执行工具
            tool_results = await execute_tools(response["tool_calls"])

            # 将工具结果加入对话
            state["messages"].append(ToolMessage(
                content=json.dumps(tool_results),
                tool_call_id=response["tool_calls"][0]["id"]
            ))

            continue_count += 1
            continue  # 继续下一轮

        elif finish_reason == "stop":
            logger.info("Normal completion")
            break

        else:
            logger.warning(f"Unknown finish_reason: {finish_reason}")
            break

    return {
        "final_report": accumulated_output,
        "draft_report": accumulated_output,
        "is_complete": True,
        "messages": [AIMessage(content=accumulated_output)]
    }
```

---

### 4.4 配置驱动的处理策略 ⭐⭐⭐

#### 建议实现

```python
# 新增 agent/processor_config.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class AgentProcessorConfig:
    """Agent 处理配置"""

    # 工具调用模式
    xml_tool_calling: bool = True
    native_tool_calling: bool = True

    # 执行策略
    execute_tools: bool = True
    tool_execution_strategy: Literal["sequential", "parallel"] = "sequential"
    max_tool_calls_per_turn: int = 10

    # 自动续写
    enable_auto_continue: bool = True
    max_auto_continues: int = 25

    # 流式处理
    stream_tool_results: bool = True
    stream_thinking: bool = True

    # 上下文管理
    enable_context_compression: bool = True
    max_context_tokens: int = 128000

    # 错误处理
    retry_on_tool_error: bool = True
    max_retries: int = 3

# 在 common/config.py 中添加
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Agent 处理配置
    agent_xml_tool_calling: bool = True
    agent_auto_continue: bool = True
    agent_max_auto_continues: int = 25
    agent_tool_execution_strategy: str = "sequential"
```

---

### 4.5 增强的工具注册表 ⭐⭐⭐⭐

```python
# 增强 tools/registry.py
from typing import Type, List, Optional, Dict, Any, Callable
from tools.base import WeaverTool

class EnhancedToolRegistry:
    """增强的工具注册表"""

    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register_tool_class(
        self,
        tool_class: Type[WeaverTool],
        function_names: Optional[List[str]] = None,
        **init_kwargs
    ):
        """
        注册工具类

        示例:
        registry.register_tool_class(
            BrowserTool,
            function_names=["navigate", "click"],  # 只启用这两个方法
            headless=True  # 传递给工具构造函数
        )
        """
        tool_instance = tool_class(**init_kwargs)

        for method_name in dir(tool_instance):
            if method_name.startswith('_'):
                continue

            method = getattr(tool_instance, method_name)
            if not callable(method):
                continue

            # 选择性注册
            if function_names is None or method_name in function_names:
                self.tools[method_name] = {
                    "instance": tool_instance,
                    "method": method,
                    "tool_class": tool_class.__name__,
                    "schema": getattr(method, 'tool_schema', None)
                }

    def get_available_functions(self) -> Dict[str, Callable]:
        """获取所有可调用函数"""
        return {
            name: info["method"]
            for name, info in self.tools.items()
        }

    def get_langchain_tools(self) -> List[BaseTool]:
        """转换为 LangChain BaseTool 格式"""
        # 实现省略...
        pass
```

---

## 5. 具体实施建议

### 5.1 短期改进（1-2 周）⚡

#### 优先级 1: 统一工具结果格式

**文件**: `tools/base.py` (新增)

```python
# 创建 ToolResult 和 WeaverTool 基类
# 修改现有工具返回统一格式
```

**影响范围**: 低
**收益**: 高（统一错误处理）

---

#### 优先级 2: 增强事件系统

**文件**: `agent/events.py` (修改)

```python
# 添加新事件类型：
# - TOOL_STREAM_START
# - TOOL_STREAM_CHUNK
# - TOOL_STREAM_END
# - XML_TOOL_DETECTED
# - AUTO_CONTINUE
```

**影响范围**: 低
**收益**: 中（更好的可观测性）

---

#### 优先级 3: 配置类引入

**文件**: `agent/processor_config.py` (新增)

```python
# 创建 AgentProcessorConfig
# 在 agent_factory.py 中使用
```

**影响范围**: 低
**收益**: 中（灵活配置）

---

### 5.2 中期改进（2-4 周）🚀

#### 优先级 1: XML 工具调用支持

**文件**:
- `agent/xml_parser.py` (新增)
- `agent/response_processor.py` (新增)
- `agent/nodes.py` (修改)

**实施步骤**:
1. 移植 XMLToolParser
2. 在响应处理中添加 XML 检测
3. 测试 Claude 模型的 XML 工具调用

**影响范围**: 中
**收益**: 高（Claude 友好）

---

#### 优先级 2: 自动续写机制

**文件**: `agent/nodes.py` (修改)

**实施步骤**:
1. 在 agent_node 中实现 auto-continue 循环
2. 添加 finish_reason 检测
3. 添加续写计数和限制

**影响范围**: 中
**收益**: 高（复杂任务体验）

---

#### 优先级 3: 工具注册表增强

**文件**: `tools/registry.py` (重构)

**实施步骤**:
1. 实现 EnhancedToolRegistry
2. 支持工具类注册
3. 支持选择性启用方法

**影响范围**: 中
**收益**: 中（灵活性）

---

### 5.3 长期优化（1-2 月）🎯

#### 优先级 1: 流式处理重构

**文件**: `agent/response_processor.py` (新增)

**目标**: 借鉴 Manus 的 ResponseProcessor 架构

**影响范围**: 高
**收益**: 高（统一流式逻辑）

---

#### 优先级 2: 可观测性增强

**文件**: `common/observability.py` (新增)

**目标**: 集成 Langfuse trace

**影响范围**: 低
**收益**: 高（调试和监控）

---

#### 优先级 3: 上下文管理优化

**文件**: `agent/context_manager.py` (增强)

**目标**: 借鉴 Manus 的智能压缩和摘要

**影响范围**: 中
**收益**: 中（长对话支持）

---

## 6. 代码示例

### 6.1 完整的工具示例

```python
# tools/enhanced_search_tool.py
from tools.base import WeaverTool, tool_schema, ToolResult
from typing import List, Dict, Any
import json

class EnhancedSearchTool(WeaverTool):
    """增强的搜索工具（借鉴 Manus 设计）"""

    def __init__(self, api_key: str, max_retries: int = 3):
        self.api_key = api_key
        self.max_retries = max_retries
        super().__init__()

    @tool_schema(
        name="search_web",
        description="Search the web for current information",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5
                },
                "search_type": {
                    "type": "string",
                    "enum": ["general", "news", "academic"],
                    "description": "Type of search",
                    "default": "general"
                }
            },
            "required": ["query"]
        }
    )
    def search(
        self,
        query: str,
        max_results: int = 5,
        search_type: str = "general"
    ) -> ToolResult:
        """执行搜索"""
        try:
            # 搜索逻辑
            results = self._perform_search(query, max_results, search_type)

            return self.success_response({
                "query": query,
                "results": results,
                "count": len(results)
            }, metadata={
                "search_type": search_type,
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            return self.fail_response(
                f"Search failed: {str(e)}",
                metadata={"error_type": type(e).__name__}
            )

    @tool_schema(
        name="search_images",
        description="Search for images",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Image search query"},
                "count": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    )
    def search_images(self, query: str, count: int = 5) -> ToolResult:
        """搜索图片"""
        try:
            images = self._search_images(query, count)
            return self.success_response({"images": images})
        except Exception as e:
            return self.fail_response(f"Image search failed: {e}")

# 使用示例
registry = EnhancedToolRegistry()
registry.register_tool_class(
    EnhancedSearchTool,
    function_names=["search", "search_images"],  # 选择性启用
    api_key=settings.tavily_api_key,
    max_retries=3
)
```

---

## 7. 实施路线图

### Phase 1: 基础增强（Week 1-2）

```
Week 1:
  Day 1-2: 创建 tools/base.py (ToolResult, WeaverTool)
  Day 3-4: 修改现有工具使用新基类
  Day 5: 增强 agent/events.py (新事件类型)

Week 2:
  Day 1-2: 创建 agent/processor_config.py
  Day 3-4: 在 agent_factory.py 中集成配置
  Day 5: 测试和文档
```

### Phase 2: 核心功能（Week 3-6）

```
Week 3-4: XML 工具调用支持
  - 移植 XMLToolParser
  - 增强响应处理
  - Claude 模型测试

Week 5-6: 自动续写机制
  - 实现 auto-continue 循环
  - finish_reason 检测
  - 测试复杂任务流程
```

### Phase 3: 高级优化（Week 7-12）

```
Week 7-8: 工具注册表重构
Week 9-10: 流式处理重构
Week 11-12: 可观测性增强 + 上下文管理优化
```

---

## 8. 总结

### 8.1 Manus 的核心优势

1. ✅ **装饰器驱动的工具系统**: 元数据与实现紧密耦合
2. ✅ **双模式工具调用**: XML + Native 兼容更多模型
3. ✅ **流式响应处理**: 实时解析和执行
4. ✅ **自动续写机制**: 无需手动管理工具调用循环
5. ✅ **配置驱动架构**: 行为可灵活切换

### 8.2 Weaver 的现有优势

1. ✅ **LangGraph 工作流**: 可视化和复杂路由
2. ✅ **LangChain 中间件栈**: 强大的工具管理
3. ✅ **事件驱动系统**: 完善的可观测性
4. ✅ **沙箱工具集成**: 安全的代码执行环境

### 8.3 融合建议

**最佳实践: 保留 Weaver 的 LangGraph 优势，借鉴 Manus 的工具系统设计**

```
┌────────────────────────────────────────────────────────┐
│              Weaver Enhanced (融合版)                  │
├────────────────────────────────────────────────────────┤
│  LangGraph Workflow (保留)                             │
│  ↓                                                     │
│  Enhanced Tool System (借鉴 Manus)                     │
│  ↓                                                     │
│  XML + Native Tool Calling (新增)                      │
│  ↓                                                     │
│  Auto-Continue Mechanism (新增)                        │
└────────────────────────────────────────────────────────┘
```

---

## 附录

### A. 关键文件路径

#### Manus 项目（参考）
- `/f/learning/实战项目三："Manus"通用智能体项目开发实战/part 1. FuFanManus系统架构及本地部署/02_前后端源码/backend/agentpress/`
  - `tool.py`
  - `tool_registry.py`
  - `xml_tool_parser.py`
  - `response_processor.py`
  - `thread_manager.py`

#### Weaver 项目（实施）
- `F:\pythonproject\Weaver\`
  - `tools/base.py` (新增)
  - `tools/registry.py` (增强)
  - `agent/xml_parser.py` (新增)
  - `agent/response_processor.py` (新增)
  - `agent/processor_config.py` (新增)
  - `agent/nodes.py` (修改)
  - `agent/events.py` (修改)

---

**结论**:

Manus 的 AgentPress 框架提供了一套优雅的工具驱动架构。Weaver 可以在保留 LangGraph 编排优势的基础上，借鉴这些设计模式，特别是：

1. 工具系统的装饰器模式
2. XML 工具调用支持
3. 自动续写机制
4. 配置驱动的处理策略

建议按照 **短期 → 中期 → 长期** 的优先级逐步实施，每个阶段完成后充分测试，确保不影响现有功能。

---

**下一步行动**:

1. ✅ 阅读本报告理解核心设计
2. ✅ 从短期改进开始实施
3. ✅ 根据实际效果调整计划
4. ✅ 持续迭代优化

有任何问题随时咨询！🚀
