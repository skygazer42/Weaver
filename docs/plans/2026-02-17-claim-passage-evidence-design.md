# Claim→Passage Evidence Linking (VNext) — Design

**Date:** 2026-02-17  
**Owner:** Codex (with human review checkpoints)

## Context

Weaver 已经具备：
- evidence endpoint：`GET /api/sessions/{thread_id}/evidence`（sources/claims/quality_summary/fetched_pages/passages）
- passages：基于 research fetcher 抓取网页正文并切分（含 `heading_path`、`quote`、`snippet_hash` 等元数据）
- claim verifier：当前只在 *search results snippets* 上做“claim↔evidence”匹配（URL 级别），无法指向具体段落

现状问题：
- 前端/评测侧难以“复核某个 claim 到底被哪一段证据支持/反驳”
- 仅 URL 级别 evidence 不够细粒度，冲突与支持都难定位

## Goal

在 **不引入额外 LLM 成本** 的前提下，把 claim verifier 的 evidence 从 URL 级别提升到 **passage 级别**：

- 对每条 claim：
  - 仍保留 `evidence_urls`（兼容现有逻辑与 UI）
  - 新增 `evidence_passages[]`，包含可定位的 `snippet_hash` + `quote`（以及可选的 `heading_path`）
- 让前端可以：
  - 展示 claim 的 verified/unsupported/contradicted
  - 点击/复制 passage quote，快速复核

## Non-goals

- 不在本轮强制“报告自动插引用标记”
- 不做基于 embedding 的语义检索（先用 deterministic overlap，稳定/便宜）
- 不改变 deepsearch 的主流程和接口语义（仅补充 artifacts）

## Proposed Data Model

### Backend internal (ClaimVerifier)

`ClaimCheck` 新增：
- `evidence_passages: list[dict]`（最多 N 条，默认 3）

单条 evidence passage：
- `url: str`
- `snippet_hash: str | \"\"`（优先用于定位）
- `quote: str | \"\"`（面向 UI 的短摘录）
- `heading_path: list[str] | None`（可选）

### API (Evidence endpoint)

`EvidenceClaim` 在 OpenAPI 中新增可选字段：
- `evidence_passages: EvidenceClaimEvidence[] = []`

并定义：
- `EvidenceClaimEvidence { url, snippet_hash?, quote?, heading_path? }`

## Algorithm (Deterministic, Passage-first)

当 `passages` 可用且开启开关时：

1. 对每个 claim 做 tokenization（沿用现有规则，含中英文与数字）
2. 对每个 passage text 做 tokenization（同规则）
3. 计算 overlap = |claim_tokens ∩ passage_tokens|
4. overlap ≥ `min_overlap_tokens` 认为“候选证据”
5. 基于现有 `_is_contradiction` 规则分类：
   - contradiction → contradicted candidates
   - else → supported candidates
6. 选择 top-N（按 overlap 降序）作为 `evidence_passages`
7. `evidence_urls` 仍由 top candidates 的 canonical URLs 组成并去重

当 passages 不可用：
- 退回到现有的 search snippets evidence（保持兼容）

## Config

新增可配置项（Settings + `.env.example`）：
- `DEEPSEARCH_CLAIM_VERIFIER_USE_PASSAGES`（default: true）
- `DEEPSEARCH_CLAIM_VERIFIER_MIN_OVERLAP_TOKENS`（default: 2）
- `DEEPSEARCH_CLAIM_VERIFIER_MAX_EVIDENCE_PER_CLAIM`（default: 3）

## Testing / Acceptance

- 单测：`ClaimVerifier.verify_report(..., passages=...)` 会产出 `evidence_passages`（含 snippet_hash）
- deepsearch 集成：生成 artifacts 时将 passages 传入 claim verifier
- OpenAPI contract：evidence endpoint schema 包含 `evidence_passages`
- 前端类型：运行 `pnpm -C web api:types` 后 `web/lib/api-types.ts` 对齐

