'use client'

import React, { forwardRef, useId, useImperativeHandle, useRef, useState } from 'react'
import { ChevronDown, Code2, List, Pencil, Plug, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import type { useMcpConfig } from '@/hooks/useMcpConfig'
import { useI18n } from '@/lib/i18n/i18n-context'
import { formatCommandArgs, McpValidationError, parseCommandArgs, parseMcpServersJson, recordToRows, rowsToRecord, type McpKeyValueRow, type McpServerConfig, type McpTransport } from '@/lib/mcp'
import { cn } from '@/lib/utils'

export interface McpServersPanelHandle {
  save: () => Promise<boolean>
}

type McpServersPanelProps = ReturnType<typeof useMcpConfig> & { disabled?: boolean; onSavingChange: (saving: boolean) => void }
type Servers = Record<string, McpServerConfig>
interface ServerDraft {
  originalId: string | null
  id: string
  type: McpTransport
  url: string
  command: string
  args: string
  headers: McpKeyValueRow[]
  env: McpKeyValueRow[]
  cwd: string
}

function KeyValueFields({ label, rows, onChange }: { label: string; rows: McpKeyValueRow[]; onChange: (rows: McpKeyValueRow[]) => void }) {
  const { t } = useI18n()
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium">{label}</span>
        <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={() => onChange([...rows, { key: '', value: '' }])}>
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />{t('mcpAddRow')}
        </Button>
      </div>
      {rows.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input value={row.key} aria-label={`${label}: ${t('mcpKey')} ${index + 1}`} placeholder={t('mcpKey')} className="min-w-0 flex-1 font-mono text-xs" onChange={event => onChange(rows.map((item, i) => i === index ? { ...item, key: event.target.value } : item))} />
          <Input value={row.value} aria-label={`${label}: ${t('mcpValue')} ${index + 1}`} placeholder={t('mcpValue')} className="min-w-0 flex-1 font-mono text-xs" autoComplete="off" onChange={event => onChange(rows.map((item, i) => i === index ? { ...item, value: event.target.value } : item))} />
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive" aria-label={`${t('mcpRemoveRow')}: ${label} ${index + 1}`} onClick={() => onChange(rows.filter((_, i) => i !== index))}>
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      ))}
    </div>
  )
}

