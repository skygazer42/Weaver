import type { Message, ProcessEvent } from '@/types/chat'

export interface ResearchNode {
  id: string
  topic: string
  depth: number
  parent_id: string | null
  children_ids: string[]
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped'
  findings_count: number
  sources_count: number
  summary_length: number
  summary_preview?: string
  sources?: string[]
  queries?: string[]
  relevance_score?: number
  epoch?: number
}

export interface ResearchTree {
  root_id: string | null
  max_depth: number
  max_branches: number
  total_nodes: number
  total_sources: number
  completed_nodes: number
  pending_nodes: number
  nodes: Record<string, ResearchNode>
}

interface ResearchQuality {
  query_coverage_score?: number
  freshness_summary?: { fresh_30_ratio?: number; known_count?: number }
  unique_domains?: number
  total_sources?: number
}

export interface StudioTelemetry {
  coveragePct?: number
  freshnessPct?: number
  uniqueDomains?: number
  totalSources?: number
  completedNodes?: number
  totalNodes?: number
}

export interface StudioSource {
  index: number
  title: string
  url: string
  domain: string
}

export interface StudioDomain {
  domain: string
  count: number
}

export type StudioTab = 'graph' | 'artifacts' | 'sources'

export function parseStudioSourceUrl(value: unknown): URL | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

function nodeEvents(events: ProcessEvent[]) {
  return events.filter(event => event.type === 'research_node_start' || event.type === 'research_node_complete')
}

function synthesizeTree(events: ProcessEvent[], topic: string): ResearchTree | null {
  const nodes = new Map<string, ResearchNode>()
  for (const { type, data } of nodeEvents(events)) {
    const id = data?.node_id ?? data?.nodeId
    if (typeof id !== 'string' || !id) continue

    const node: ResearchNode = nodes.get(id) ?? {
      id, topic: data.topic || topic || id, depth: 0, parent_id: null, children_ids: [],
      status: 'pending', findings_count: 0, sources_count: 0, summary_length: 0,
    }
    if (typeof data.epoch === 'number') node.epoch = data.epoch
    if (type === 'research_node_start') {
      node.topic = data.topic || node.topic
      node.depth = data.depth ?? node.depth
      node.parent_id = data.parent_id ?? null
      node.status = 'in_progress'
    } else {
      node.status = 'completed'
      node.summary_preview = data.summary
      node.summary_length = data.summary?.length ?? 0
      const sources: { url?: unknown }[] = Array.isArray(data.sources) ? data.sources : []
      node.sources = sources
        .map(source => parseStudioSourceUrl(source?.url)?.href)
        .filter((url): url is string => Boolean(url))
      node.sources_count = node.sources.length
    }
    nodes.set(id, node)
  }
  if (!nodes.size) return null

  const epochs = new Map([...nodes.values()].filter(node => node.epoch !== undefined).map(node => [node.epoch, node]))
  for (const { type, data } of events) {
    if (type !== 'search' || typeof data?.query !== 'string') continue
    const node = nodes.get(data.node_id) ?? epochs.get(data.epoch)
    if (node && !node.queries?.includes(data.query)) node.queries = [...(node.queries ?? []), data.query]
  }

  const entries = [...nodes.values()]
  const roots: ResearchNode[] = []
  for (const node of entries) {
    const parent = node.parent_id === null ? undefined : nodes.get(node.parent_id)
    if (parent && parent !== node) parent.children_ids.push(node.id)
    else roots.push(node)
  }
  const completed = entries.filter(node => node.status === 'completed').length
  const totalSources = new Set(entries.flatMap(node => node.sources ?? [])).size
  let root = roots[0] ?? entries[0]
  if (roots.length > 1 || (root.epoch !== undefined && root.parent_id !== null)) {
    let id = 'research-root'
    while (nodes.has(id)) id += '-root'
    root = {
      id, topic: topic || root.topic, depth: 0, parent_id: null, children_ids: roots.map(node => node.id),
      status: completed === entries.length ? 'completed' : 'in_progress',
      findings_count: 0, sources_count: 0, summary_length: 0,
    }
    for (const child of roots) child.parent_id = id
    nodes.set(id, root)
  }

  return {
    root_id: root.id,
    max_depth: Math.max(...entries.map(node => node.depth)),
    max_branches: Math.max(...[...nodes.values()].map(node => node.children_ids.length)),
    total_nodes: entries.length,
    total_sources: totalSources,
    completed_nodes: completed,
    pending_nodes: entries.length - completed,
    nodes: Object.fromEntries(nodes),
  }
}

