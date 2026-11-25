export type McpTransport = 'streamable_http' | 'stdio' | 'sse'

export interface McpServerConfig {
  type: McpTransport
  enabled: boolean
  url?: string
  headers?: Record<string, string>
  command?: string
  args?: string[]
  env?: Record<string, string>
  cwd?: string
  timeout?: number
}

export interface McpToolInfo {
  name: string
  original_name: string
  description: string
}

export interface McpServerStatus {
  id: string
  type: McpTransport
  enabled: boolean
  status: 'connected' | 'error' | 'disabled'
  error: string | null
  tool_count: number
  tools: McpToolInfo[]
}

export interface McpConfigResponse {
  enabled: boolean
  servers: Record<string, McpServerConfig>
  mcpServers: Record<string, McpServerConfig>
  loaded_tools: number
  config_path: string
  server_statuses: McpServerStatus[]
  message?: string
}

export type McpValidationCode = 'mcpConfigInvalid' | 'mcpServerIdInvalid' | 'mcpServerIdExists' | 'mcpTransportInvalid' | 'mcpUrlInvalid' | 'mcpCommandRequired' | 'mcpArgsInvalid' | 'mcpKeyValueInvalid' | 'mcpDuplicateKey'

export class McpValidationError extends Error {
  constructor(public readonly code: McpValidationCode) {
    super(code)
  }
}

export interface McpKeyValueRow {
  key: string
  value: string
}

export function recordToRows(record: Record<string, string> = {}): McpKeyValueRow[] {
  return Object.entries(record).map(([key, value]) => ({ key, value }))
}

export function rowsToRecord(rows: McpKeyValueRow[]): Record<string, string> {
  const entries = rows.filter(row => row.key || row.value).map(({ key, value }) => {
    if (!key.trim()) throw new McpValidationError('mcpKeyValueInvalid')
    return [key.trim(), value] as const
  })
  if (new Set(entries.map(([key]) => key)).size !== entries.length) throw new McpValidationError('mcpDuplicateKey')
  return Object.fromEntries(entries)
}

export function formatCommandArgs(args: string[] = []): string {
  return JSON.stringify(args)
}

export function parseCommandArgs(raw: string): string[] {
  let args: unknown
  try {
    args = JSON.parse(raw.trim() || '[]')
  } catch {
    throw new McpValidationError('mcpArgsInvalid')
  }
  if (!Array.isArray(args) || !args.every(arg => typeof arg === 'string')) throw new McpValidationError('mcpArgsInvalid')
  return args
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function stringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value) || !Object.values(value).every(item => typeof item === 'string')) throw new McpValidationError('mcpKeyValueInvalid')
  return value as Record<string, string>
}

export function parseMcpServersJson(raw: string): Record<string, McpServerConfig> {
  const parsed: unknown = JSON.parse(raw)
  if (!isRecord(parsed)) throw new McpValidationError('mcpConfigInvalid')
  const servers = Object.hasOwn(parsed, 'mcpServers') ? parsed.mcpServers : parsed
  if (!isRecord(servers)) throw new McpValidationError('mcpConfigInvalid')
  const ids = new Set<string>()
  return Object.fromEntries(Object.entries(servers).map(([rawId, entry]) => {
    const id = rawId.trim()
    if (!id || id.startsWith('__')) throw new McpValidationError('mcpServerIdInvalid')
    if (ids.has(id)) throw new McpValidationError('mcpServerIdExists')
    ids.add(id)
    if (!isRecord(entry)) throw new McpValidationError('mcpConfigInvalid')
    const explicitType = entry.type ?? entry.transport
    const url = typeof entry.url === 'string' ? entry.url.trim() : ''
    const command = typeof entry.command === 'string' ? entry.command.trim() : ''
    const aliases: Record<string, McpTransport> = { http: 'streamable_http', 'streamable-http': 'streamable_http', streamablehttp: 'streamable_http', streamable_http: 'streamable_http', stdio: 'stdio', sse: 'sse' }
    const type = explicitType === undefined
      ? (url ? (/\/sse\/?(?:[?#].*)?$/i.test(url) ? 'sse' : 'streamable_http') : command ? 'stdio' : undefined)
      : typeof explicitType === 'string' && Object.hasOwn(aliases, explicitType.trim().toLowerCase()) ? aliases[explicitType.trim().toLowerCase()] : undefined
    if (!type) throw new McpValidationError('mcpTransportInvalid')
    if (entry.enabled !== undefined && typeof entry.enabled !== 'boolean') throw new McpValidationError('mcpConfigInvalid')
    const config: McpServerConfig = { type, enabled: entry.enabled ?? true }
    if (typeof entry.timeout === 'number' && entry.timeout > 0) config.timeout = entry.timeout
    if (type === 'stdio') {
      if (!command) throw new McpValidationError('mcpCommandRequired')
      config.command = command
      config.args = parseCommandArgs(JSON.stringify(entry.args ?? []))
      if (entry.env !== undefined) config.env = stringRecord(entry.env)
      if (entry.cwd !== undefined) {
        if (typeof entry.cwd !== 'string') throw new McpValidationError('mcpConfigInvalid')
        if (entry.cwd.trim()) config.cwd = entry.cwd.trim()
      }
    } else {
      let endpoint: URL
      try {
        endpoint = new URL(url)
      } catch {
        throw new McpValidationError('mcpUrlInvalid')
      }
      if (!['http:', 'https:'].includes(endpoint.protocol)) throw new McpValidationError('mcpUrlInvalid')
      config.url = url
      if (entry.headers !== undefined) config.headers = stringRecord(entry.headers)
    }
    return [id, config]
  }))
}
