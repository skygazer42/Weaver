import type { Artifact, ProcessEvent, ToolInvocation } from '../types/chat'

export type ThinkingStepKind =
  | 'thinking'
  | 'search'
  | 'reading'
  | 'milestone'
  | 'quality'
  | 'task'
  | 'artifact'
  | 'status'

export interface ThinkingStep {
  id: string
  kind: ThinkingStepKind
  text?: string
  query?: string
  page?: string
  count?: number
  progress?: number
  state?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: 'started' | 'completed' | 'updated'
  title?: string
  summary?: string
  downloadUrl?: string
}

export interface NormalizedThinkingProcess {
  steps: ThinkingStep[]
  stepCount: number
}

interface Candidate extends ThinkingStep {
  order: number
}

interface RawOperation {
  name: string
  data: Record<string, unknown>
  args: Record<string, unknown>
  callId?: string
  order: number
  eventType?: string
}

const TOOL_EVENT_TYPES = new Set(['tool', 'tool_start', 'tool_result', 'tool_error'])
const URL_KEYS = new Set([
  'url',
  'urls',
  'href',
  'link',
  'links',
  'page_url',
  'pageUrl',
  'source_url',
  'sourceUrl',
  'target_url',
  'targetUrl',
])

// These values are implementation details. They may be used for classification, never returned to the UI.
const INTERNAL_TERM_PATTERN = /\b(?:tavily_search|crawl_urls|fetch_url|serper_search|brave_search|execute_code|browser_[\w-]+|sb_browser_[\w-]+|research_node_[\w-]+|research_tree_update|quality_update|task_update|unknown|tool_start|tool_result|tool_error|tool-calling)\b/gi
const GENERIC_STATUS_PATTERN = /^(?:initializing research agent|running agent|working|thinking|processing|connecting|starting)(?:\b|[.…\s])/i

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function textValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const text = textValue(value).trim()
    if (text) return text
  }
  return ''
}