export const McpServersPanel = forwardRef<McpServersPanelHandle, McpServersPanelProps>(function McpServersPanel({ config, isLoading, error, refresh, saveConfig, disabled = false, onSavingChange }, ref) {
  const { t } = useI18n()
  const id = useId()
  const [draft, setDraft] = useState<{ enabled: boolean; servers: Servers } | null>(null)
  const [editor, setEditor] = useState<ServerDraft | null>(null)
  const [raw, setRaw] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const editorRef = useRef<HTMLInputElement>(null)
  const rawRef = useRef<HTMLTextAreaElement>(null)
  const enabled = draft?.enabled ?? config?.enabled ?? false
  const servers = draft?.servers ?? config?.servers ?? {}
  const changed = config !== null && (enabled !== config.enabled || JSON.stringify(servers) !== JSON.stringify(config.servers))
  const connected = config?.server_statuses.filter(server => server.status === 'connected').length ?? 0
  const messageFor = (cause: unknown) => cause instanceof McpValidationError ? t(cause.code) : t('mcpConfigInvalid')
  let rawError: string | null = null
  if (raw !== null) {
    try { parseMcpServersJson(raw) } catch (cause) { rawError = messageFor(cause) }
  }

  const updateServers = (next: Servers) => setDraft({ enabled, servers: next })
  const updateEditor = (next: Partial<ServerDraft>) => {
    setEditor(current => current && { ...current, ...next })
    setValidationError(null)
  }
  const editServer = (serverId: string | null) => {
    const server = serverId === null ? undefined : servers[serverId]
    setEditor({ originalId: serverId, id: serverId ?? '', type: server?.type ?? 'streamable_http', url: server?.url ?? '', command: server?.command ?? '', args: formatCommandArgs(server?.args), headers: recordToRows(server?.headers), env: recordToRows(server?.env), cwd: server?.cwd ?? '' })
    setValidationError(null)
  }
  const editedServers = (): Servers => {
    if (!editor) return servers
    const serverId = editor.id.trim()
    if (!serverId || serverId.startsWith('__')) throw new McpValidationError('mcpServerIdInvalid')
    if (serverId !== editor.originalId && Object.hasOwn(servers, serverId)) throw new McpValidationError('mcpServerIdExists')
    const original = editor.originalId === null ? undefined : servers[editor.originalId]
    const server: McpServerConfig = { type: editor.type, enabled: original?.enabled ?? true }
    if (original?.timeout !== undefined) server.timeout = original.timeout
    if (editor.type === 'stdio') {
      server.command = editor.command
      server.args = parseCommandArgs(editor.args)
      server.env = rowsToRecord(editor.env)
      if (editor.cwd.trim()) server.cwd = editor.cwd.trim()
    } else {
      server.url = editor.url
      server.headers = rowsToRecord(editor.headers)
    }
    const normalized = parseMcpServersJson(JSON.stringify({ [serverId]: server }))
    return { ...Object.fromEntries(Object.entries(servers).filter(([key]) => key !== editor.originalId)), ...normalized }
  }
  const applyEditor = () => {
    try {
      updateServers(editedServers())
      setEditor(null)
      setValidationError(null)
    } catch (cause) {
      setValidationError(messageFor(cause))
      editorRef.current?.focus()
    }
  }
  const applyRaw = () => {
    try {
      updateServers(parseMcpServersJson(raw ?? '{}'))
      setRaw(null)
    } catch {
      rawRef.current?.focus()
    }
  }

  useImperativeHandle(ref, () => ({
    save: async () => {
      let next: Servers
      try {
        next = raw !== null ? parseMcpServersJson(raw) : editedServers()
      } catch (cause) {
        setValidationError(messageFor(cause))
        if (raw !== null) rawRef.current?.focus()
        else editorRef.current?.focus()
        return false
      }
      if (!config || (enabled === config.enabled && JSON.stringify(next) === JSON.stringify(config.servers))) return true
      onSavingChange(true)
      try {
        await saveConfig(enabled, next)
        setDraft(null)
        setEditor(null)
        setRaw(null)
        toast.success(t('mcpSaved'))
        return true
      } catch {
        toast.error(t('mcpSaveFailed'))
        return false
      } finally {
        onSavingChange(false)
      }
    },
  }))

  return (
    <section id="mcp-servers" aria-label={t('mcpConfiguration')} className="scroll-mt-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Plug className="h-4 w-4 text-muted-foreground" aria-hidden="true" />{t('mcpConfiguration')}</h2>
          <p className="text-xs leading-5 text-muted-foreground">{t('mcpDescription')}</p>
        </div>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0 text-muted-foreground" aria-label={t('mcpRefresh')} disabled={isLoading || disabled} onClick={() => void refresh()}>
          <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} aria-hidden="true" />
        </Button>
      </div>
      {error && <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive-border bg-destructive-surface px-3 py-2 text-xs text-destructive"><span>{t('mcpLoadFailed')}</span><Button type="button" variant="ghost" size="sm" className="h-7 shrink-0 text-xs" disabled={isLoading || disabled} onClick={() => void refresh()}>{t('mcpRetry')}</Button></div>}
      <fieldset disabled={disabled || isLoading || !config} className="min-w-0 space-y-4">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/80 bg-surface-subtle/60 p-3">
          <div className="space-y-1">
            <Label htmlFor={`${id}-enabled`} className="text-sm font-medium">{t('enableMcp')}</Label>
            <p className="text-xs text-muted-foreground">{enabled ? t('mcpActive') : t('mcpDisabled')}</p>
          </div>
          <Switch id={`${id}-enabled`} checked={enabled} onCheckedChange={next => setDraft({ enabled: next, servers })} />
        </div>
        <div role="status" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="font-mono">{config?.config_path ?? 'config/mcp.json'}</span>
          <span className="tabular-nums">{t('mcpConnectedCount').replace('{count}', String(connected))}</span>
          <span className="tabular-nums">{t('mcpToolCount').replace('{count}', String(config?.loaded_tools ?? 0))}</span>
        </div>
        {isLoading && <p role="status" className="text-xs text-muted-foreground">{t('loading')}</p>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1 rounded-md bg-surface-subtle p-1">
            <Button type="button" variant="ghost" size="sm" aria-pressed={raw === null} className={cn('h-7 gap-1.5 px-2 text-xs', raw === null && 'bg-card shadow-xs')} onClick={() => { if (raw !== null) applyRaw() }}><List className="h-3.5 w-3.5" aria-hidden="true" />{t('mcpServerList')}</Button>
            <Button type="button" variant="ghost" size="sm" aria-pressed={raw !== null} disabled={editor !== null} className={cn('h-7 gap-1.5 px-2 text-xs', raw !== null && 'bg-card shadow-xs')} onClick={() => { if (raw === null) setRaw(JSON.stringify({ mcpServers: servers }, null, 2)) }}><Code2 className="h-3.5 w-3.5" aria-hidden="true" />{t('mcpImportJson')}</Button>
          </div>
          {raw === null && !editor && <Button type="button" variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => editServer(null)}><Plus className="h-3.5 w-3.5" aria-hidden="true" />{t('mcpAddServer')}</Button>}
        </div>
        {raw !== null ? (
          <div className="space-y-2">
            <Label htmlFor={`${id}-json`} className="text-xs">{t('serversConfiguration')}</Label>
            <p id={`${id}-json-hint`} className="text-xs leading-5 text-muted-foreground">{t('mcpImportHint')}</p>
            <Textarea ref={rawRef} id={`${id}-json`} value={raw} onChange={event => setRaw(event.target.value)} spellCheck={false} aria-invalid={!!rawError} aria-describedby={`${id}-json-hint${rawError ? ` ${id}-json-error` : ''}`} className={cn('min-h-[200px] font-mono text-xs leading-5', rawError && 'border-destructive')} />
            {rawError ? <p id={`${id}-json-error`} role="alert" className="text-xs text-destructive">{rawError}</p> : <p role="status" className="text-xs text-success">{t('mcpJsonValid')}</p>}
            <div className="flex justify-end"><Button type="button" variant="outline" size="sm" disabled={!!rawError} onClick={applyRaw}>{t('mcpApplyJson')}</Button></div>
          </div>
        ) : editor ? (
          <div className="space-y-4 rounded-lg border border-border/80 bg-card p-4">
            <h3 className="text-sm font-medium">{editor.originalId === null ? t('mcpAddServer') : t('mcpEditServer')}</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5"><Label htmlFor={`${id}-server-id`} className="text-xs">{t('mcpServerId')}</Label><Input ref={editorRef} autoFocus id={`${id}-server-id`} value={editor.id} placeholder={t('mcpServerIdPlaceholder')} onChange={event => updateEditor({ id: event.target.value })} className="font-mono text-xs" /></div>
              <div className="space-y-1.5"><Label htmlFor={`${id}-transport`} className="text-xs">{t('mcpTransport')}</Label><Select value={editor.type} onValueChange={value => updateEditor({ type: value as McpTransport })}><SelectTrigger id={`${id}-transport`} className="text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="streamable_http">{t('mcpTransportHttp')}</SelectItem><SelectItem value="stdio">{t('mcpTransportStdio')}</SelectItem><SelectItem value="sse">{t('mcpTransportSse')}</SelectItem></SelectContent></Select></div>
            </div>
            {editor.type === 'stdio' ? <>
              <div className="space-y-1.5"><Label htmlFor={`${id}-command`} className="text-xs">{t('mcpCommand')}</Label><Input id={`${id}-command`} value={editor.command} placeholder="npx" onChange={event => updateEditor({ command: event.target.value })} className="font-mono text-xs" /></div>
              <div className="space-y-1.5"><Label htmlFor={`${id}-args`} className="text-xs">{t('mcpArgs')}</Label><Input id={`${id}-args`} value={editor.args} onChange={event => updateEditor({ args: event.target.value })} className="font-mono text-xs" /><p className="text-xs leading-5 text-muted-foreground">{t('mcpArgsHint')}</p></div>
              <KeyValueFields label={t('mcpEnv')} rows={editor.env} onChange={env => updateEditor({ env })} />
              <div className="space-y-1.5"><Label htmlFor={`${id}-cwd`} className="text-xs">{t('mcpCwd')}</Label><Input id={`${id}-cwd`} value={editor.cwd} onChange={event => updateEditor({ cwd: event.target.value })} className="font-mono text-xs" /></div>
            </> : <>
              <div className="space-y-1.5"><Label htmlFor={`${id}-url`} className="text-xs">{t('mcpUrl')}</Label><Input id={`${id}-url`} type="url" value={editor.url} placeholder="https://mcp.example.com/mcp" onChange={event => updateEditor({ url: event.target.value })} className="font-mono text-xs" /></div>
              <KeyValueFields label={t('mcpHeaders')} rows={editor.headers} onChange={headers => updateEditor({ headers })} />
            </>}
            {validationError && <p role="alert" className="text-xs text-destructive">{validationError}</p>}
            <div className="flex justify-end gap-2"><Button type="button" variant="ghost" size="sm" onClick={() => { setEditor(null); setValidationError(null) }}>{t('cancel')}</Button><Button type="button" variant="outline" size="sm" onClick={applyEditor}>{t('mcpApplyServer')}</Button></div>
          </div>
        ) : (
          <div className="space-y-2">
            {Object.entries(servers).map(([serverId, server]) => {
              const saved = config?.servers[serverId]
              const status = JSON.stringify(saved) === JSON.stringify(server) ? config?.server_statuses.find(item => item.id === serverId) : undefined
              const state = !enabled || !server.enabled ? 'disabled' : status?.status ?? 'pending'
              const statusLabel = state === 'connected' ? t('mcpConnected') : state === 'error' ? t('error') : state === 'disabled' ? t('mcpServerDisabled') : t('mcpPending')
              const summary = server.type === 'stdio' ? `${server.command} ${(server.args ?? []).join(' ')}`.trim() : server.url
              return (
                <article key={serverId} className="min-w-0 rounded-lg border border-border/80 bg-card p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 space-y-1.5">
                      <h3 className="truncate font-mono text-sm font-medium" title={serverId}>{serverId}</h3>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="subtle">{server.type === 'stdio' ? t('mcpTransportStdio') : server.type === 'sse' ? t('mcpTransportSse') : t('mcpTransportHttp')}</Badge>
                        <Badge variant={state === 'connected' ? 'success' : state === 'error' ? 'destructive' : state === 'pending' ? 'warning' : 'subtle'}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{statusLabel}</Badge>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Switch aria-label={`${t('mcpEnableServer')}: ${serverId}`} checked={server.enabled} onCheckedChange={next => updateServers({ ...servers, [serverId]: { ...server, enabled: next } })} className="mr-1" />
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" aria-label={`${t('mcpEditServer')}: ${serverId}`} onClick={() => editServer(serverId)}><Pencil className="h-3.5 w-3.5" aria-hidden="true" /></Button>
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" aria-label={`${t('delete')}: ${serverId}`} onClick={() => updateServers(Object.fromEntries(Object.entries(servers).filter(([key]) => key !== serverId)))}><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /></Button>
                    </div>
                  </div>
                  <p className="mt-2 truncate font-mono text-xs text-muted-foreground" title={summary}>{summary}</p>
                  {state === 'error' && status?.error && <p className="mt-2 break-words rounded-md bg-destructive-surface px-2.5 py-2 text-xs leading-5 text-destructive">{status.error}</p>}
                  <details className="group mt-2 text-xs">
                    <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-sm py-1 text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"><ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" aria-hidden="true" /><span className="tabular-nums">{t('mcpToolCount').replace('{count}', String(state === 'disabled' ? 0 : status?.tool_count ?? 0))}</span></summary>
                    <ul className="mt-1 space-y-3 border-t border-border/70 pt-3">
                      {state !== 'disabled' && status?.tools.map(tool => <li key={tool.name} className="min-w-0 space-y-1"><p className="break-all font-mono font-medium">{tool.original_name}</p><p className="break-words leading-5 text-muted-foreground">{tool.description}</p></li>)}
                    </ul>
                    {(state === 'disabled' || !status?.tools.length) && <p className="py-2 text-muted-foreground">{t('mcpNoTools')}</p>}
                  </details>
                </article>
              )
            })}
            {config && Object.keys(servers).length === 0 && <div className="rounded-lg border border-dashed border-border px-4 py-7 text-center"><Plug className="mx-auto mb-2 h-5 w-5 text-muted-foreground" aria-hidden="true" /><p className="text-sm font-medium">{t('mcpNoServers')}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{t('mcpNoServersHint')}</p></div>}
          </div>
        )}
        {(changed || editor || raw !== null) && <p className="text-xs leading-5 text-muted-foreground">{t('mcpSaveHint')}</p>}
      </fieldset>
    </section>
  )
})
