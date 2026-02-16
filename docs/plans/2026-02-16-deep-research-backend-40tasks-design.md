# Deep Research Backend (Evidence-First) Design

> **Context:** 本设计用于支撑后续“40 个任务”的增量式实现：优先提升深度研究的证据链质量（引用覆盖率、可追溯、可复核、可回归），并把后端接口与前端严格对齐（以 OpenAPI 为单一真相），同时引入标准 SSE Chat 流式端点（现有协议保留兼容）。

**Date:** 2026-02-16  
**Owner:** Codex (with human review checkpoints)

---

## 1. 现状梳理（Weaver today）

### 1.1 后端（FastAPI + LangGraph）

- `main.py` 作为单体 API 入口，包含大量 endpoint + Pydantic models。
- `/api/events/{thread_id}` 已使用标准 SSE（包含 `id:`、`event:`、`data:`），并支持 `Last-Event-ID` 恢复游标（见 `agent/core/events.py`）。
- `/api/chat` 返回 `text/event-stream`，但实际 payload 采用 **Vercel AI SDK Data Stream Protocol**（当前实现为 `0:{json}\n` 逐行协议），前端通过 `fetch().body.getReader()` 自行解析。
- DeepSearch / DeepResearch 已有不少基础能力（多搜索源编排、freshness 识别、tree exploration、结果聚合等），但“证据链质量门禁”和“主张-证据一致性校验”仍属于可提升项。

### 1.2 前端（Next.js）

- Chat 走 `/api/chat`（fetch streaming），取消走 `/api/chat/cancel/{threadId}`。
- 研究过程可视化走 `/api/events/{threadId}`（EventSource SSE）。
- 对多类接口（sessions/comments/versions/share/export/tts/asr/mcp config）均采用手写 fetch。
- 当前前端 types（`web/types/chat.ts`）已隐含了若干事件字段形状，可作为对齐参考，但本项目本轮决定：**OpenAPI 为单一真相**。

---

## 2. 目标（Goals）与非目标（Non-goals）

### 2.1 Goals（本轮必达）

**G1 — Evidence-first 深度研究质量提升**
- 让“每个关键结论/主张”都能被证据支持，并能被追溯到来源 URL（含规范化与去重）。
- 引入可配置的质量门禁：引用覆盖率不足、证据冲突、freshness 不足（对时间敏感 query）时，自动回到 revise/research 分支，而不是直接输出终稿。

**G2 — OpenAPI 作为接口单一真相（Contract-first in practice）**
- 把关键接口 request/response 用稳定的 Pydantic schema 定义清楚，避免“前端猜形状 / 后端随意加字段”。
- 建立 OpenAPI → 前端 TypeScript types（或轻量 client）的自动生成流程，并加入 CI/本地校验，保证前后端不会悄悄 drift。

**G3 — 新增标准 SSE Chat 流式端点（推荐方案）**
- 新增一个 **标准 SSE** 的 chat 流式端点（`id/event/data`），并让前端默认迁移过去。
- 旧 `/api/chat` 继续兼容当前 `0:` 行协议（便于回滚与渐进迁移）。

**G4 — 评测闭环（Regression + Benchmark）**
- 接入可复现的 golden regression runner（固定小集合 query，输出结构化 JSON），并支持 nightly / 手动触发 smoke。
- 评测重点围绕：引用覆盖率、主张-证据一致性、freshness 覆盖（时间敏感）等质量指标。

### 2.2 Non-goals（本轮明确不做/不强求）

- 不做“大重构替换”现有 FastAPI + LangGraph 架构。
- 不强推全量 RAG/本地文档检索（如需可作为后续阶段）。
- 不一次性把所有前端 fetch 全部替换为生成 client（会以高频/高风险接口优先，逐步迁移）。
- 不承诺本轮把全仓库 Python ruff lint 清零（当前 `ruff check .` 在主分支存在大量历史问题；本轮保证新代码与关键改动文件尽量符合规则，且用 tests/contract tests 做主验证门禁）。

---

## 3. 参考基线（Clone & Compare Baseline）

> 我们将这些项目 clone 到工作区外的 `_refs/` 目录，仅用于对标与借鉴实现；默认优先“借鉴思路 → 本项目重写实现”。若确需直接移植代码，仅限许可证兼容（MIT/Apache-2.0/BSD），并保留必要声明。

已 clone（路径：`~/.config/superpowers/worktrees/Weaver/_refs/`）：

| Repo | License | Why it matters |
|------|---------|----------------|
| `langchain-ai/open_deep_research` | MIT | 对标“开放 deep research”范式、可运营的研究循环与评测思路 |
| `assafelovic/gpt-researcher` | Apache-2.0 | 对标 report/citation 工程化流水线与引用组织方式 |
| `bytedance/deer-flow` | MIT | 对标并行/可靠性/数据流组织、可扩展的 research pipeline |
| `SkyworkAI/DeepResearchAgent` | MIT | 对标分层 agent / 深度控制与研究子任务拆解 |
| `MiroMindAI/MiroThinker` | MIT | 对标高频工具调用与长任务稳定性/可视化模式 |
| `Ayanami0730/deep_research_bench` | Apache-2.0 | 对标 benchmark 数据格式与可复现评测闭环 |
| `microsoft/LiveDRBench` | MIT | 对标“真实世界”研究评测、发现/验证能力 |

