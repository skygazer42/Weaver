# Weaver 深度研究能力提升计划 v2

> 基于对 GPT-Researcher、LangChain Open Deep Research、SkyworkAI DeepResearchAgent、ByteDance DeerFlow、MiroThinker 等高星项目的分析

## 行业顶尖项目特性对比

| 特性 | GPT-Researcher | Open Deep Research | DeepResearchAgent | DeerFlow | MiroThinker | Weaver现状 |
|-----|----------------|-------------------|------------------|----------|-------------|-----------|
| 树状探索 | ✅ | - | - | ✅ | - | ✅ 已实现 |
| 知识空白分析 | - | ✅ | - | - | - | ✅ 已实现 |
| 层级多Agent | - | - | ✅ | ✅ | - | ❌ 待开发 |
| 本地文档分析 | ✅ PDF/Word/Excel | - | ✅ | - | ✅ | ❌ 待开发 |
| RAG集成 | - | - | - | ✅ RAGFlow | - | ❌ 待开发 |
| 多搜索源 | ✅ 20+ | ✅ MCP | ✅ | ✅ InfoQuest | ✅ | ⚠️ 仅Tavily |
| 报告导出 | ✅ PDF/Word/MD | - | - | - | - | ❌ 待开发 |
| TTS语音 | - | - | - | ✅ | - | ⚠️ 部分 |
| 多模态输出 | ✅ AI插图 | - | - | ✅ PPT/播客 | - | ❌ 待开发 |
| 异步并行 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ 部分 |
| 基准测试 | - | ✅ RACE | - | - | ✅ GAIA 80.8% | ❌ 待开发 |
| 子Agent隔离 | - | - | ✅ | ✅ | - | ❌ 待开发 |
| 交互式扩展 | - | - | - | - | ✅ 400调用/任务 | ❌ 待开发 |

---

## 20项改进任务

### 阶段一：核心架构增强 (任务 1-5)

#### 任务 1: 层级多Agent系统
**优先级**: P0 - 关键
**参考**: SkyworkAI DeepResearchAgent, DeerFlow
**描述**: 实现两层Agent架构
- 顶层: Planning Agent (任务分解、协调)
- 底层: 专业化Agent (Researcher, Analyzer, Browser, Coder)

**文件变更**:
- 新建 `agent/core/hierarchy.py` - Agent层级管理
- 新建 `agent/workflows/agents/` 目录 - 专业Agent实现
  - `researcher_agent.py` - 研究Agent
  - `analyzer_agent.py` - 分析Agent
  - `browser_agent.py` - 浏览器Agent
  - `coder_agent.py` - 代码Agent
  - `coordinator_agent.py` - 协调Agent
- 修改 `agent/core/graph.py` - 集成层级系统

**验收标准**:
- [ ] Planning Agent 可分解任务
- [ ] 专业Agent可独立执行子任务
- [ ] Agent间可协调通信

---

#### 任务 2: 多搜索源聚合
**优先级**: P0 - 关键
**参考**: GPT-Researcher (20+ sources)
**描述**: 支持多个搜索引擎并行搜索

**新增搜索源**:
- Bing Search API
- Google Custom Search
- DuckDuckGo (无需API)
- Brave Search
- SearXNG (自托管)
- Serper.dev

**文件变更**:
- 新建 `tools/search/multi_search.py` - 多源搜索聚合器
- 新建 `tools/search/providers/` - 各搜索源实现
  - `bing.py`
  - `google.py`
  - `duckduckgo.py`
  - `brave.py`
  - `searxng.py`
- 修改 `common/config.py` - 添加多源配置

**验收标准**:
- [ ] 支持至少5个搜索源
- [ ] 可配置优先级和权重
- [ ] 结果自动去重合并
- [ ] 优雅降级(源不可用时)

---

#### 任务 3: 本地文档RAG集成
**优先级**: P0 - 关键
**参考**: GPT-Researcher, DeerFlow RAGFlow
**描述**: 支持本地文档作为研究知识源

**支持格式**:
- PDF (含OCR)
- Word (.docx)
- Excel (.xlsx)
- Markdown (.md)
- CSV
- 代码文件

**文件变更**:
- 新建 `tools/rag/` 目录
  - `document_loader.py` - 文档加载器
  - `chunker.py` - 文档切分
  - `embedder.py` - 向量嵌入
  - `retriever.py` - 检索器
  - `local_rag.py` - 本地RAG主入口
