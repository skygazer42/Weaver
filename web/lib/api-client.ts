import { apiUrl } from '@/lib/api'
import type { components } from '@/lib/api-types'

export type McpServersConfig = Record<string, unknown>

export type McpConfigResponse = {
  enabled: boolean
  servers: McpServersConfig
  loaded_tools: number
}

function mergeHeaders(headers: HeadersInit | undefined, defaults: Record<string, string>): Headers {
  const merged = new Headers(headers)
  for (const [key, value] of Object.entries(defaults)) {
    if (!merged.has(key)) merged.set(key, value)
  }
  return merged
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: mergeHeaders(init.headers, { Accept: 'application/json' }),
  })

  const bodyText = await response.text().catch(() => '')
  if (!response.ok) {
    const suffix = bodyText ? `: ${bodyText}` : ''
    throw new Error(`API request failed (${response.status})${suffix}`)
  }

  if (!bodyText) return undefined as T
  try {
    return JSON.parse(bodyText) as T
  } catch {
    return bodyText as unknown as T
  }
}

export async function getMcpConfig(): Promise<McpConfigResponse> {
  return apiFetch<McpConfigResponse>('/api/mcp/config')
}

export async function updateMcpConfig(
  payload: components['schemas']['MCPConfigPayload']
): Promise<McpConfigResponse> {
  return apiFetch<McpConfigResponse>('/api/mcp/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export type ResumeInterruptRequest = components['schemas']['GraphInterruptResumeRequest']
export type ChatResponse = {
  id: string
  content: string
  role?: string
  timestamp: string
}
export type ResumeInterruptResponse =
  | ChatResponse
  | { status: 'interrupted'; interrupts: unknown[] }

export async function resumeInterrupt(payload: ResumeInterruptRequest): Promise<ResumeInterruptResponse> {
  return apiFetch<ResumeInterruptResponse>('/api/interrupt/resume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
