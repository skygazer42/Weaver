// Default to 8001 to avoid common local port conflicts (e.g. other services on 8000).
const DEFAULT_API_PORT = 8001
export const DEFAULT_API_URL = `http://127.0.0.1:${DEFAULT_API_PORT}`

function normalizeBaseUrl(raw: string): string {
  return raw.replace(/\/$/, '')
}

export function getApiBaseUrl(): string {
  const envUrl = (process.env.NEXT_PUBLIC_API_URL || '').trim()
  if (envUrl) return normalizeBaseUrl(envUrl)

  // Browser runtime: default to the current host so remote access works out of the box.
  // Example: UI on http://<server-ip>:3100 → API defaults to http://<server-ip>:8001
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'https' : 'http'
    const hostname = window.location.hostname || '127.0.0.1'
    return `${protocol}://${hostname}:${DEFAULT_API_PORT}`
  }

  // SSR / Node runtime fallback (assumes API is local to the Next server).
  return DEFAULT_API_URL
}

export function apiUrl(path: string): string {
  const baseUrl = getApiBaseUrl()
  const trimmed = (path || '').trim()
  if (!trimmed) return baseUrl
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return trimmed

  if (trimmed.startsWith('/')) return `${baseUrl}${trimmed}`
  return `${baseUrl}/${trimmed}`
}

export type ChatStreamProtocol = 'sse' | 'legacy'

export function getChatStreamProtocol(): ChatStreamProtocol {
  const raw = (process.env.NEXT_PUBLIC_CHAT_STREAM_PROTOCOL || 'sse').trim().toLowerCase()
  return raw === 'legacy' ? 'legacy' : 'sse'
}

export function getChatStreamUrl(): string {
  const protocol = getChatStreamProtocol()
  return apiUrl(protocol === 'legacy' ? '/api/chat' : '/api/chat/sse')
}

export type ResearchStreamProtocol = 'sse' | 'legacy'

export function getResearchStreamProtocol(): ResearchStreamProtocol {
  const raw = (process.env.NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL || 'sse').trim().toLowerCase()
  return raw === 'legacy' ? 'legacy' : 'sse'
}

export function getResearchStreamUrl(query?: string): string {
  const protocol = getResearchStreamProtocol()
  if (protocol === 'sse') return apiUrl('/api/research/sse')

  const params = new URLSearchParams({ query: String(query || '').trim() })
  return apiUrl(`/api/research?${params.toString()}`)
}

export function getApiWsBaseUrl(): string {
  return getApiBaseUrl().replace(/^http/, 'ws')
}
