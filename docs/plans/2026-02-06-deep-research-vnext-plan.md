# Deep Research VNext Implementation Plan (20 Tasks)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 对标最新主流 Deep Research 开源实现，补齐 Weaver 在“检索质量、证据可追溯、评测闭环、稳定性与可运营性”上的关键缺口，并严格执行“每完成 2 个任务 commit 一次”。

**Architecture:** 保持现有 FastAPI + LangGraph + Next.js 架构不变，优先做小步、可回滚、可测试的增量改造。核心策略是先打通 deepsearch 新执行入口，再增强检索/引用质量，最后补评测与前端可视化。

**Tech Stack:** Python 3.11+, FastAPI, LangGraph/LangChain, pytest, ruff, GitHub Actions, Next.js 14, pnpm.

**Reference Baseline (2026-02-06):**
- LangChain open_deep_research
- GPT-Researcher
- ByteDance DeerFlow
- SkyworkAI DeepResearchAgent
- Alibaba-NLP DeepResearch Bench

---

## Baseline Setup (pre-task)

- Create branch:
  - `git checkout -b codex/deep-research-vnext-20260206`
- Install deps:
  - `make setup && make web-install`
- Baseline verify:
  - `make lint && make test && pnpm -C web lint && pnpm -C web build`

---

### Task 1: Wire DeepSearch Entry to Auto Selector

**Files:**
- Modify: `agent/workflows/nodes.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Test: `tests/test_deepsearch_mode_selection.py`

**Steps:**
1. RED: 新增测试，断言 deepsearch 节点优先走 auto selector，而不是固定 `run_deepsearch`。
2. Run: `pytest -q tests/test_deepsearch_mode_selection.py`（预期 FAIL）。
3. GREEN: 在 `deepsearch_node` 中切换到 `run_deepsearch_auto`，保留异常处理语义。
4. Run: `pytest -q tests/test_deepsearch_mode_selection.py`（预期 PASS）。

---

### Task 2: Add Runtime Deep Mode Override (`auto|tree|linear`)

**Files:**
- Modify: `common/config.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Modify: `README.md`
- Test: `tests/test_settings_parsing.py`

**Steps:**
1. RED: 新增配置解析测试，覆盖 `DEEPSEARCH_MODE=auto|tree|linear`。
2. Run: `pytest -q tests/test_settings_parsing.py -k deepsearch_mode`（预期 FAIL）。
3. GREEN: 在配置层和 `run_deepsearch_auto` 中实现优先级（请求级 override > env 配置 > 默认值）。
4. Run: `pytest -q tests/test_settings_parsing.py -k deepsearch_mode`（预期 PASS）。
5. Commit (Task 1+2):
   - `git add agent/workflows/nodes.py agent/workflows/deepsearch_optimized.py common/config.py tests/test_deepsearch_mode_selection.py tests/test_settings_parsing.py README.md`
   - `git commit -m "feat: route deepsearch through auto/tree/linear mode selector"`

---

### Task 3: Switch DeepSearch Retrieval to MultiSearch Orchestrator

**Files:**
- Modify: `agent/workflows/deepsearch.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_deepsearch_multi_search.py`

**Steps:**
1. RED: 新增测试，断言 deepsearch 不再直接调用 Tavily 单源路径。
2. Run: `pytest -q tests/test_deepsearch_multi_search.py`（预期 FAIL）。
3. GREEN: 接入 `multi_search()`，支持按 strategy 拉取并回填标准结果结构。
4. Run: `pytest -q tests/test_deepsearch_multi_search.py`（预期 PASS）。

---

### Task 4: Add Freshness-Aware Ranking for Time-Sensitive Queries

**Files:**
- Modify: `tools/search/multi_search.py`
- Modify: `common/config.py`
- Test: `tests/test_multi_search_ranking.py`

**Steps:**
1. RED: 新增测试，验证 `published_date` 对排序有时效衰减影响。
2. Run: `pytest -q tests/test_multi_search_ranking.py`（预期 FAIL）。
3. GREEN: 增加 freshness score（可配置半衰期）并与相关性融合排序。
4. Run: `pytest -q tests/test_multi_search_ranking.py`（预期 PASS）。
5. Commit (Task 3+4):
   - `git add agent/workflows/deepsearch.py agent/workflows/deepsearch_optimized.py tools/search/multi_search.py common/config.py tests/test_deepsearch_multi_search.py tests/test_multi_search_ranking.py`
   - `git commit -m "feat: adopt multi-search and freshness-aware ranking"`

