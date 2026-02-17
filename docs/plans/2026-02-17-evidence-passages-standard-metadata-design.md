# Evidence Passages (Standard Metadata) + Render Auto Heuristics — Design

**Date:** 2026-02-17  
**Owner:** Codex + Luke  

## Goal
在不推翻现有 FastAPI + DeepSearch 架构的前提下：

1) 提升 Render `auto` 的命中率（识别 Cloudflare / 人机验证 / JS challenge 等 interstitial 页面并自动走 Playwright crawler）。  
2) 显著提升证据 passages 的可读性与可追溯性：每个 passage 携带 “所在章节标题” + “页面标题” + “抓取时间” + “抓取方式”，以便前端更好展示/折叠/引用。

## Non-goals
- 不引入新的独立 evidence 端点；继续以 `GET /api/sessions/{thread_id}/evidence` 为主合同。
- 不做全文去噪/抽取算法大升级（boilerplate removal / readability 之类留到后续）。
- 不改变 `passages.text` 的 offsets 语义：`start_char/end_char` 仍相对于 “用于分段的文本”（优先 markdown，其次 plain text）。

## Contract (OpenAPI is source of truth)

### EvidencePassageItem schema changes
在 `EvidencePassageItem` 中新增可选字段（Standard 字段包）：
- `heading?: str | null` — passage 所在章节标题（来自 markdown headings）
- `page_title?: str | null` — 页面标题（来自抓取 `<title>` / `<h1>`）
- `retrieved_at?: str | null` — 抓取时间（ISO 8601）
- `method?: str | null` — 抓取方式（`direct_http` / `render_crawler` / `reader_public` / `reader_self_hosted` 等）

保持兼容：旧前端仍可只读 `url/text/start_char/end_char`。

### Evidence endpoint
`GET /api/sessions/{thread_id}/evidence` 返回的 `passages[]` 将包含上述字段（尽量填充；无值则省略或为 null）。

## Data Flow

### 1) Fetch → FetchedPage
- `ContentFetcher.fetch_many()` 抓取页面并输出 `FetchedPage`（含 `title/retrieved_at/method/markdown/text`）。

### 2) FetchedPage → Passages
- 分段输入：优先使用 `page.markdown`，fallback `page.text`。
- `split_into_passages()` 输出 passages + offsets。
- markdown 输入时额外输出 `heading`（取 “该 passage 起始位置最近的 markdown heading”）。
- DeepSearch evidence builder enrich 每个 passage：
  - `page_title = page.title`
  - `retrieved_at = page.retrieved_at`
  - `method = page.method`

### 3) Session artifacts → Evidence API
DeepSearch 将 `passages` 写入 `deepsearch_artifacts`，Evidence endpoint 原样读出并通过 response_model 暴露给前端。

## Render `auto` heuristics
在 `research_fetch_render_mode=auto` 下：
- 若直抓得到的文本看起来像 interstitial（而非正文），即使长度超过 `RESEARCH_FETCH_RENDER_MIN_CHARS` 也触发 render crawler。
- 初期规则以 “低误伤” 为原则：只匹配高置信模板文案（Cloudflare / captcha / JS challenge / access denied）。

## Testing / Verification
- 单测离线运行（monkeypatch crawler / requests）。
- 新增 coverage：
  - headings 提取 + offsets 稳定
  - deepsearch passages enrichment（heading/page_title/retrieved_at/method）
  - OpenAPI contract 包含新字段；TS types 同步更新
  - Render `auto` 对主流 interstitial 模板触发 crawler