- 修改 `agent/workflows/deepsearch_optimized.py` - 集成RAG

**依赖新增**:
```
pypdf2
python-docx
openpyxl
langchain-chroma
```

**验收标准**:
- [ ] 可上传并解析多种格式文档
- [ ] 支持向量检索
- [ ] 与在线搜索结果融合
- [ ] 支持增量更新索引

---

#### 任务 4: 异步并行研究引擎
**优先级**: P1 - 高
**参考**: MiroThinker (400 tool calls/task)
**描述**: 提升并发研究能力

**实现内容**:
- 异步搜索执行
- 并行URL爬取
- 并行分支探索
- 资源池管理

**文件变更**:
- 新建 `agent/core/async_engine.py` - 异步执行引擎
- 修改 `agent/workflows/research_tree.py` - 异步分支探索
- 修改 `tools/crawl/crawler.py` - 异步爬取

**验收标准**:
- [ ] 支持并行执行10+个搜索
- [ ] 支持并行爬取20+个URL
- [ ] 资源使用可配置
- [ ] 保持取消支持

---

#### 任务 5: 子Agent上下文隔离
**优先级**: P1 - 高
**参考**: LangChain Deep Agents
**描述**: 子Agent独立上下文窗口

**实现内容**:
- 每个子Agent有独立消息历史
- 支持上下文摘要注入
- 结果汇总回主Agent

**文件变更**:
- 新建 `agent/core/context_isolation.py` - 上下文隔离管理
- 修改 `agent/core/state.py` - 添加子上下文字段

**验收标准**:
- [ ] 子Agent不共享消息历史
- [ ] 可注入父上下文摘要
- [ ] 结果正确汇总

---

### 阶段二：输出能力增强 (任务 6-10)

#### 任务 6: 报告导出格式
**优先级**: P1 - 高
**参考**: GPT-Researcher
**描述**: 支持多种格式导出

**支持格式**:
- Markdown (默认)
- PDF (带样式)
- Word (.docx)
- HTML

**文件变更**:
- 新建 `tools/export/` 目录
  - `markdown_exporter.py`
  - `pdf_exporter.py`
  - `docx_exporter.py`
  - `html_exporter.py`
  - `export_manager.py`
- 新建 `web/components/export-button.tsx` - 前端导出按钮

**依赖新增**:
```
weasyprint  # PDF
python-docx
jinja2
```

**验收标准**:
- [ ] 一键导出4种格式
- [ ] PDF保留格式和图表
- [ ] 包含引用和来源

---

#### 任务 7: AI生成插图
**优先级**: P2 - 中
**参考**: GPT-Researcher (Gemini)
**描述**: 报告中自动生成信息图

**实现内容**:
- 关键概念可视化
- 数据图表生成
- 流程图/架构图
- 时间线

**文件变更**:
- 新建 `tools/visualization/` 目录
  - `chart_generator.py` - 图表生成
  - `infographic.py` - 信息图生成
  - `diagram.py` - 流程图生成
- 修改 `agent/workflows/nodes.py` - writer节点集成

**验收标准**:
- [ ] 可生成3种以上图表类型
- [ ] 自动识别适合可视化的数据
- [ ] 图片嵌入报告

---

#### 任务 8: 多模态输出 (PPT/播客)
**优先级**: P2 - 中
**参考**: DeerFlow
**描述**: 支持演示文稿和音频输出

**实现内容**:
- 研究报告转PPT
- 报告转语音(播客风格)
- 摘要视频脚本

**文件变更**:
- 新建 `tools/multimodal/` 目录
  - `ppt_generator.py` - PPT生成
  - `podcast_generator.py` - 播客生成
  - `video_script.py` - 视频脚本
- 修改 API 添加导出端点

**验收标准**:
- [ ] 可生成带样式的PPT
- [ ] 可生成MP3音频
- [ ] 可配置风格和长度

---

#### 任务 9: TTS报告朗读增强
**优先级**: P2 - 中
**参考**: DeerFlow
**描述**: 增强现有TTS能力

**实现内容**:
- 长文本分段合成
- 多种声音风格
- 语速/音调可调
- 背景音乐(可选)

