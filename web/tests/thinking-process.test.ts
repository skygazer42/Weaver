import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { normalizeThinkingProcess } from '../lib/thinkingProcess'
import { ThinkingProcess } from '../components/chat/message/ThinkingProcess'
import { I18nProvider } from '../lib/i18n/i18n-context'
import { translations } from '../lib/i18n/translations'
import type { Artifact, ProcessEvent, ToolInvocation } from '../types/chat'

const event = (id: string, type: string, data: Record<string, unknown>, timestamp: number): ProcessEvent => ({
  id,
  type,
  data,
  timestamp,
})

const tool = (toolName: string, toolCallId: string, args: Record<string, unknown> = {}): ToolInvocation => ({
  toolName,
  toolCallId,
  args,
  state: 'completed',
})

test('normalizes noisy research events into user-facing steps', () => {
  const events: ProcessEvent[] = [
    ...Array.from({ length: 4 }, (_, index) => event(`unknown-${index}`, 'tool', {
      name: 'unknown',
      status: 'completed',
    }, index)),
    event('status-init', 'status', { text: 'Initializing research agent...' }, 10),
    event('status-running', 'status', { text: 'Running agent (tool-calling)...' }, 11),
    event('thinking-1', 'thinking', { text: '先确认问题范围，再查找一手资料。' }, 12),
    event('search-event', 'search', { query: 'latest quantum computing breakthroughs' }, 20),
    event('search-start', 'tool_start', {
      name: 'tavily_search',
      toolCallId: 'search-1',
      args: { query: ' latest   quantum computing breakthroughs ' },
    }, 21),
    event('search-result', 'tool_result', {
      name: 'tavily_search',
      toolCallId: 'search-1',
      args: {},
    }, 22),
    event('search-empty', 'tool_start', {
      name: 'tavily_search',
      toolCallId: 'search-2',
      args: {},
    }, 23),
    ...Array.from({ length: 6 }, (_, index) => event(`crawl-start-${index}`, 'tool_start', {
      name: 'crawl_urls',
      toolCallId: `crawl-${index}`,
      args: {},
    }, 30 + index)),
    ...Array.from({ length: 6 }, (_, index) => event(`crawl-result-${index}`, 'tool_result', {
      name: 'crawl_urls',
      toolCallId: `crawl-${index}`,
      args: {},
    }, 40 + index)),
  ]

  const tools: ToolInvocation[] = [
    ...Array.from({ length: 4 }, (_, index) => tool('unknown', `unknown-tool-${index}`)),
    tool('tavily_search', 'search-tool-1', { query: 'latest quantum computing breakthroughs' }),
    tool('tavily_search', 'search-tool-empty'),
    ...Array.from({ length: 6 }, (_, index) => tool('crawl_urls', `crawl-${index}`)),
    tool('execute_code', 'artifact-tool'),
  ]

  const artifacts: Artifact[] = [{
    id: 'artifact-1',
    type: 'report',
    title: 'Research report',
    content: 'A readable report preview.',
    download_url: '/api/artifacts/report-1',
    tool_call_id: 'artifact-tool',
    createdAt: 1,
    updatedAt: 1,
  }]

  const normalized = normalizeThinkingProcess({ events, tools, artifacts })
  const serialized = JSON.stringify(normalized)

  assert.doesNotMatch(serialized, /tavily_search|crawl_urls|unknown|tool-calling/)
  assert.deepEqual(
    normalized.steps.filter((step) => step.kind === 'search').map((step) => step.query),
    ['latest quantum computing breakthroughs'],
  )
  assert.deepEqual(normalized.steps.filter((step) => step.kind === 'reading').map((step) => step.count), [6])
  assert.equal(normalized.steps.filter((step) => step.kind === 'artifact')[0]?.downloadUrl, '/api/artifacts/report-1')
  assert.equal(normalized.stepCount, normalized.steps.length)
  assert.equal(normalized.stepCount, 4)
})

