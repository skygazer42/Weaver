import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ResearchStudioPanel } from '../components/chat/ResearchStudioPanel'
import { I18nProvider } from '../lib/i18n/i18n-context'
import { translations } from '../lib/i18n/translations'
import {
  extractResearchStudio, filterStudioSources, layoutResearchTree, resolveStudioTab,
  type ResearchNode, type ResearchTree, type StudioTab,
} from '../lib/researchStudio'
import type { Message } from '../types/chat'

const node = (id: string, parent_id: string | null, depth: number, extra: Partial<ResearchNode> = {}): ResearchNode => ({
  id, topic: `Topic ${id}`, parent_id, depth, children_ids: [], status: 'completed',
  findings_count: 1, sources_count: 0, summary_length: 0, ...extra,
})

const tree: ResearchTree = {
  root_id: 'root', max_depth: 2, max_branches: 2, total_nodes: 4, completed_nodes: 3, pending_nodes: 1, total_sources: 5,
  nodes: {
    root: node('root', null, 0, { children_ids: ['a', 'b'] }),
    a: node('a', 'root', 1, { children_ids: ['c'], status: 'in_progress', queries: ['battery prices'] }),
    b: node('b', 'root', 1),
    c: node('c', 'a', 2),
  },
}

const event = (type: string, data: unknown) => ({ id: type, type, timestamp: 1, data })
const assistant = (fields: Partial<Message> = {}): Message => ({ id: 'assistant', role: 'assistant', content: '', ...fields })
const prompt: Message = { id: 'user', role: 'user', content: 'Compare battery storage costs' }
const treeEvent = event('research_tree_update', { tree, quality: { query_coverage_score: 0.75, total_sources: 5 } })
const start = (id: string, epoch: number) => event('research_node_start', { node_id: id, parent_id: 'deepsearch', depth: 1, epoch, topic: prompt.content })

test('prefers the latest tree snapshot and merges later quality fields for that run', () => {
  const studio = extractResearchStudio([assistant({ processEvents: [treeEvent] }), prompt, assistant({ processEvents: [
    treeEvent, start('ignored', 1),
    event('quality_update', { query_coverage_score: 0.894, unique_domains: 4, freshness_summary: { fresh_30_ratio: 0.43, known_count: 3 } }),
  ] })])
  assert.equal(studio.tree, tree)
  assert.equal(studio.telemetry.coveragePct, 89)
  assert.equal(studio.telemetry.freshnessPct, 43)
  assert.equal(studio.telemetry.uniqueDomains, 4)
  assert.equal(studio.telemetry.totalSources, 5)
  assert.equal(studio.telemetry.completedNodes, 3)
  assert.equal(studio.telemetry.totalNodes, 4)
})

test('uses the current epoch run ahead of an older snapshot and groups epochs under the research topic', () => {
  const studio = extractResearchStudio([assistant({ processEvents: [treeEvent] }), prompt, assistant({ isStreaming: true, processEvents: [
    start('epoch-1', 1),
    event('research_node_complete', { node_id: 'epoch-1', summary: 'Matched two benchmarks.', sources: [{ title: 'Benchmark', url: 'https://example.org/paper' }] }),
    start('epoch-2', 2),
  ] })])
  const fallback = studio.tree!
  const root = fallback.nodes[fallback.root_id!]
  assert.equal(root.topic, prompt.content)
  assert.deepEqual(root.children_ids, ['epoch-1', 'epoch-2'])
  assert.equal(fallback.nodes['epoch-1'].status, 'completed')
  assert.equal(fallback.nodes['epoch-1'].summary_preview, 'Matched two benchmarks.')
  assert.deepEqual(fallback.nodes['epoch-1'].sources, ['https://example.org/paper'])
  assert.equal(fallback.nodes['epoch-2'].status, 'in_progress')
  assert.equal(studio.sources[0].title, 'Benchmark')
  assert.equal(studio.telemetry.totalNodes, 2)
  assert.equal(studio.telemetry.coveragePct, undefined)
})