---

### Task 5: Domain-Aware Provider Profile Routing

**Files:**
- Modify: `agent/workflows/domain_router.py`
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_multi_search_profiles.py`

**Steps:**
1. RED: 新增测试，验证 academic/news/general 走不同 provider 子集。
2. Run: `pytest -q tests/test_multi_search_profiles.py`（预期 FAIL）。
3. GREEN: 把 domain router 的 `suggested_sources` 映射为 provider profile 并在 multi-search 执行层生效。
4. Run: `pytest -q tests/test_multi_search_profiles.py`（预期 PASS）。

---

### Task 6: Add Retry + Circuit Breaker for Search Providers

**Files:**
- Create: `tools/search/reliability.py`
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_multi_search_reliability.py`

**Steps:**
1. RED: 新增测试，覆盖瞬时失败重试与连续失败熔断恢复。
2. Run: `pytest -q tests/test_multi_search_reliability.py`（预期 FAIL）。
3. GREEN: 抽象 provider 调用包装器，统一超时、退避、熔断状态。
4. Run: `pytest -q tests/test_multi_search_reliability.py`（预期 PASS）。
5. Commit (Task 5+6):
   - `git add agent/workflows/domain_router.py tools/search/multi_search.py tools/search/reliability.py tests/test_multi_search_profiles.py tests/test_multi_search_reliability.py`
   - `git commit -m "feat: domain-aware provider profiles and search reliability guardrails"`

---

### Task 7: Introduce Canonical Source Registry

**Files:**
- Create: `agent/workflows/source_registry.py`
- Modify: `agent/workflows/result_aggregator.py`
- Test: `tests/test_source_registry.py`

**Steps:**
1. RED: 新增测试，验证 URL 规范化（scheme、tracking params、尾斜杠）后可稳定去重。
2. Run: `pytest -q tests/test_source_registry.py`（预期 FAIL）。
3. GREEN: 在聚合阶段引入统一 source registry，生成稳定 source_id。
4. Run: `pytest -q tests/test_source_registry.py`（预期 PASS）。

---

### Task 8: Enforce Citation Gate Before Final Report

**Files:**
- Modify: `agent/workflows/nodes.py`
- Modify: `agent/workflows/quality_assessor.py`
- Test: `tests/test_report_citation_gate.py`

**Steps:**
1. RED: 新增测试，断言低引用覆盖率时不直接完成流程，而进入 revise/research 分支。
2. Run: `pytest -q tests/test_report_citation_gate.py`（预期 FAIL）。
3. GREEN: 在 evaluator 路径加入 citation gate（阈值可配置）。
4. Run: `pytest -q tests/test_report_citation_gate.py`（预期 PASS）。
5. Commit (Task 7+8):
   - `git add agent/workflows/source_registry.py agent/workflows/result_aggregator.py agent/workflows/nodes.py agent/workflows/quality_assessor.py tests/test_source_registry.py tests/test_report_citation_gate.py`
   - `git commit -m "feat: canonical source registry and citation quality gate"`

---

### Task 9: Add Claim Verifier Against Collected Evidence

**Files:**
- Create: `agent/workflows/claim_verifier.py`
- Modify: `agent/workflows/quality_assessor.py`
- Test: `tests/test_claim_verifier.py`

**Steps:**
1. RED: 新增测试，覆盖“有主张但无证据”与“证据冲突”两类判定。
2. Run: `pytest -q tests/test_claim_verifier.py`（预期 FAIL）。
3. GREEN: 实现 claim-to-evidence 匹配，输出 verified/contradicted/unsupported。
4. Run: `pytest -q tests/test_claim_verifier.py`（预期 PASS）。

---

### Task 10: Feed Quality Signals Back to Coordinator

**Files:**
- Modify: `agent/workflows/agents/coordinator.py`
- Modify: `agent/workflows/nodes.py`
- Test: `tests/test_coordinator_quality_loop.py`