test('recovers queries and page inputs across tool lifecycle events without duplicate steps', () => {
  const result = normalizeThinkingProcess({
    events: [
      event('empty-search', 'tool_start', { name: 'serper_search', toolCallId: 'search-1' }, 1),
      event('query-search', 'tool_result', { name: 'serper_search', toolCallId: 'search-1', args: { query: 'Evidence   review' } }, 2),
      event('same-query', 'search', { query: ' evidence review ' }, 3),
      event('anonymous-query', 'tool_start', { name: 'brave_search', args: { query: 'Second query' } }, 4),
      event('page-start', 'tool_start', { name: 'fetch_url', toolCallId: 'page-1', args: { url: 'https://www.example.com/research/' } }, 5),
      event('page-result', 'tool_result', { name: 'fetch_url', toolCallId: 'page-1' }, 6),
      event('same-page', 'screenshot', { page_url: 'https://example.com/research?utm_source=search#summary' }, 7),
    ],
    tools: [tool('serper_search', 'search-1'), tool('brave_search', 'search-2')],
  })

  assert.deepEqual(result.steps.filter((step) => step.kind === 'search').map((step) => step.query), ['Evidence review', 'Second query'])
  assert.deepEqual(result.steps.filter((step) => step.kind === 'reading').map((step) => step.page), ['example.com/research'])
})

test('counts anonymous empty page calls once per start/result pair', () => {
  const result = normalizeThinkingProcess({ events: [
    ...Array.from({ length: 6 }, (_, index) => event(`start-${index}`, 'tool_start', { name: 'crawl_urls' }, index)),
    ...Array.from({ length: 6 }, (_, index) => event(`result-${index}`, 'tool_result', { name: 'crawl_urls' }, index + 6)),
  ] })
  assert.deepEqual(result.steps.map(({ kind, count }) => ({ kind, count })), [{ kind: 'reading', count: 6 }])
  assert.equal(result.stepCount, 1)
})

test('does not count empty completion events or saved inputs as extra page reads', () => {
  const result = normalizeThinkingProcess({
    events: [
      event('start', 'tool_start', { tool: 'fetch_url', args: { url: 'https://example.org/evidence' } }, 1),
      event('result', 'tool_result', { tool: 'fetch_url', result: 'Read successfully' }, 2),
    ],
    tools: [tool('fetch_url', 'page-1')],
  })
  assert.deepEqual(result.steps.map(({ kind, page, count }) => ({ kind, page, count })), [
    { kind: 'reading', page: 'example.org/evidence', count: undefined },
  ])
})

test('keeps the three most recent distinct thoughts and meaningful milestones', () => {
  const result = normalizeThinkingProcess({ events: [
    ...['First thought', 'Second thought', 'Third thought', 'Fourth thought', ' First   thought '].map((text, index) => event(`thought-${index}`, 'thinking', { text }, index)),
    event('node', 'research_node_start', { nodeId: 'internal-node-123', epoch: 8, depth: 3, topic: 'Battery research' }, 10),
    event('node-complete', 'research_node_complete', { node_id: 'internal-node-123', summary: 'Compared primary sources.' }, 11),
    event('quality', 'quality_update', { stage: 'post_review', epoch: 8, query_coverage_score: 0.87 }, 12),
    event('task', 'task_update', { id: 'internal-task-456', title: 'Write report', progress: 62 }, 13),
    event('status', 'status', { text: 'Reviewing source evidence.' }, 14),
    event('status-duplicate', 'status', { text: 'Reviewing source evidence.' }, 15),
  ] })
  assert.deepEqual(result.steps.filter((step) => step.kind === 'thinking').map((step) => step.text), ['Third thought', 'Fourth thought', 'First thought'])
  assert.equal(result.steps.find((step) => step.kind === 'quality')?.progress, 87)
  assert.equal(result.steps.find((step) => step.kind === 'task')?.progress, 62)
  assert.equal(result.steps.filter((step) => step.kind === 'status').length, 1)
  assert.doesNotMatch(JSON.stringify(result), /internal-node|internal-task|post_review|epoch|nodeId/)
})

