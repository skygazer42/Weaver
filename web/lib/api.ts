// Default to 8001 to avoid common local port conflicts (e.g. other services on 8000).
export const DEFAULT_API_URL = 'http://127.0.0.1:8001'

export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL
  return raw.replace(/\/$/, '')
}

export function getApiWsBaseUrl(): string {
  return getApiBaseUrl().replace(/^http/, 'ws')
}
