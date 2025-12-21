# Manus Agent 核心功能复现计划

**版本**: v1.0
**日期**: 2024-12-21
**项目**: Weaver Agent Enhancement
**目标**: 在 Weaver 中逐步实现 Manus 的核心架构特性

---

## 📋 总体目标

在保留 Weaver 的 LangGraph 工作流优势基础上，融合 Manus 的核心设计：
- ✅ 统一的工具基类系统
- ✅ XML 工具调用支持（Claude 友好）
- ✅ 自动续写机制
- ✅ 配置驱动的处理策略
- ✅ 增强的工具注册表
- ✅ 流式响应处理优化

---

## 🎯 实施原则

1. **渐进式实施** - 每个阶段独立完成，可测试验证
2. **向后兼容** - 通过配置开关控制新功能
3. **最小侵入** - 优先新增文件，谨慎修改现有代码
4. **充分测试** - 每个阶段完成后立即测试
5. **可回滚** - 所有改动通过配置可回退

---

## 📅 实施阶段

### Phase 1: 工具系统基础 (Week 1-2) ⭐⭐⭐⭐⭐

**目标**: 建立统一的工具基类和结果容器

#### 任务清单

##### Task 1.1: 创建工具基类 (Day 1-2)
**文件**: `tools/base.py` (新增)

**实现内容**:
```python
# 1. ToolResult 数据类
@dataclass
class ToolResult:
    success: bool
    output: str
    metadata: Optional[Dict[str, Any]]

# 2. WeaverTool 抽象基类
class WeaverTool(ABC):
    - __init__() - 初始化和 schema 注册
    - _register_schemas() - 自动扫描装饰器
    - success_response() - 成功响应
    - fail_response() - 失败响应

# 3. tool_schema 装饰器
def tool_schema(**schema):
    # 装饰器逻辑
```

**验收标准**:
- ✅ ToolResult 可以序列化为 JSON
- ✅ WeaverTool 可以被继承
- ✅ 装饰器可以标记方法并注册 schema
- ✅ 单元测试通过

##### Task 1.2: 创建示例工具 (Day 3)
**文件**: `tools/example_enhanced_tool.py` (新增)

**实现内容**:
```python
class ExampleEnhancedTool(WeaverTool):
    @tool_schema(
        name="example_search",
        description="Example search tool",
        parameters={...}
    )
    def search(self, query: str) -> ToolResult:
        # 实现
```

**验收标准**:
- ✅ 继承 WeaverTool 正常工作
- ✅ Schema 自动注册
- ✅ 返回 ToolResult 格式

##### Task 1.3: 兼容层实现 (Day 4)
**文件**: `tools/langchain_adapter.py` (新增)

**实现内容**:
```python
def weaver_tool_to_langchain(tool: WeaverTool) -> List[BaseTool]:
    """将 WeaverTool 转换为 LangChain BaseTool"""

def langchain_result_to_tool_result(result: str) -> ToolResult:
    """将 LangChain 工具结果转换为 ToolResult"""
```

**验收标准**:
- ✅ WeaverTool 可以转换为 LangChain BaseTool
- ✅ 现有工具可以继续使用
- ✅ 集成测试通过

##### Task 1.4: 更新现有工具 (Day 5-6)
**文件**:
- `tools/tavily_search.py` (修改)
- `tools/browser_tool.py` (修改)
- `tools/python_code_tool.py` (修改)

**实现内容**:
逐个将现有工具迁移到新基类，同时保持向后兼容

**验收标准**:
- ✅ 所有现有工具使用新基类
- ✅ 现有功能不受影响
- ✅ 返回统一的 ToolResult 格式

##### Task 1.5: 测试和文档 (Day 7)
**文件**:
- `tests/test_tool_base.py` (新增)
- `docs/TOOL_SYSTEM_GUIDE.md` (新增)

**测试内容**:
- 工具基类单元测试
- 装饰器功能测试
- LangChain 兼容性测试
- 端到端集成测试

---

### Phase 2: XML 工具调用支持 (Week 3-4) ⭐⭐⭐⭐

**目标**: 实现 Claude 友好的 XML 工具调用格式

#### 任务清单

##### Task 2.1: XML 解析器 (Day 1-2)
**文件**: `agent/xml_parser.py` (新增)

**实现内容**:
```python
class XMLToolParser:
    # 正则模式
    FUNCTION_CALLS_PATTERN = re.compile(...)
    INVOKE_PATTERN = re.compile(...)
    PARAMETER_PATTERN = re.compile(...)

    def parse_content(self, content: str) -> List[XMLToolCall]
    def _parse_parameter_value(self, value: str) -> Any
```