function percent(value: number | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(Math.min(1, Math.max(0, value)) * 100) : undefined
}

export function extractResearchStudio(messages: readonly Message[]) {
  const assistants = messages.filter(message => message.role === 'assistant')
  const latestAssistant = assistants.at(-1)
  const sources = new Map<string, StudioSource>()
  const addSource = (value: unknown, title?: string) => {
    const url = parseStudioSourceUrl(value)
    if (!url) return
    const href = url.href
    url.hash = ''
    url.pathname = url.pathname.replace(/\/+$/, '')
    const previous = sources.get(url.href)
    if (previous) {
      if (!previous.title && title) previous.title = title
    } else {
      sources.set(url.href, { index: sources.size + 1, title: title || '', url: href, domain: url.hostname.replace(/^www\./, '') })
    }
  }
  for (const message of assistants) {
    for (const source of message.sources ?? []) addSource(source.url, source.title)
  }

  let tree: ResearchTree | null = null
  let researchRun: Message | undefined
  for (let index = assistants.length - 1; index >= 0; index--) {
    const message = assistants[index]
    const events = message.processEvents ?? []
    const snapshot = events.findLast(event => event.type === 'research_tree_update' && event.data?.tree?.nodes)
    if (snapshot && Object.keys(snapshot.data.tree.nodes).length) {
      tree = snapshot.data.tree
    } else if (nodeEvents(events).length) {
      const prompt = messages.slice(0, messages.indexOf(message)).findLast(entry => entry.role === 'user')
      tree = synthesizeTree(events, prompt?.content.trim() ?? '')
    }
    if (tree) {
      researchRun = message
      break
    }
  }

  for (const { type, data } of researchRun?.processEvents ?? []) {
    if (type === 'research_node_complete' && Array.isArray(data?.sources)) {
      for (const source of data.sources) addSource(source?.url, source?.title)
    }
  }
  for (const node of Object.values(tree?.nodes ?? {})) {
    for (const url of node.sources ?? []) addSource(url)
  }

  const quality: ResearchQuality = {}
  for (const { type, data } of (researchRun ?? latestAssistant)?.processEvents ?? []) {
    if (type === 'quality_update') Object.assign(quality, data)
    else if (type === 'research_tree_update' || type === 'research_node_complete') Object.assign(quality, data?.quality)
  }
  const domains = new Map<string, number>()
  for (const source of sources.values()) domains.set(source.domain, (domains.get(source.domain) ?? 0) + 1)
  const telemetry: StudioTelemetry = {
    coveragePct: percent(quality.query_coverage_score),
    freshnessPct: quality.freshness_summary?.known_count === 0 ? undefined : percent(quality.freshness_summary?.fresh_30_ratio),
    uniqueDomains: quality.unique_domains ?? (domains.size || undefined),
    totalSources: quality.total_sources ?? tree?.total_sources ?? (sources.size || undefined),
    completedNodes: tree?.completed_nodes,
    totalNodes: tree?.total_nodes,
  }
  const isResearchActive = Boolean(researchRun && researchRun === latestAssistant && researchRun.isStreaming
    && Object.values(tree?.nodes ?? {}).some(node => node.status === 'in_progress' || node.status === 'pending'))

  return {
    tree, telemetry, isResearchActive, researchId: researchRun?.id,
    artifacts: messages.flatMap(message => message.artifacts ?? []),
    sources: [...sources.values()],
    domains: [...domains].map(([domain, count]) => ({ domain, count }))
      .sort((a, b) => b.count - a.count || a.domain.localeCompare(b.domain)),
  }
}