test('keeps integer task percentages and replaces earlier updates with current progress', () => {
  const result = normalizeThinkingProcess({ events: [
    event('task-start', 'task_update', { task: { id: 'private-id', content: 'Compare sources', progress: 0, status: 'pending' } }, 1),
    event('task-progress', 'task_update', { task: { id: 'private-id', content: 'Compare sources', progress: 1, status: 'running' } }, 2),
    event('quality', 'quality_update', { query_coverage_score: 1 }, 3),
  ] })
  assert.equal(result.steps.filter((step) => step.kind === 'task').length, 1)
  assert.equal(result.steps.find((step) => step.kind === 'task')?.progress, 1)
  assert.equal(result.steps.find((step) => step.kind === 'task')?.state, 'running')
  assert.equal(result.steps.find((step) => step.kind === 'quality')?.progress, 100)
  assert.doesNotMatch(JSON.stringify(result), /private-id|task_update/)
})

test('has no detail steps when only engineering noise or empty search calls exist', () => {
  const result = normalizeThinkingProcess({
    events: [
      event('init', 'status', { text: 'Initializing research agent...' }, 1),
      event('run', 'status', { text: 'Running agent (tool-calling)...' }, 2),
      event('working', 'status', { text: 'Working…' }, 3),
      event('new-backend-event', 'engine_debug', { text: 'private details' }, 4),
      event('empty-search', 'search', {}, 5),
    ],
    tools: [tool('unknown', 'unknown-1'), tool('execute_code', 'code-1'), tool('tavily_search', 'search-1')],
  })
  assert.deepEqual(result, { steps: [], stepCount: 0 })
})

test('retains readable and downloadable artifacts while hiding raw tool results and JSON previews', () => {
  const base: Artifact = { id: 'preview', type: 'tool_output', title: 'Evidence summary', content: 'Compared three primary sources.', tool_call_id: 'call-1', createdAt: 1, updatedAt: 1 }
  const result = normalizeThinkingProcess({
    tools: [{ ...tool('execute_code', 'call-1'), result: 'Debug trace and private tool payload' }],
    artifacts: [
      base,
      { ...base, id: 'download-only', title: 'unknown', content: '{"tool":"execute_code"}', download_url: '/api/tool-artifacts/full-output' },
      { ...base, id: 'raw-json', content: '{"nodeId":"private"}' },
    ],
  })
  assert.equal(result.stepCount, 2)
  assert.equal(result.steps[0]?.summary, base.content)
  assert.equal(result.steps[1]?.title, undefined)
  assert.equal(result.steps[1]?.summary, undefined)
  assert.equal(result.steps[1]?.downloadUrl, '/api/tool-artifacts/full-output')
  assert.doesNotMatch(JSON.stringify(result), /Debug trace|execute_code|unknown|nodeId/)
})

test('renders a summary without a disclosure control when all details are hidden', () => {
  const html = renderToStaticMarkup(createElement(I18nProvider, null,
    createElement(ThinkingProcess, {
      tools: [tool('unknown', 'unknown-1')],
      metrics: { duration_ms: 5000 },
      isThinking: false,
    }),
  ))
  assert.match(html, /Thought for 5s/)
  assert.doesNotMatch(html, /aria-expanded|aria-controls|chevron|unknown|step/)
})

test('renders natural singular and plural step summaries and has complete translations', () => {
  for (const count of [1, 2]) {
    const html = renderToStaticMarkup(createElement(I18nProvider, null,
      createElement(ThinkingProcess, {
        events: Array.from({ length: count }, (_, index) => event(`search-${index}`, 'search', { query: `Research topic ${index}` }, index)),
        metrics: { duration_ms: 5000 },
        isThinking: false,
      }),
    ))
    assert.match(html, new RegExp(`Thought for 5s · ${count} step${count === 1 ? '' : 's'}`))
  }
  for (const language of ['en', 'zh', 'ja', 'ko'] as const) {
    assert.deepEqual(Object.keys(translations[language]), Object.keys(translations.en))
  }
})

