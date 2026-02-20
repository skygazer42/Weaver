// Default to 8001 to avoid common local port conflicts (e.g. other services on 8000).
export const DEFAULT_API_URL = 'http://127.0.0.1:8001'

export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL
  return raw.replace(/\/$/, '')
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
