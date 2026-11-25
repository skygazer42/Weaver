import type { Message, MessageSource, ProcessEvent } from '@/types/chat'
import { getArtifactDownloadUrl } from '@/lib/api'
import { translations, type Language as Locale } from '@/lib/i18n/translations'
import { escapeMarkup } from '@/lib/reportExport'

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

export interface StudioMediaItem {
  src: string
  title?: string
}

export type StudioTab = 'graph' | 'artifacts' | 'sources' | 'live'
export type BrowserDockMode = 'docked' | 'floating'

export function parseStudioSourceUrl(value: unknown): URL | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

function sourceKey(url: URL) {
  const canonical = new URL(url.href)
  canonical.hash = ''
  canonical.pathname = canonical.pathname.replace(/\/+$/, '')
  return canonical.href
}

export function resolveStudioCitation(index: number, local: readonly MessageSource[] | undefined, sources: readonly StudioSource[]) {
  if (!local?.length) return sources.find(source => source.index === index)
  const url = parseStudioSourceUrl(local[index - 1]?.url)
  if (!url) return undefined
  const key = sourceKey(url)
  return sources.find(source => {
    const candidate = parseStudioSourceUrl(source.url)
    return candidate && sourceKey(candidate) === key
  })
}

const rasterMime = /^image\/(?:png|jpeg|gif|webp|avif|bmp)$/i
const base64 = /^[a-z0-9+/]+={0,2}$/i