**文件变更**:
- 修改 `tools/tts/` - 增强TTS功能
- 新建 `web/components/audio-player.tsx` - 音频播放器

**验收标准**:
- [ ] 支持10000+字报告
- [ ] 3种以上声音风格
- [ ] 流式播放

---

#### 任务 10: 研究过程可视化
**优先级**: P2 - 中
**描述**: 可视化研究树和进度

**实现内容**:
- 研究树实时展示
- 分支探索进度
- 知识覆盖热力图
- 来源网络图

**文件变更**:
- 新建 `web/components/research-tree-viz.tsx`
- 新建 `web/components/coverage-map.tsx`
- 修改 API 推送树状态

**依赖新增**:
```
d3 / react-flow
```

**验收标准**:
- [ ] 实时显示研究树
- [ ] 节点可点击查看详情
- [ ] 覆盖度可视化

---

### 阶段三：智能化提升 (任务 11-15)

#### 任务 11: 领域专家路由
**优先级**: P1 - 高
**参考**: Open Deep Research (22 domains)
**描述**: 根据主题路由到专业领域

**支持领域**:
- 科技/编程
- 医学/健康
- 法律/政策
- 金融/经济
- 学术/论文
- 新闻/时事
- 产品/商业

**文件变更**:
- 新建 `agent/core/domain_router.py` - 领域路由
- 新建 `prompts/templates/domains/` - 领域专用提示词
- 修改 `agent/core/smart_router.py` - 集成领域路由

**验收标准**:
- [ ] 自动识别7+领域
- [ ] 领域专用搜索策略
- [ ] 领域专用报告模板

---

#### 任务 12: 研究质量自评估
**优先级**: P1 - 高
**参考**: MiroThinker GAIA
**描述**: 内置研究质量评估

**评估维度**:
- 信息覆盖度
- 来源可靠性
- 时效性
- 一致性
- 深度

**文件变更**:
- 新建 `agent/core/quality_scorer.py` - 质量评分
- 修改 `agent/workflows/nodes.py` - evaluator增强

**验收标准**:
- [ ] 5维度自动评分
- [ ] 评分可解释
- [ ] 触发自动补充研究

---

#### 任务 13: 迭代知识填充 (IterDRAG增强)
**优先级**: P1 - 高
**参考**: 已有knowledge_gap.py
**描述**: 增强现有知识空白分析

**实现内容**:
- 多轮迭代填充
- 优先级调度
- 收敛检测
- 最大迭代控制

**文件变更**:
- 修改 `agent/workflows/knowledge_gap.py` - 增强迭代
- 修改 `agent/workflows/deepsearch_optimized.py` - 集成

**验收标准**:
- [ ] 自动多轮补充
- [ ] 覆盖度收敛到80%+
- [ ] 避免无限循环

---

#### 任务 14: 多模型协作
**优先级**: P1 - 高
**参考**: Open Deep Research
**描述**: 不同任务使用最优模型

**模型分配**:
- 路由/分类: 快速模型 (GPT-4-mini)
- 规划/推理: 推理模型 (o1/DeepSeek)
- 摘要/写作: 写作模型 (Claude/GPT-4)
- 评估: 评估模型

**文件变更**:
- 完善 `agent/core/multi_model.py`
- 修改 `common/config.py` - 模型配置

**验收标准**:
- [ ] 可配置4类模型
- [ ] 自动根据任务选模型
- [ ] 支持API兼容模型

---

#### 任务 15: 人机协作增强
**优先级**: P1 - 高
**参考**: DeerFlow HITL
**描述**: 增强human-in-the-loop

**实现内容**:
- 计划审批中断
- 关键决策确认
- 中间结果反馈
- 方向修正

**文件变更**:
- 修改 `agent/workflows/nodes.py` - human_review增强
- 新建 `web/components/approval-dialog.tsx`
- 修改 API interrupt端点

**验收标准**:
- [ ] 计划需用户审批
- [ ] 可中途调整方向
- [ ] 反馈影响后续研究

---

### 阶段四：工程能力 (任务 16-20)

#### 任务 16: 研究会话持久化与恢复
**优先级**: P1 - 高
**参考**: Deep Agents
**描述**: 支持长研究任务中断恢复

**实现内容**:
- 完整状态快照
- 断点恢复
- 历史会话浏览
- 导出/导入会话

