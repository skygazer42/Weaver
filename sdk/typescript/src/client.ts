import type { StreamEvent } from './types.js'
import { readDataStreamEvents, readSseEvents } from './sse.js'

export class WeaverApiError extends Error {
  status: number
  path: string
  bodyText: string

  constructor(opts: { status: number; path: string; bodyText: string }) {
    const suffix = opts.bodyText ? `: ${opts.bodyText}` : ''
    super(`Weaver API request failed (${opts.status}) ${opts.path}${suffix}`)
    this.status = opts.status
    this.path = opts.path
    this.bodyText = opts.bodyText
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

function normalizeBaseUrl(raw: string): string {
  const text = String(raw || '').trim()
  if (!text) return 'http://127.0.0.1:8001'
  return text.replace(/\/+$/, '')
}

function mergeHeaders(
  headers: HeadersInit | undefined,
  defaults: Record<string, string>
): Headers {
  const merged = new Headers(headers)
  for (const [key, value] of Object.entries(defaults)) {
    if (!merged.has(key)) merged.set(key, value)
  }
  return merged
}

export class WeaverClient {
  private baseUrl: string
  private headers: Record<string, string>
  private fetchImpl: FetchLike
  lastThreadId: string | null = null

  constructor(opts: { baseUrl?: string; headers?: Record<string, string>; fetch?: FetchLike } = {}) {
    this.baseUrl = normalizeBaseUrl(opts.baseUrl || 'http://127.0.0.1:8001')
    this.headers = opts.headers || {}
    this.fetchImpl = opts.fetch || fetch
  }

  private url(path: string): string {
    const p = path.startsWith('/') ? path : `/${path}`
    return `${this.baseUrl}${p}`
  }

  async requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(this.url(path), {
      ...init,
      headers: mergeHeaders({ ...this.headers, ...(init.headers || {}) }, {
        Accept: 'application/json',
      }),
    })

    const bodyText = await response.text().catch(() => '')
    if (!response.ok) {
      throw new WeaverApiError({ status: response.status, path, bodyText })
    }

    if (!bodyText) return undefined as T
    try {
      return JSON.parse(bodyText) as T
    } catch {
      return bodyText as unknown as T
    }
  }

  async requestRaw(path: string, init: RequestInit = {}): Promise<Response> {
    const response = await this.fetchImpl(this.url(path), {
      ...init,
      headers: mergeHeaders({ ...this.headers, ...(init.headers || {}) }, {}),
    })

    if (!response.ok) {
      const bodyText = await response.text().catch(() => '')
      throw new WeaverApiError({ status: response.status, path, bodyText })
    }

    return response
  }

  async *chatSse(payload: unknown, opts: { signal?: AbortSignal } = {}): AsyncGenerator<StreamEvent> {
    const response = await this.fetchImpl(this.url('/api/chat/sse'), {
      method: 'POST',
      headers: mergeHeaders({ ...this.headers }, {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
      signal: opts.signal,
    })

    if (!response.ok) {
      const bodyText = await response.text().catch(() => '')
      throw new WeaverApiError({ status: response.status, path: '/api/chat/sse', bodyText })
    }

    this.lastThreadId =
      response.headers.get('X-Thread-ID') || response.headers.get('x-thread-id') || null

    for await (const event of readSseEvents(response)) {
      const data = event.data

      if (data && typeof data === 'object' && 'type' in data && 'data' in data) {
        yield data as StreamEvent
        continue
      }

      if (event.event) {
        yield { type: event.event, data }
      }
    }
  }

  async cancelChat(threadId: string): Promise<unknown> {
    const safeId = encodeURIComponent(String(threadId))
    return this.requestJson(`/api/chat/cancel/${safeId}`, { method: 'POST' })
  }

  async cancelAllChats(): Promise<unknown> {
    return this.requestJson('/api/chat/cancel-all', { method: 'POST' })
  }

  async *researchStream(query: string, opts: { signal?: AbortSignal } = {}): AsyncGenerator<StreamEvent> {
    const params = new URLSearchParams({ query: String(query || '') })
    const path = `/api/research?${params.toString()}`
    const response = await this.requestRaw(path, {
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
      signal: opts.signal,
    })

    for await (const ev of readDataStreamEvents(response)) {
      yield ev
    }
  }

  async listSessions(opts: { limit?: number; status?: string } = {}): Promise<unknown> {
    const params = new URLSearchParams()
    if (opts.limit != null) params.set('limit', String(opts.limit))
    if (opts.status) params.set('status', String(opts.status))
    const query = params.toString()
    const path = query ? `/api/sessions?${query}` : '/api/sessions'
    return this.requestJson(path)
  }

  async getSession(threadId: string): Promise<unknown> {
    const safeId = encodeURIComponent(String(threadId))
    return this.requestJson(`/api/sessions/${safeId}`)
  }

  async getEvidence(threadId: string): Promise<unknown> {
    const safeId = encodeURIComponent(String(threadId))
    return this.requestJson(`/api/sessions/${safeId}/evidence`)
  }

  async listExportTemplates(): Promise<unknown> {
    return this.requestJson('/api/export/templates')
  }

  async exportReport(
    threadId: string,
    opts: { format?: string; title?: string; template?: string } = {}
  ): Promise<{ contentType: string | null; bytes: ArrayBuffer }> {
    const safeId = encodeURIComponent(String(threadId))
    const params = new URLSearchParams()
    if (opts.format) params.set('format', String(opts.format))
    if (opts.title) params.set('title', String(opts.title))
    if (opts.template) params.set('template', String(opts.template))
    const query = params.toString()
    const path = query ? `/api/export/${safeId}?${query}` : `/api/export/${safeId}`

    const response = await this.requestRaw(path, { method: 'GET' })
    return {
      contentType: response.headers.get('content-type'),
      bytes: await response.arrayBuffer(),
    }
  }
}