export type ResearchStudioData = ReturnType<typeof extractResearchStudio>

export function filterStudioSources(sources: readonly StudioSource[], query: string, domain = '') {
  const search = query.trim().toLowerCase()
  const selected = domain.toLowerCase()
  return sources.filter(source => (!selected || source.domain === selected) &&
    (!search || [source.title, source.url, source.domain].some(value => value.toLowerCase().includes(search))))
}

export function resolveStudioTab(
  state: { hasTree: boolean; hasArtifacts: boolean; hasSources: boolean; isResearchActive: boolean },
  manualTab?: StudioTab,
): StudioTab {
  if (manualTab) return manualTab
  if (state.hasTree && state.isResearchActive) return 'graph'
  if (state.hasArtifacts) return 'artifacts'
  if (state.hasTree) return 'graph'
  return state.hasSources ? 'sources' : 'graph'
}

export function layoutResearchTree(tree: ResearchTree) {
  const cardWidth = 128
  const cardHeight = 84
  const horizontalGap = 12
  const verticalGap = 28
  const padding = 12
  const levels: ResearchNode[][] = []
  const visited = new Set<string>()
  const links: { from: string; to: string }[] = []
  const byParent = new Map<string, string[]>()

  for (const node of Object.values(tree.nodes)) {
    if (!node.parent_id) continue
    const siblings = byParent.get(node.parent_id) ?? []
    siblings.push(node.id)
    byParent.set(node.parent_id, siblings)
  }

  function visit(id: string, level: number, parent?: string) {
    if (visited.has(id) || !Object.hasOwn(tree.nodes, id)) return
    visited.add(id)
    const node = tree.nodes[id]
    if (parent) links.push({ from: parent, to: id })
    const row = levels[level] ??= []
    row.push(node)
    for (const child of node.children_ids) visit(child, level + 1, id)
    for (const child of byParent.get(id) ?? []) visit(child, level + 1, id)
  }

  if (tree.root_id) visit(tree.root_id, 0)
  for (const node of Object.values(tree.nodes)) {
    if (!node.parent_id || !Object.hasOwn(tree.nodes, node.parent_id)) visit(node.id, 0)
  }
  for (const id of Object.keys(tree.nodes)) visit(id, 0)

  const rowWidth = (count: number) => count * cardWidth + Math.max(0, count - 1) * horizontalGap
  const width = rowWidth(Math.max(1, ...levels.map(row => row.length))) + 2 * padding
  const height = Math.max(1, levels.length) * cardHeight + Math.max(0, levels.length - 1) * verticalGap + 2 * padding
  const position = new Map<string, { x: number; y: number }>()
  const nodes = levels.flatMap((row, depth) => row.map((node, index) => {
    const parent = row.length === 1 && node.parent_id ? position.get(node.parent_id) : undefined
    const x = parent?.x ?? (width - rowWidth(row.length)) / 2 + index * (cardWidth + horizontalGap)
    const y = padding + depth * (cardHeight + verticalGap)
    position.set(node.id, { x, y })
    return { node, x, y, width: cardWidth, height: cardHeight }
  }))
  const edges = links.map(({ from, to }) => {
    const parent = position.get(from)!
    const child = position.get(to)!
    const x1 = parent.x + cardWidth / 2
    const x2 = child.x + cardWidth / 2
    const y1 = parent.y + cardHeight
    const y2 = child.y
    const midY = (y1 + y2) / 2
    return { from, to, path: `M ${x1} ${y1} C ${x1} ${midY} ${x2} ${midY} ${x2} ${y2}` }
  })

  return { nodes, edges, width, height }
}