function mediaUrl(value: unknown, mime?: string): string | undefined {
  if (typeof value !== 'string' || !value) return
  if (/^\/api\/(?:screenshots|artifacts|workspaces)\//.test(value)) return getArtifactDownloadUrl(value)
  const url = parseStudioSourceUrl(value)
  if (url && !url.username && !url.password) return url.href
  const data = /^data:(image\/[\w+-]+);base64,([\s\S]+)$/i.exec(value)
  if (data) return rasterMime.test(data[1]) && base64.test(data[2]) ? value : undefined
  if (mime && rasterMime.test(mime) && base64.test(value)) return 'data:' + mime + ';base64,' + value
}

export function extractStudioMedia(messages: readonly Message[]): StudioMediaItem[] {
  const media = new Map<string, StudioMediaItem>()
  const add = (src: string | undefined, title?: unknown) => {
    if (src && !media.has(src)) media.set(src, { src, title: typeof title === 'string' ? title : undefined })
  }
  for (const message of messages) {
    for (const { type, data } of message.processEvents ?? []) {
      if ((type !== 'screenshot' && type !== 'tool_screenshot') || !data) continue
      const mime = data.mime_type || (/\.jpe?g$/i.test(data.filename ?? '') ? 'image/jpeg' : 'image/png')
      add(mediaUrl(data.image, mime) ?? mediaUrl(data.url), data.title || data.action)
    }
    for (const artifact of message.artifacts ?? []) {
      if (artifact.type !== 'image' && artifact.type !== 'chart') continue
      add(mediaUrl(artifact.image, artifact.mimeType || 'image/png')
        ?? mediaUrl(artifact.download_url) ?? mediaUrl(artifact.content), artifact.title)
    }
  }
  return [...media.values()]
}

export function composePromptWithResearchPlan(prompt: string, subtopics: string[], locale: Locale): string {
  const items = subtopics.map(topic => topic.trim().replace(/\s+/g, ' ')).filter(Boolean)
  if (!items.length) return prompt
  const outline = items.map((topic, index) => String(index + 1) + '. ' + topic).join('\n')
  return [prompt, '## ' + translations[locale].studioPlanTitle + '\n' + outline].filter(Boolean).join('\n\n')
}

function reportLabel(value: string) {
  const label = value
    .replace(/!?\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\[\d+\]|[*\x60~]/g, '')
    .replace(/(?:^|\s)#+\s*$/, '')
    .replace(/\s+/g, ' ').trim()
  const letters = Array.from(label)
  return letters.length > 54 ? letters.slice(0, 53).join('').trimEnd() + '…' : label
}

export function extractReportMindMap(markdown: string, fallbackTitle = 'Mind map'): ResearchTree | null {
  const rootId = 'report-root'
  const makeNode = (id: string, topic: string, depth: number, parent_id: string | null): ResearchNode => ({
    id, topic, depth, parent_id, children_ids: [], status: 'completed',
    findings_count: 0, sources_count: 0, summary_length: 0,
  })
  const root = makeNode(rootId, reportLabel(fallbackTitle) || 'Mind map', 0, null)
  const nodes: Record<string, ResearchNode> = { [rootId]: root }
  let count = 1
  let fence = ''
  let currentHeading = root
  let levels: { level: number; node: ResearchNode }[] = []
  let usedTitle = false
  const bullets = new Map<string, string[]>()
  const add = (parent: ResearchNode, topic: string) => {
    const node = makeNode('report-' + count++, topic, parent.depth + 1, parent.id)
    parent.children_ids.push(node.id)
    nodes[node.id] = node
    return node
  }

  for (const line of markdown.split(/\r?\n/)) {
    const delimiter = /^ {0,3}(\x60{3,}|~{3,})(.*)$/.exec(line)
    if (fence) {
      if (delimiter && delimiter[1][0] === fence[0] && delimiter[1].length >= fence.length && !delimiter[2].trim()) fence = ''
      continue
    }
    if (delimiter) {
      fence = delimiter[1]
      continue
    }
    const heading = /^ {0,3}(#{1,3})[ \t]+(.+)$/.exec(line)
    const bullet = /^ {0,3}(?:[-+*]|\d+[.)])[ \t]+(.+)$/.exec(line)
    const label = reportLabel(heading?.[2] ?? bullet?.[1]?.replace(/^\[[ xX]\]\s+/, '') ?? '')
    if (!label) continue
    if (heading) {
      const level = heading[1].length
      if (level === 1 && !usedTitle && count === 1) {
        root.topic = label
        usedTitle = true
        continue
      }
      if (count === 18) break
      levels = levels.filter(entry => entry.level < level)
      currentHeading = add(levels.at(-1)?.node ?? root, label)
      levels.push({ level, node: currentHeading })
    } else {
      const entries = bullets.get(currentHeading.id) ?? []
      if (entries.length < 2) {
        entries.push(label)
        bullets.set(currentHeading.id, entries)
        // Keep the report order even though heading slots take priority.
        currentHeading.children_ids.push('bullet:' + (entries.length - 1))
      }
    }
  }

  for (const parent of Object.values(nodes)) {
    parent.children_ids = parent.children_ids.flatMap(id => {
      if (!id.startsWith('bullet:')) return [id]
      if (count === 18) return []
      const bullet = bullets.get(parent.id)![Number(id.slice(7))]
      const node = makeNode('report-' + count++, bullet, parent.depth + 1, parent.id)
      nodes[node.id] = node
      return [node.id]
    })
  }
  if (count === 1) return null
  const entries = Object.values(nodes)
  return {
    root_id: rootId, nodes, total_nodes: count, completed_nodes: count, total_sources: 0, pending_nodes: 0,
    max_depth: Math.max(...entries.map(node => node.depth)),
    max_branches: Math.max(...entries.map(node => node.children_ids.length)),
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

export function extractResearchStudio(messages: readonly Message[], locale: Locale = 'en') {
  const assistants = messages.filter(message => message.role === 'assistant')
  const latestAssistant = assistants.at(-1)
  const sources = new Map<string, StudioSource>()
  const addSource = (value: unknown, title?: string) => {
    const url = parseStudioSourceUrl(value)
    if (!url) return
    const key = sourceKey(url)
    const previous = sources.get(key)
    if (previous) {
      if (!previous.title && title) previous.title = title
    } else {
      sources.set(key, { index: sources.size + 1, title: title || '', url: url.href, domain: url.hostname.replace(/^www\./, '') })
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

  const report = latestAssistant?.artifacts?.findLast(artifact => artifact.type === 'report' && !/^\s*</.test(artifact.content))
  const reportPrompt = messages.slice(0, latestAssistant ? messages.lastIndexOf(latestAssistant) : 0)
    .findLast(message => message.role === 'user')?.content.split(/\r?\n/, 1)[0]

  return {
    tree, telemetry, isResearchActive, researchId: researchRun?.id,
    mindMap: latestAssistant?.isStreaming ? null
      : extractReportMindMap(report?.content || latestAssistant?.content || '', report?.title || reportPrompt || translations[locale].studioMindMap),
    media: extractStudioMedia(messages),
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

export function layoutResearchTree(tree: ResearchTree, compact = false) {
  const cardWidth = compact ? 120 : 128
  const cardHeight = compact ? 62 : 84
  const rowSize = compact ? cardHeight : cardWidth
  const rowGap = compact ? 10 : 12
  const levelSize = compact ? cardWidth : cardHeight
  const levelGap = compact ? 19 : 28
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

  const rowSpan = (count: number) => count * rowSize + Math.max(0, count - 1) * rowGap
  const across = rowSpan(Math.max(1, ...levels.map(row => row.length))) + 2 * padding
  const length = Math.max(1, levels.length) * levelSize + Math.max(0, levels.length - 1) * levelGap + 2 * padding
  const [width, height] = compact ? [length, across] : [across, length]
  const position = new Map<string, { x: number; y: number }>()
  const nodes = levels.flatMap((row, depth) => row.map((node, index) => {
    const parent = row.length === 1 && node.parent_id ? position.get(node.parent_id) : undefined
    const acrossPosition = (compact ? parent?.y : parent?.x)
      ?? (across - rowSpan(row.length)) / 2 + index * (rowSize + rowGap)
    const depthPosition = padding + depth * (levelSize + levelGap)
    const [x, y] = compact ? [depthPosition, acrossPosition] : [acrossPosition, depthPosition]
    position.set(node.id, { x, y })
    return { node, x, y, width: cardWidth, height: cardHeight }
  }))
  const edges = links.map(({ from, to }) => {
    const parent = position.get(from)!
    const child = position.get(to)!
    const x1 = parent.x + (compact ? cardWidth : cardWidth / 2)
    const x2 = child.x + (compact ? 0 : cardWidth / 2)
    const y1 = parent.y + (compact ? cardHeight / 2 : cardHeight)
    const y2 = child.y + (compact ? cardHeight / 2 : 0)
    const midX = (x1 + x2) / 2
    const midY = (y1 + y2) / 2
    const curve = compact ? `${midX} ${y1} ${midX} ${y2}` : `${x1} ${midY} ${x2} ${midY}`
    return { from, to, path: `M ${x1} ${y1} C ${curve} ${x2} ${y2}` }
  })

  return { nodes, edges, width, height }
}

export function buildStandaloneGraphSvg(
  layout: ReturnType<typeof layoutResearchTree>,
  { title = '', dark = false }: { title?: string; dark?: boolean } = {},
): string {
  const colors = dark
    ? { canvas: '#111827', card: '#192438', root: '#223960', edge: '#677b99', border: '#465874', accent: '#79aaff', text: '#eff5ff' }
    : { canvas: '#f4f7fc', card: '#fff', root: '#e7efff', edge: '#8497b5', border: '#b9c9e0', accent: '#315ebb', text: '#18263b' }
  const xml = (value: string) => escapeMarkup(value.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]/g, ''))
  const edges = layout.edges.map(({ path }) => `<path d="${path}"/>`).join('')
  const cards = layout.nodes.map(({ x, y, width, height, node }) => {
    const root = node.parent_id === null
    const lines: string[] = []
    let line = ''
    let units = 0
    for (const character of Array.from(node.topic.replace(/\s+/g, ' ').trim())) {
      const size = /[^\u0000-\u024f]/.test(character) ? 2 : 1
      if (units + size > 18) {
        const boundary = line.lastIndexOf(' ')
        lines.push(boundary > 7 ? line.slice(0, boundary) : line)
        line = boundary > 7 ? line.slice(boundary + 1) : ''
        units = line.length
      }
      line += character
      units += size
    }
    if (line) lines.push(line)
    const maxLines = height < 65 ? 3 : 4
    if (lines.length > maxLines) {
      lines.length = maxLines
      lines[maxLines - 1] = lines[maxLines - 1].trimEnd() + '…'
    }
    const label = lines.map((part, index) =>
      `<tspan x="${width / 2}" dy="${index ? 14 : 0}">${xml(part.trim())}</tspan>`).join('')
    return `<g transform="translate(${x} ${y})"><rect width="${width}" height="${height}" rx="8" fill="${root ? colors.root : colors.card}" stroke="${root ? colors.accent : colors.border}"/><text x="${width / 2}" y="${height / 2 - (lines.length - 1) * 7 + 4}" text-anchor="middle" font-weight="${root ? 700 : 600}"><title>${xml(node.topic)}</title>${label}</text></g>`
  }).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}" role="img"><title>${xml(title)}</title><rect width="100%" height="100%" fill="${colors.canvas}"/><g fill="none" stroke="${colors.edge}" stroke-width="1.5">${edges}</g><g font-family="Arial, sans-serif" font-size="11" fill="${colors.text}">${cards}</g></svg>`
}