---

## 4. 架构设计（High-level Architecture）

### 4.1 证据链数据模型（Evidence primitives）

核心新增/强化的“结构化产物”：

- **Source**（标准来源条目）
  - `source_id`（稳定 ID）
  - `url`（canonicalized）
  - `raw_url`（原始 URL）
  - `title/domain/provider/published_date`
  - `retrieved_at`
- **Claim**（可验证主张）
  - `claim_id`
  - `text`
  - `supporting_source_ids[]`
  - `status`: `verified | unsupported | contradicted`
  - `notes`（冲突摘要/缺口）
- **Quality metrics**
  - `citation_coverage`（结论是否有引用）
  - `consistency`（冲突程度）
  - `freshness_ratio_30d`（时间敏感 query 的近 30 天占比）
  - `query_coverage`（维度覆盖率/缺口数）

这些结构化结果会被：
- 写入 session snapshot（便于恢复/追溯）
- 通过 SSE/stream 发送给前端用于可视化（Research Progress Dashboard）
- 输出到评测 runner JSON 作为可比较信号

### 4.2 质量门禁（Quality Gates）

在最终报告产出前增加门禁判定：

- **Citation Gate**：引用覆盖率 < 阈值 → 进入 revise/research 分支（补证据/补来源）
- **Claim Verifier Gate**：若出现 `unsupported` 或 `contradicted` 的关键 claim → 进入 revise 分支（要求修订或补充证据）
- **Freshness Gate（time-sensitive）**：时间敏感 query 的 freshness 占比过低 → 强制补近 30 天来源或提示限制

门禁阈值可配置（env + request override），并会实时发 `quality_update` 事件给前端。

### 4.3 搜索与检索质量（Retrieval Quality）

- Multi-provider search orchestration（已有基础）补齐：
  - provider profile（domain/news/academic/general）
  - 重试 + 熔断 + 退避（provider reliability）
  - freshness-aware ranking（时间敏感）
  - canonical URL 去重（跨 provider）
- 统一结果结构（title/url/snippet/published_date/provider/score），便于后续 claim verifier 与 citation gate 使用。

---

## 5. API 设计（OpenAPI as Source of Truth）

### 5.1 总体策略

- 把关键接口的 Pydantic models 提升为“一等公民”，集中管理，避免 `main.py` 的重复/冲突。
- 修复现有 schema 命名冲突（例如当前存在两个同名 `ResumeRequest`，会导致 OpenAPI 组件覆盖风险）。
- 为高频接口补齐稳定 response schema（即便内部实现仍是 LangGraph）。

### 5.2 Chat 流式端点（新增）

新增：`POST /api/chat/sse`
- Request body 与现有 `/api/chat` 对齐（messages/model/search_mode/images/agent_id/user_id…）
- Response：标准 SSE（`text/event-stream`）
  - `event: status | text | message | completion | tool | artifact | interrupt | error | done`
  - `data: { "type": "...", "data": {...} }`
  - `id: <seq>`（可选，便于断线恢复）

兼容保留：现有 `POST /api/chat`（`0:{json}\n` 行协议）
- 默认不删除；前端迁移完成后再考虑降级为 legacy。

### 5.3 OpenAPI → 前端 types 生成

目标：让 `web/` 通过脚本生成 `web/lib/api-types.ts`（或类似文件）：
- 后端：提供可离线导出 OpenAPI JSON 的脚本（无需跑 server）
- 前端：用 `openapi-typescript` 从 JSON 生成 TS types
- CI：生成后 `git diff --exit-code` 校验，防止 drift

---

## 6. 测试与验收（Quality bar）

### 6.1 必须有的测试类型

- **单元测试**：source canonicalization、freshness ranking、claim verifier、citation gate 逻辑
- **接口/契约测试**：OpenAPI schema 关键字段存在；chat SSE 事件序列满足约定；sessions 恢复 deep artifacts
- **回归 runner**：golden queries 输出 JSON（包含 sources/claims/quality），可 diff/统计

### 6.2 验收指标（示例，可配置）

- 对时间敏感 query：`freshness_ratio_30d >= X`（否则触发提示/补检索）
- 最终报告：`citation_coverage >= Y`
- claim verifier：关键 claim `unsupported/contradicted` 数量低于阈值，否则自动 revise

---

## 7. 风险与应对（Risks）

- **历史 lint 债务**：`ruff check .` 当前存在大量历史错误；本轮不追求全量清零，以“新增代码无新增 lint 债 + 关键文件逐步收敛 + tests/contract tests 为门禁”为策略。
- **流式协议迁移风险**：新增 `/api/chat/sse` 并保留旧端点，前端支持开关与回滚；避免一次性切换导致线上不可用。
- **许可证风险**：默认重写实现；若确需移植，仅限 MIT/Apache-2.0/BSD，且保留必要 notices。

---

## 8. 里程碑（Milestones）

1) OpenAPI schema 稳定化 + TS types 生成流水线  
2) Chat 标准 SSE 端点落地 + 前端迁移  
3) Source registry + citation gate + claim verifier 上线（带可视化 + 可配置阈值）  
4) Benchmark / golden regression runner + CI gate  