**验收标准**:
- ✅ 解析 `<function_calls>` 块
- ✅ 提取 `<invoke>` 和参数
- ✅ 智能类型推断（JSON/布尔/数字/字符串）
- ✅ 容错性强（处理格式错误）

##### Task 2.2: 响应处理增强 (Day 3-4)
**文件**: `agent/response_handler.py` (新增)

**实现内容**:
```python
class EnhancedResponseHandler:
    def __init__(self, xml_parser: XMLToolParser)

    async def process_stream(
        self,
        response_stream: AsyncGenerator,
        enable_xml: bool = True,
        enable_native: bool = True
    ) -> AsyncGenerator
```

**验收标准**:
- ✅ 实时检测 XML 工具调用
- ✅ 同时支持 Native 格式（OpenAI）
- ✅ 流式 yield 工具调用事件
- ✅ 执行工具并返回结果

##### Task 2.3: 配置驱动架构 (Day 5)
**文件**: `agent/processor_config.py` (新增)

**实现内容**:
```python
@dataclass
class AgentProcessorConfig:
    # 工具调用模式
    xml_tool_calling: bool = True
    native_tool_calling: bool = True

    # 执行策略
    execute_tools: bool = True
    tool_execution_strategy: Literal["sequential", "parallel"] = "sequential"

    # 自动续写
    enable_auto_continue: bool = True
    max_auto_continues: int = 25
```

**验收标准**:
- ✅ 所有行为可配置
- ✅ 集成到 common/config.py
- ✅ 环境变量控制

##### Task 2.4: 节点集成 (Day 6)
**文件**: `agent/nodes.py` (修改)

**实现内容**:
在 `agent_node` 中集成 XML 工具调用支持

**验收标准**:
- ✅ 通过配置开关启用
- ✅ 与现有 Native 格式并存
- ✅ Claude 模型测试通过

##### Task 2.5: 测试和文档 (Day 7-8)
**文件**:
- `tests/test_xml_parser.py` (新增)
- `tests/test_xml_tool_calling.py` (新增)
- `docs/XML_TOOL_CALLING_GUIDE.md` (新增)

**测试内容**:
- XML 解析器单元测试
- 工具调用集成测试
- Claude 模型端到端测试

---

### Phase 3: 自动续写机制 (Week 5-6) ⭐⭐⭐⭐⭐

**目标**: 实现基于 finish_reason 的自动续写循环

#### 任务清单

##### Task 3.1: finish_reason 检测 (Day 1-2)
**文件**: `agent/continuation.py` (新增)

**实现内容**:
```python
class AutoContinuationHandler:
    def should_continue(self, response: Dict) -> bool:
        """检查是否需要自动续写"""

    async def execute_continuation_loop(
        self,
        agent_executor: Callable,
        state: Dict,
        max_continues: int = 25
    ) -> Dict
```

**验收标准**:
- ✅ 准确检测 finish_reason
- ✅ 正确判断是否续写
- ✅ 防止无限循环

##### Task 3.2: 状态跨轮保持 (Day 3)
**文件**: `agent/continuation.py` (修改)

**实现内容**:
```python
class ContinuationState:
    accumulated_output: str
    continue_count: int
    tool_results: List[ToolResult]

    def merge_state(self, new_state: Dict) -> Dict
```

**验收标准**:
- ✅ 状态正确累积
- ✅ 工具结果正确注入对话历史
- ✅ 上下文完整性

##### Task 3.3: 节点改造 (Day 4-5)
**文件**: `agent/nodes.py` (修改)

**实现内容**:
```python
async def agent_node_with_auto_continue(
    state: AgentState,
    config: RunnableConfig,
    max_continues: int = 25
) -> Dict[str, Any]:
    """支持自动续写的 agent 节点"""

    continuation_handler = AutoContinuationHandler()
    return await continuation_handler.execute_continuation_loop(...)
```

**验收标准**:
- ✅ 自动续写正常工作
- ✅ 通过配置开关启用
- ✅ 与原版节点共存

##### Task 3.4: 事件系统增强 (Day 6)
**文件**: `agent/events.py` (修改)

**实现内容**:
添加新事件类型：
- `AUTO_CONTINUE_START`
- `AUTO_CONTINUE_ITERATION`
- `AUTO_CONTINUE_COMPLETE`

**验收标准**:
- ✅ 事件正确触发
- ✅ 前端可以显示续写进度
- ✅ 日志完整

##### Task 3.5: 测试和文档 (Day 7)
**文件**:
- `tests/test_auto_continue.py` (新增)
- `docs/AUTO_CONTINUE_GUIDE.md` (新增)

**测试内容**:
- 多轮工具调用测试
- 续写计数测试
- 状态保持测试
- 复杂任务端到端测试

---

### Phase 4: 工具注册表增强 (Week 7-8) ⭐⭐⭐