**文件变更**:
- 新建 `agent/core/session_manager.py`
- 修改数据库schema
- 新建 `web/pages/sessions.tsx`

**验收标准**:
- [ ] 任意点可暂停
- [ ] 完整恢复研究进度
- [ ] 会话可导出分享

---

#### 任务 17: 基准测试套件
**优先级**: P2 - 中
**参考**: MiroThinker GAIA, Open Deep Research RACE
**描述**: 建立评测体系

**评测集**:
- 自建问答集 (100题)
- GAIA子集适配
- 时效性测试集
- 深度测试集

**文件变更**:
- 新建 `tests/benchmarks/` 目录
- 新建评测脚本和数据集

**验收标准**:
- [ ] 可自动运行评测
- [ ] 生成评测报告
- [ ] 跟踪版本改进

---

#### 任务 18: MCP工具生态扩展
**优先级**: P2 - 中
**参考**: GPT-Researcher MCP Server
**描述**: 扩展MCP工具集成

**实现内容**:
- MCP工具自动发现
- 常用MCP服务预配置
- Weaver作为MCP Server暴露

**文件变更**:
- 新建 `tools/mcp/discovery.py`
- 新建 `mcp-server/` - Weaver MCP Server
- 修改 `tools/core/mcp.py`

**验收标准**:
- [ ] 自动发现5+MCP工具
- [ ] Weaver可作为MCP Server
- [ ] 工具描述完善

---

#### 任务 19: 监控与可观测性
**优先级**: P2 - 中
**描述**: 生产级监控

**实现内容**:
- LLM调用追踪
- Token使用统计
- 研究性能分析
- 错误报警

**文件变更**:
- 新建 `common/observability/` 目录
  - `tracing.py` - 调用追踪
  - `metrics.py` - 指标收集
  - `dashboard.py` - 仪表盘
- 修改 Prometheus指标

**验收标准**:
- [ ] 完整调用链追踪
- [ ] Token成本可视化
- [ ] 性能瓶颈可识别

---

#### 任务 20: API & SDK封装
**优先级**: P2 - 中
**描述**: 提供开发者友好的API

**实现内容**:
- RESTful API文档 (OpenAPI)
- Python SDK
- TypeScript SDK
- Webhook回调

**文件变更**:
- 新建 `sdk/python/weaver_sdk/`
- 新建 `sdk/typescript/`
- 修改 `main.py` - OpenAPI增强

**验收标准**:
- [ ] Swagger文档完善
- [ ] Python SDK可pip安装
- [ ] 示例代码完整

---

## 实施优先级矩阵

```
            高影响
              │
     P0关键   │  P1高
   ┌──────────┼──────────┐
   │ 1.多Agent │ 4.异步引擎│
   │ 2.多搜索源│ 5.上下文隔│
   │ 3.本地RAG │ 11.领域路由│
   │          │ 12.质量评估│
   │          │ 13.知识填充│
   │          │ 14.多模型 │
   │          │ 15.人机协作│
   │          │ 16.会话持久│
   ├──────────┼──────────┤
   │          │ 6.导出格式│
   │          │ 7.AI插图  │
   │          │ 8.多模态  │
   │          │ 9.TTS增强 │
   │          │ 10.过程可视│
   │          │ 17.基准测试│
   │          │ 18.MCP扩展│
   │          │ 19.监控   │
   │          │ 20.SDK    │
   └──────────┴──────────┘
            低影响
   低紧急 ─────────── 高紧急
```

---

## 参考资源

### 开源项目
- [GPT-Researcher](https://github.com/assafelovic/gpt-researcher) - 17k+ stars
- [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research) - RACE #6
- [DeepResearchAgent](https://github.com/SkyworkAI/DeepResearchAgent) - 层级多Agent
- [DeerFlow](https://github.com/bytedance/deer-flow) - ByteDance开源
- [MiroThinker](https://github.com/MiroMindAI/MiroThinker) - GAIA 80.8%
- [Deep Agents](https://github.com/langchain-ai/deepagents) - LangChain官方

### 文档
- [LangGraph Platform](https://langchain.com/langgraph)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [GAIA Benchmark](https://gaia-benchmark.github.io/)

---

*计划创建时间: 2026-02-01*
*版本: 2.0*