function cleanText(value: unknown, maxLength = 240): string {
  const text = firstText(value)
    .replace(INTERNAL_TERM_PATTERN, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return ''
  return text.length > maxLength ? `${text.slice(0, maxLength - 1).trimEnd()}…` : text
}

function normalizedText(value: unknown): string {
  return cleanText(value, 10000).normalize('NFKC').toLowerCase()
}

function numberValue(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return value
}

function percentValue(value: unknown): number | undefined {
  const number = numberValue(value)
  if (number === undefined) return undefined
  return Math.round(Math.max(0, Math.min(100, number)))
}

function extractQuery(data: Record<string, unknown>, args: Record<string, unknown>): string {
  return cleanText(firstText(data.query, data.search_query, data.searchQuery, args.query, args.search_query, args.searchQuery), 10000)
}

function collectUrls(value: unknown, key = '', depth = 0, urls: string[] = []): string[] {
  if (depth > 3 || value === null || value === undefined) return urls

  if (typeof value === 'string') {
    const matches = value.match(/https?:\/\/[^\s"'<>]+/gi) || []
    for (const match of matches) {
      const normalized = match.replace(/[),.;]+$/, '')
      if (normalized) urls.push(normalized)
    }
    return urls
  }

  if (Array.isArray(value)) {
    for (const item of value) collectUrls(item, key, depth + 1, urls)
    return urls
  }

  const record = asRecord(value)
  for (const [childKey, childValue] of Object.entries(record)) {
    if (URL_KEYS.has(childKey) || URL_KEYS.has(key)) {
      collectUrls(childValue, childKey, depth + 1, urls)
    } else if (typeof childValue === 'object' && childValue !== null) {
      collectUrls(childValue, childKey, depth + 1, urls)
    }
  }
  return urls
}

function pageLabel(url: string): string {
  try {
    const parsed = new URL(url)
    const host = parsed.hostname.replace(/^www\./i, '')
    const path = parsed.pathname.replace(/\/$/, '')
    return cleanText(`${host}${path}`, 120)
  } catch {
    return cleanText(url, 120)
  }
}

function isSearchName(name: string): boolean {
  return /search/i.test(name) && !/screenshot/i.test(name)
}

function isReadingName(name: string): boolean {
  return /(?:crawl[_-]?urls?|fetch[_-]?url|scrap|browser_|screenshot|navigate|read[_-]?url|webpage)/i.test(name)
}

function operationFromEvent(event: ProcessEvent, order: number): RawOperation | undefined {
  const data = asRecord(event.data)
  if (!TOOL_EVENT_TYPES.has(event.type) && event.type !== 'screenshot') return undefined
  const args = asRecord(data.args)
  const name = firstText(data.name, data.tool, data.toolName, event.type).toLowerCase()
  if (!name) return undefined
  const callId = firstText(data.toolCallId, data.tool_call_id, data.callId, data.id) || undefined
  return { name, data, args, callId, order, eventType: event.type }
}

function operationFromTool(tool: ToolInvocation, order: number): RawOperation | undefined {
  const args = asRecord(tool.args)
  const name = firstText(tool.toolName).toLowerCase()
  if (!name) return undefined
  return { name, data: {}, args, callId: tool.toolCallId || undefined, order }
}

export function normalizeThinkingProcess({
  events = [],
  tools = [],
  artifacts = [],
}: {
  events?: ProcessEvent[]
  tools?: ToolInvocation[]
  artifacts?: Artifact[]
}): NormalizedThinkingProcess {
  const candidates = new Map<string, Candidate>()
  const operations = new Map<string, RawOperation>()
  const pendingOperations = new Map<string, string[]>()
  const thinkingCandidates = new Map<string, { text: string; order: number }>()
  let nextId = 0
  let nextOperationId = 0
  let readingWithoutUrlCount = 0
  let readingWithoutUrlOrder = Number.POSITIVE_INFINITY

  const add = (step: Omit<ThinkingStep, 'id'>, dedupeKey: string, order: number) => {
    const previous = candidates.get(dedupeKey)
    if (previous && previous.order <= order) return
    candidates.set(dedupeKey, { ...step, id: previous?.id || `step-${nextId++}`, order })
  }

  const addThinking = (text: string, order: number) => {
    const key = normalizedText(text)
    if (!key) return
    thinkingCandidates.delete(key)
    thinkingCandidates.set(key, { text: cleanText(text), order })
  }

  const addSearch = (query: string, order: number) => {
    const normalizedQuery = normalizedText(query)
    if (!normalizedQuery) return
    add({ kind: 'search', query: cleanText(query, 10000) }, `search:${normalizedQuery}`, order)
  }

  const addReading = (operation: RawOperation) => {
    const urls = Array.from(new Set(collectUrls({ ...operation.data, args: operation.args })))
    if (urls.length > 0) {
      for (const url of urls) {
        const page = pageLabel(url)
        const key = normalizedText(page)
        if (key) add({ kind: 'reading', page }, `reading:${key}`, operation.order)
      }
      return
    }
    readingWithoutUrlCount += 1
    readingWithoutUrlOrder = Math.min(readingWithoutUrlOrder, operation.order)
  }

  const queueOperation = (operation: RawOperation) => {
    const isStart = operation.eventType === 'tool_start' || operation.data.status === 'running'
    const isResult = operation.eventType === 'tool_result' || operation.data.status === 'completed'
    const pending = pendingOperations.get(operation.name) || []
    const key = operation.callId || (isResult ? pending.shift() : undefined) || `anonymous-${nextOperationId++}`
    if (!operation.callId && isStart) pending.push(key)
    pendingOperations.set(operation.name, pending)

    let previous = operations.get(key)
    if (!previous && operation.callId && !operation.eventType) {
      const query = extractQuery(operation.data, operation.args)
      const urls = collectUrls(operation.args)
      const anonymous = Array.from(operations.entries()).find(([, candidate]) =>
        !candidate.callId && candidate.name === operation.name && (
          (!query && urls.length === 0) ||
          (query && normalizedText(query) === normalizedText(extractQuery(candidate.data, candidate.args))) ||
          urls.some((url) => collectUrls({ ...candidate.data, args: candidate.args }).includes(url))
        ),
      )
      if (anonymous) {
        previous = anonymous[1]
        operations.delete(anonymous[0])
      }
    }
    if (!previous) {
      operations.set(key, operation)
      return
    }
    operations.set(key, {
      ...previous,
      callId: operation.callId || previous.callId,
      name: TOOL_EVENT_TYPES.has(operation.name) ? previous.name : operation.name,
      data: {
        ...previous.data,
        ...operation.data,
        query: extractQuery(operation.data, operation.args) || extractQuery(previous.data, previous.args),
      },
      args: {
        ...previous.args,
        ...operation.args,
        urls: [...collectUrls(previous.data), ...collectUrls(previous.args), ...collectUrls(operation.data), ...collectUrls(operation.args)],
      },
    })
  }

  const orderedEvents = [...events].sort((a, b) => a.timestamp - b.timestamp)
  for (const [index, event] of orderedEvents.entries()) {
    const type = String(event.type || '').toLowerCase()
    const order = event.timestamp || index
    const data = asRecord(event.data)

    if (type === 'thinking') {
      addThinking(firstText(data.text, data.content), order)
      continue
    }

    if (type === 'status') {
      const text = cleanText(data.text || data.message)
      const normalized = normalizedText(text)
      if (text && !GENERIC_STATUS_PATTERN.test(text) && !normalized.startsWith('working')) {
        add({ kind: 'status', text }, `status:${normalized}`, order)
      }
      continue
    }

    if (type === 'search') {
      addSearch(extractQuery(data, {}), order)
      continue
    }

    if (type === 'task_update') {
      const task = asRecord(data.task)
      const title = cleanText(firstText(data.title, data.topic, task.content, asRecord(data.section).title))
      const summary = cleanText(firstText(data.summary, data.description, data.message, task.result))
      const progress = percentValue(data.progress ?? task.progress)
      const rawState = firstText(data.status, task.status)
      const state = ['pending', 'running', 'completed', 'failed', 'cancelled'].includes(rawState)
        ? rawState as ThinkingStep['state']
        : undefined
      if (title || summary || progress !== undefined) {
        const key = `task:${normalizedText(title || summary)}`
        candidates.delete(key)
        add(
          { kind: 'task', title: title || undefined, summary: summary || undefined, progress, state },
          key,
          order,
        )
      }
      continue
    }

    if (type === 'research_node_start' || type === 'research_node_complete' || type === 'research_tree_update') {
      const topic = cleanText(data.topic || data.title)
      const summary = cleanText(data.summary || data.description || data.message)
      const progress = percentValue(data.progress ?? data.percent ?? data.percentage)
      const phase = type === 'research_node_start' ? 'started' : type === 'research_node_complete' ? 'completed' : 'updated'
      add(
        { kind: 'milestone', phase, title: topic || undefined, summary: summary || undefined, progress },
        `milestone:${phase}:${normalizedText(topic || summary)}:${progress ?? ''}`,
        order,
      )
      continue
    }

    if (type === 'quality_update') {
      const summary = cleanText(data.summary || data.message)
      const coverage = numberValue(data.query_coverage_score ?? data.citation_coverage_score ?? data.citation_coverage)
      const score = coverage === undefined ? percentValue(data.progress) : percentValue(coverage * 100)
      add(
        { kind: 'quality', summary: summary || undefined, progress: score },
        `quality:${normalizedText(summary)}:${score ?? ''}`,
        order,
      )
      continue
    }

    const operation = operationFromEvent(event, order)
    if (operation) queueOperation(operation)
  }

  const toolOperations = tools
    .map((tool, index) => operationFromTool(tool, Number.MAX_SAFE_INTEGER - tools.length + index))
    .filter((operation): operation is RawOperation => Boolean(operation))
  for (const operation of toolOperations) queueOperation(operation)

  for (const operation of operations.values()) {
    const query = extractQuery(operation.data, operation.args)
    if (isSearchName(operation.name)) {
      if (query) addSearch(query, operation.order)
      continue
    }
    const urls = collectUrls({ ...operation.data, args: operation.args })
    if (!isReadingName(operation.name) && urls.length === 0) continue
    addReading(operation)
  }

  if (readingWithoutUrlCount > 0) {
    add(
      { kind: 'reading', count: readingWithoutUrlCount },
      'reading:without-url',
      readingWithoutUrlOrder,
    )
  }

  for (const [key, thinking] of Array.from(thinkingCandidates).slice(-3)) {
    add({ kind: 'thinking', text: thinking.text }, `thinking:${key}`, thinking.order)
  }

  for (const artifact of artifacts) {
    const downloadUrl = firstText(artifact.download_url) || undefined
    const summary = /^[\[{]/.test(firstText(artifact.content)) ? '' : cleanText(artifact.content, 220)
    if (!downloadUrl && !summary) continue
    const title = cleanText(artifact.title, 120)
    add(
      {
        kind: 'artifact',
        title: title || undefined,
        summary: summary || undefined,
        downloadUrl,
      },
      `artifact:${artifact.id || normalizedText(title || summary)}`,
      Number.MAX_SAFE_INTEGER,
    )
  }

  const steps = Array.from(candidates.values())
    .sort((a, b) => a.order - b.order)
    .map(({ order: _order, ...step }) => step)

  return { steps, stepCount: steps.length }
}