**目标**: 实现动态方法扫描和选择性注册

#### 任务清单

##### Task 4.1: 增强注册表 (Day 1-3)
**文件**: `tools/enhanced_registry.py` (新增)

**实现内容**:
```python
class EnhancedToolRegistry:
    def register_tool_class(
        self,
        tool_class: Type[WeaverTool],
        function_names: Optional[List[str]] = None,
        **init_kwargs
    ):
        """注册工具类，支持选择性启用方法"""

    def get_available_functions(self) -> Dict[str, Callable]
    def get_openapi_schemas(self) -> List[Dict]
    def get_langchain_tools(self) -> List[BaseTool]
```

**验收标准**:
- ✅ 自动扫描工具类方法
- ✅ 选择性启用功能
- ✅ 传递初始化参数
- ✅ 兼容现有注册表

##### Task 4.2: 迁移现有工具 (Day 4-5)
**文件**:
- `agent/agent_factory.py` (修改)
- `tools/__init__.py` (修改)

**实现内容**:
使用新注册表替换旧的工具管理方式

**验收标准**:
- ✅ 所有工具正常注册
- ✅ 功能不受影响
- ✅ 性能无明显下降

##### Task 4.3: 测试和文档 (Day 6-7)
**文件**:
- `tests/test_enhanced_registry.py` (新增)
- `docs/TOOL_REGISTRY_GUIDE.md` (新增)

---

### Phase 5: 流式处理优化 (Week 9-10) ⭐⭐⭐⭐

**目标**: 统一流式响应处理逻辑

#### 任务清单

##### Task 5.1: 响应处理器 (Day 1-4)
**文件**: `agent/response_processor.py` (新增)

**实现内容**:
```python
class ResponseProcessor:
    def __init__(
        self,
        xml_parser: XMLToolParser,
        tool_registry: EnhancedToolRegistry,
        config: AgentProcessorConfig
    )

    async def process_streaming_response(
        self,
        llm_response: AsyncGenerator,
        thread_id: str,
        config: ProcessorConfig
    ) -> AsyncGenerator[Dict[str, Any], None]
```

**验收标准**:
- ✅ 统一处理 XML 和 Native 格式
- ✅ 支持流式和批量执行
- ✅ 配置驱动策略切换
- ✅ 并行/串行工具执行

##### Task 5.2: 节点重构 (Day 5-7)
**文件**: `agent/nodes.py` (重构)

**实现内容**:
使用统一的 ResponseProcessor 替换分散的处理逻辑

**验收标准**:
- ✅ 代码更简洁
- ✅ 逻辑更清晰
- ✅ 性能提升
- ✅ 功能完整

##### Task 5.3: 测试和文档 (Day 8-10)
**文件**:
- `tests/test_response_processor.py` (新增)
- `docs/RESPONSE_PROCESSING_GUIDE.md` (新增)

---

### Phase 6: 集成测试与优化 (Week 11-12) ⭐⭐⭐⭐⭐

**目标**: 全面测试、性能优化、文档完善

#### 任务清单

##### Task 6.1: 端到端测试 (Day 1-3)
**文件**: `tests/integration/` (新增目录)

**测试场景**:
1. 简单任务（单次工具调用）
2. 复杂任务（多轮工具调用 + 自动续写）
3. XML 工具调用（Claude 模型）
4. Native 工具调用（OpenAI 模型）
5. 混合模式（XML + Native）
6. 错误处理和恢复
7. 并发工具执行
8. 长对话上下文管理

##### Task 6.2: 性能优化 (Day 4-5)
- Token 使用优化
- 工具执行并行化
- 响应延迟优化
- 内存使用优化

##### Task 6.3: 文档完善 (Day 6-7)
**文件**:
- `docs/MANUS_FEATURES_COMPLETE_GUIDE.md` (新增)
- `README.md` (更新)
- `docs/API_REFERENCE.md` (新增)

##### Task 6.4: 迁移指南 (Day 8)
**文件**: `docs/MIGRATION_GUIDE.md` (新增)

**内容**:
- 从旧版工具系统迁移
- 配置项变更说明
- 最佳实践
- 常见问题

##### Task 6.5: 发布准备 (Day 9-10)
- 版本标签
- CHANGELOG 更新
- 发布说明
- 演示视频

---

## 📊 进度跟踪

### 总体进度
```
Phase 1: 工具系统基础       [          ] 0%
Phase 2: XML 工具调用       [          ] 0%
Phase 3: 自动续写机制       [          ] 0%
Phase 4: 工具注册表增强     [          ] 0%
Phase 5: 流式处理优化       [          ] 0%
Phase 6: 集成测试与优化     [          ] 0%

总体进度:                  [          ] 0%
```