**Steps:**
1. RED: 新增测试，断言低质量评分会触发 `plan/research`，高质量评分才 `complete`。
2. Run: `pytest -q tests/test_coordinator_quality_loop.py`（预期 FAIL）。
3. GREEN: 将质量评分、缺口数、引用准确率作为协调器输入信号。
4. Run: `pytest -q tests/test_coordinator_quality_loop.py`（预期 PASS）。
5. Commit (Task 9+10):
   - `git add agent/workflows/claim_verifier.py agent/workflows/quality_assessor.py agent/workflows/agents/coordinator.py agent/workflows/nodes.py tests/test_claim_verifier.py tests/test_coordinator_quality_loop.py`
   - `git commit -m "feat: add evidence-based claim verification and coordinator quality feedback"`

---

### Task 11: Add Token and Time Budgets to DeepSearch Loop

**Files:**
- Modify: `common/config.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Test: `tests/test_deepsearch_budget_guard.py`

**Steps:**
1. RED: 新增测试，覆盖 token/time 超限时提前收敛并给出可解释终止原因。
2. Run: `pytest -q tests/test_deepsearch_budget_guard.py`（预期 FAIL）。
3. GREEN: 引入 `deepsearch_max_seconds`、`deepsearch_max_tokens` guardrail。
4. Run: `pytest -q tests/test_deepsearch_budget_guard.py`（预期 PASS）。

---

### Task 12: Add Session-Level Search Cache with TTL

**Files:**
- Modify: `agent/core/search_cache.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_search_cache_ttl.py`

**Steps:**
1. RED: 新增测试，验证同查询命中缓存、TTL 过期后重查。
2. Run: `pytest -q tests/test_search_cache_ttl.py`（预期 FAIL）。
3. GREEN: 在 deepsearch + multi-search 打通缓存层并记录命中率。
4. Run: `pytest -q tests/test_search_cache_ttl.py`（预期 PASS）。
5. Commit (Task 11+12):
   - `git add common/config.py agent/core/search_cache.py agent/workflows/deepsearch_optimized.py tools/search/multi_search.py tests/test_deepsearch_budget_guard.py tests/test_search_cache_ttl.py`
   - `git commit -m "feat: add deepsearch budget guards and session-level query cache"`

---

### Task 13: Persist Deep Research Artifacts in Session Metadata

**Files:**
- Modify: `common/session_manager.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Test: `tests/test_session_deepsearch_artifacts.py`

**Steps:**
1. RED: 新增测试，断言会话可保存 research_tree、queries、quality summary。
2. Run: `pytest -q tests/test_session_deepsearch_artifacts.py`（预期 FAIL）。
3. GREEN: 在 session snapshot 中持久化深研关键结构化产物。
4. Run: `pytest -q tests/test_session_deepsearch_artifacts.py`（预期 PASS）。

---

### Task 14: Resume Deep Research from Saved Artifact State

**Files:**
- Modify: `main.py`
- Modify: `common/session_manager.py`
- Test: `tests/test_resume_session_deepsearch.py`

**Steps:**
1. RED: 新增接口测试，验证从中断点恢复后可继续而非重跑全量流程。
2. Run: `pytest -q tests/test_resume_session_deepsearch.py`（预期 FAIL）。
3. GREEN: 在 `/api/sessions/{thread_id}/resume` 增加 deepsearch artifact 恢复逻辑。
4. Run: `pytest -q tests/test_resume_session_deepsearch.py`（预期 PASS）。
5. Commit (Task 13+14):
   - `git add common/session_manager.py agent/workflows/deepsearch_optimized.py main.py tests/test_session_deepsearch_artifacts.py tests/test_resume_session_deepsearch.py`
   - `git commit -m "feat: persist and resume deep-research artifact state"`

---

### Task 15: Create Benchmark Loader for Deep Research Bench Style Data

**Files:**
- Create: `eval/benchmarks/deep_research_bench_loader.py`
- Create: `eval/benchmarks/sample_tasks.jsonl`
- Test: `tests/test_benchmark_loader.py`

**Steps:**
1. RED: 新增测试，验证 benchmark 样例可解析为统一任务模型。
2. Run: `pytest -q tests/test_benchmark_loader.py`（预期 FAIL）。
3. GREEN: 实现 JSONL loader 与 schema 校验（query, constraints, expected_fields）。
4. Run: `pytest -q tests/test_benchmark_loader.py`（预期 PASS）。

---

### Task 16: Add Reproducible Golden Regression Runner

