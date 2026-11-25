'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { getApiBaseUrl } from '@/lib/api'
import type { McpConfigResponse, McpServerConfig } from '@/lib/mcp'

const MCP_CONFIG_UPDATED = 'weaver:mcp-config-updated'

export function useMcpConfig() {
  const [config, setConfig] = useState<McpConfigResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const request = useRef<AbortController | null>(null)

  const loadConfig = useCallback(() => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    return fetch(`${getApiBaseUrl()}/api/mcp/config`, { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error(`MCP config: HTTP ${response.status}`)
        return response.json() as Promise<McpConfigResponse>
      })
      .then(next => { if (!controller.signal.aborted) setConfig(next) })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause : new Error(String(cause))) })
      .finally(() => { if (!controller.signal.aborted) setIsLoading(false) })
  }, [])

  const refresh = useCallback(() => {
    setIsLoading(true)
    setError(null)
    return loadConfig()
  }, [loadConfig])

  const saveConfig = useCallback(async (enable: boolean, servers: Record<string, McpServerConfig>) => {
    const response = await fetch(`${getApiBaseUrl()}/api/mcp/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable, mcpServers: servers }),
    })
    if (!response.ok) throw new Error(`MCP config: HTTP ${response.status}`)
    const next: McpConfigResponse = await response.json()
    window.dispatchEvent(new CustomEvent<McpConfigResponse>(MCP_CONFIG_UPDATED, { detail: next }))
    return next
  }, [])

  useEffect(() => {
    const onUpdated = (event: Event) => {
      request.current?.abort()
      setConfig((event as CustomEvent<McpConfigResponse>).detail)
      setError(null)
      setIsLoading(false)
    }
    window.addEventListener(MCP_CONFIG_UPDATED, onUpdated)
    void loadConfig()
    return () => {
      request.current?.abort()
      window.removeEventListener(MCP_CONFIG_UPDATED, onUpdated)
    }
  }, [loadConfig])

  return { config, isLoading, error, refresh, saveConfig }
}