### 关键里程碑
- [ ] Phase 1 完成 - 工具系统基础可用
- [ ] Phase 2 完成 - XML 工具调用支持
- [ ] Phase 3 完成 - 自动续写机制上线
- [ ] Phase 4 完成 - 工具注册表升级
- [ ] Phase 5 完成 - 流式处理统一
- [ ] Phase 6 完成 - 全面测试通过，准备发布

---

## ⚠️ 风险评估

### 高风险项
1. **向后兼容性** - 工具系统重构可能影响现有功能
   - 缓解措施: 保留兼容层，配置开关控制

2. **性能影响** - 新增处理逻辑可能增加延迟
   - 缓解措施: 性能测试，优化关键路径

3. **复杂度增加** - 多种模式共存增加维护成本
   - 缓解措施: 充分文档，清晰的架构设计

### 中风险项
1. **XML 解析鲁棒性** - LLM 可能生成格式错误的 XML
   - 缓解措施: 容错解析，回退到 Native 格式

2. **自动续写死循环** - 可能陷入无限循环
   - 缓解措施: 最大次数限制，超时机制

### 低风险项
1. **配置管理** - 配置项增多可能导致混淆
   - 缓解措施: 合理的默认值，完善的文档

---

## 🔄 回滚方案

每个 Phase 完成后，提供回滚方案：

### Phase 1 回滚
```python
# 在 common/config.py 中
use_enhanced_tool_system: bool = False
```

### Phase 2 回滚
```python
# 在 common/config.py 中
enable_xml_tool_calling: bool = False
```

### Phase 3 回滚
```python
# 在 common/config.py 中
enable_auto_continue: bool = False
```

所有新功能通过配置开关控制，可随时回退到原版行为。

---

## 📈 成功标准

### 功能完整性
- ✅ 所有 6 个 Phase 的核心功能实现
- ✅ 100% 向后兼容
- ✅ 所有单元测试通过
- ✅ 所有集成测试通过

### 性能指标
- ✅ 响应延迟增加 < 10%
- ✅ Token 使用增加 < 15%
- ✅ 内存使用增加 < 20%

### 质量指标
- ✅ 工具调用成功率 > 95%
- ✅ XML 解析成功率 > 90%
- ✅ 自动续写正确率 > 95%

### 文档完整性
- ✅ 每个功能都有详细文档
- ✅ API 参考文档完整
- ✅ 迁移指南清晰
- ✅ 示例代码充分

---

## 📚 交付物清单

### 代码文件 (新增)
```
tools/
├── base.py                        # 工具基类
├── example_enhanced_tool.py       # 示例工具
├── langchain_adapter.py          # LangChain 兼容层
└── enhanced_registry.py          # 增强注册表

agent/
├── xml_parser.py                 # XML 解析器
├── response_handler.py           # 响应处理器
├── processor_config.py           # 处理器配置
├── continuation.py               # 自动续写
└── response_processor.py         # 统一响应处理器

tests/
├── test_tool_base.py
├── test_xml_parser.py
├── test_xml_tool_calling.py
├── test_auto_continue.py
├── test_enhanced_registry.py
├── test_response_processor.py
└── integration/
    ├── test_simple_tasks.py
    ├── test_complex_tasks.py
    └── test_mixed_mode.py
```

### 代码文件 (修改)
```
tools/
├── tavily_search.py              # 迁移到新基类
├── browser_tool.py               # 迁移到新基类
└── python_code_tool.py           # 迁移到新基类

agent/
├── nodes.py                      # 集成新功能
├── events.py                     # 新增事件类型
└── agent_factory.py              # 使用新注册表

common/
└── config.py                     # 新增配置项
```

### 文档文件
```
docs/
├── MANUS_IMPLEMENTATION_PLAN.md   # 本文档
├── TOOL_SYSTEM_GUIDE.md          # 工具系统指南
├── XML_TOOL_CALLING_GUIDE.md     # XML 调用指南
├── AUTO_CONTINUE_GUIDE.md        # 自动续写指南
├── TOOL_REGISTRY_GUIDE.md        # 注册表指南
├── RESPONSE_PROCESSING_GUIDE.md  # 响应处理指南
├── MANUS_FEATURES_COMPLETE_GUIDE.md  # 完整特性指南
├── MIGRATION_GUIDE.md            # 迁移指南
└── API_REFERENCE.md              # API 参考
```

---

## 🚀 下一步行动

1. **确认计划** - 审查本实施计划，确认优先级和范围
2. **环境准备** - 创建开发分支，设置测试环境
3. **开始 Phase 1** - 创建 `tools/base.py`，实现工具基类
4. **持续迭代** - 按照计划逐步推进，及时测试验证

---

**准备开始实施！** 🎯

请确认是否开始 Phase 1 的实施，或者需要调整计划。