test('lays out nodes deterministically with positive bounds, separated cards and cubic edges', () => {
  const layout = layoutResearchTree(tree)
  assert.deepEqual(layout, layoutResearchTree(tree))
  assert.ok(layout.width > 0 && layout.height > 0)
  for (const [index, card] of layout.nodes.entries()) {
    assert.ok([card.x, card.y, card.width, card.height].every(Number.isFinite))
    assert.ok(card.x >= 0 && card.y >= 0 && card.x + card.width <= layout.width && card.y + card.height <= layout.height)
    for (const other of layout.nodes.slice(index + 1)) {
      assert.ok(card.x + card.width <= other.x || other.x + other.width <= card.x || card.y + card.height <= other.y || other.y + other.height <= card.y)
    }
  }
  assert.deepEqual(new Set(layout.edges.map(({ from, to }) => `${from}:${to}`)), new Set(['root:a', 'root:b', 'a:c']))
  assert.ok(layout.edges.every(({ path }) => /^M [\d.]+ [\d.]+ C [\d.]+ [\d.]+ [\d.]+ [\d.]+ [\d.]+ [\d.]+$/.test(path)))
})

test('deduplicates HTTP sources across turns and preserves citation indices through filtering', () => {
  const studio = extractResearchStudio([
    assistant({ sources: [{ title: 'Storage Costs', url: 'https://www.example.org/costs' }] }),
    assistant({ sources: [
      { title: 'Duplicate', url: 'https://www.example.org/costs/#methodology' },
      { title: 'Quarterly Summary', url: 'https://example.org/2025' },
      { title: 'Capacity Outlook', url: 'https://energy.gov/outlook' },
      { title: 'Invalid', url: 'javascript:alert(1)' },
    ] }),
  ])
  assert.deepEqual(studio.domains, [{ domain: 'example.org', count: 2 }, { domain: 'energy.gov', count: 1 }])
  assert.deepEqual(filterStudioSources(studio.sources, 'STORAGE', 'EXAMPLE.ORG').map(source => source.index), [1])
  assert.deepEqual(filterStudioSources(studio.sources, 'example.org').map(source => source.index), [1, 2])
  assert.deepEqual(filterStudioSources(studio.sources, '2025').map(source => source.index), [2])
  assert.deepEqual(filterStudioSources(studio.sources, '', 'energy.gov').map(source => source.index), [3])
})

test('switches automatic defaults with current content and keeps explicit selection', () => {
  const state = { hasTree: true, hasArtifacts: false, hasSources: true, isResearchActive: true }
  assert.equal(resolveStudioTab(state), 'graph')
  assert.equal(resolveStudioTab({ ...state, hasArtifacts: true }), 'graph')
  assert.equal(resolveStudioTab({ ...state, hasArtifacts: true, isResearchActive: false }), 'artifacts')
  assert.equal(resolveStudioTab({ ...state, hasTree: false, isResearchActive: false }), 'sources')
  assert.equal(resolveStudioTab({ ...state, isResearchActive: false }), 'graph')
  assert.equal(resolveStudioTab(state, 'artifacts'), 'artifacts')
})

test('translates every Research Studio key in all four locales', () => {
  const keys = Object.keys(translations.en).filter(key => key.startsWith('studio'))
  assert.ok(keys.length >= 25)
  assert.deepEqual(Object.keys(translations), ['en', 'zh', 'ja', 'ko'])
  for (const table of Object.values(translations)) {
    for (const key of keys) assert.ok((table as Record<string, string>)[key]?.trim(), key)
  }
})

test('server-renders the graph, sources, and sandboxed artifacts in their respective tabs', () => {
  const studio = extractResearchStudio([assistant({
    processEvents: [treeEvent],
    sources: [{ title: 'Storage cost dataset', url: 'https://example.org/costs' }],
    artifacts: [{ id: 'report', type: 'report', title: 'Cost report.html', content: '<main>Cost report</main>', createdAt: 1, updatedAt: 1 }],
  })])

  const render = (activeTab: StudioTab) => renderToStaticMarkup(createElement(I18nProvider, null, createElement(ResearchStudioPanel, {
    studio, activeTab, onTabChange: () => {},
  })))

  const graph = render('graph')
  assert.match(graph, /Node inspector/)
  assert.match(graph, /Topic root/)
  assert.match(graph, /75%/)
  const sources = render('sources')
  assert.match(sources, /Storage cost dataset/)
  assert.match(sources, /target="_blank" rel="noopener noreferrer"/)
  const artifacts = render('artifacts')
  assert.match(artifacts, /Cost report\.html/)
  assert.match(artifacts, /sandbox="allow-scripts"/)
})
