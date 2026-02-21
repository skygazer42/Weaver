# 路线图与规划

Weaver 的目标是做一个“可迁移、可扩展、面向开发者”的 AI Agent 平台：你可以先跑起来、再逐步替换模型/工具/存储/鉴权/前端展示，而不是从 0 拼装一套。

---

## 已有能力（概览）

- 智能路由：direct / web / agent / deep
- Deep Research：多轮研究 + 引用证据展示
- 工具生态：代码执行 / 浏览器自动化 / 文件与文档生成等
- OpenAPI 合约对齐：后端 → 前端 types 自动生成（防漂移）
- 流式输出体验：SSE 事件流、工具调用对齐、代码块可读性优化

---

## Deep Research VNext（方向）

以下内容偏“规划/方向”，会随着实现与评估调整：

- 多搜索引擎编排（fallback / parallel / round_robin / best_first）
- 时效性排序（time-sensitive query freshness ranking）
- 领域感知 provider profile（scientific / medical / technical 等）
- 搜索可靠性保护（重试 + 熔断）
- 引用门禁（citation gate）与质量回路
- DeepSearch 预算守卫（时间 / Token）
- 会话级搜索缓存（TTL）
- Deep research artifact 持久化与恢复
- Benchmark loader + golden 回归脚本

相关文档：

- `docs/deep-research-rollout.md`
- `docs/benchmarks/README.md`
- `docs/IMPROVEMENT_PLAN_V2.md`