**Files:**
- Create: `scripts/benchmark_deep_research.py`
- Create: `eval/golden_queries.json`
- Test: `tests/test_deepsearch_golden_smoke.py`

**Steps:**
1. RED: 新增测试，验证 benchmark 脚本支持 `--max-cases`、`--mode`、`--output` 参数。
2. Run: `pytest -q tests/test_deepsearch_golden_smoke.py`（预期 FAIL）。
3. GREEN: 实现最小可运行回归脚本，输出可比对 JSON 报告。
4. Run: `pytest -q tests/test_deepsearch_golden_smoke.py`（预期 PASS）。
5. Commit (Task 15+16):
   - `git add eval/benchmarks/deep_research_bench_loader.py eval/benchmarks/sample_tasks.jsonl scripts/benchmark_deep_research.py eval/golden_queries.json tests/test_benchmark_loader.py tests/test_deepsearch_golden_smoke.py`
   - `git commit -m "feat: add benchmark loader and golden regression runner"`

---

### Task 17: Add Nightly Benchmark Workflow

**Files:**
- Create: `.github/workflows/benchmark-nightly.yml`
- Modify: `.github/workflows/ci.yml`

**Steps:**
1. 新增 nightly workflow，运行小规模 benchmark 并上传 artifact。
2. 在主 CI 中新增手动触发 smoke benchmark（不阻塞 PR）。
3. Verify: `python scripts/benchmark_deep_research.py --max-cases 3 --mode auto --output /tmp/bench.json`.

---

### Task 18: Surface Quality Metrics in Frontend Progress Dashboard

**Files:**
- Modify: `web/components/visualization/ProgressDashboard.tsx`
- Modify: `web/hooks/useResearchProgress.ts`
- Modify: `web/types/chat.ts`
- Create: `web/components/visualization/QualityBadge.tsx`

**Steps:**
1. 新增质量指标展示（coverage、citation、consistency）。
2. 将后端流式事件字段映射到前端状态与可视化组件。
3. Verify: `pnpm -C web lint && pnpm -C web build`.
4. Commit (Task 17+18):
   - `git add .github/workflows/benchmark-nightly.yml .github/workflows/ci.yml web/components/visualization/ProgressDashboard.tsx web/hooks/useResearchProgress.ts web/types/chat.ts web/components/visualization/QualityBadge.tsx`
   - `git commit -m "feat: add benchmark workflows and frontend quality dashboard"`

---

### Task 19: Add Source Inspector Panel for Citation Drill-Down

**Files:**
- Create: `web/components/chat/message/SourceInspector.tsx`
- Modify: `web/components/chat/MessageItem.tsx`
- Modify: `web/lib/storage-service.ts`

**Steps:**
1. 增加来源明细面板（domain、freshness、provider、raw url）。
2. 在消息引用处增加点击跳转与来源过滤。
3. Verify: `pnpm -C web lint && pnpm -C web build`.

---

### Task 20: Update Docs + Rollout Guide + Troubleshooting

**Files:**
- Modify: `README.md`
- Modify: `docs/README.en.md`
- Create: `docs/deep-research-rollout.md`
- Create: `docs/benchmarks/README.md`

**Steps:**
1. 更新 deep research 新模式、配置项、benchmark 使用手册。
2. 增加“常见问题 + 回滚开关”说明（deep mode / cache / citation gate）。
3. Verify: `git diff --check`.
4. Commit (Task 19+20):
   - `git add web/components/chat/message/SourceInspector.tsx web/components/chat/MessageItem.tsx web/lib/storage-service.ts README.md docs/README.en.md docs/deep-research-rollout.md docs/benchmarks/README.md`
   - `git commit -m "docs+ui: add source inspector and deep-research rollout playbook"`

---

## Commit Cadence Rule (Mandatory)

- 仅在完成偶数任务后提交：`2, 4, 6, 8, 10, 12, 14, 16, 18, 20`
- 每次提交必须包含前两个任务的测试与实现，不允许“代码先行、测试滞后”。

## Verification Gate (Before claiming done)

- Backend:
  - `make lint`
  - `make test`
- Frontend:
  - `pnpm -C web lint`
  - `pnpm -C web build`
- Benchmark smoke:
  - `python scripts/benchmark_deep_research.py --max-cases 3 --mode auto --output /tmp/bench.json`
