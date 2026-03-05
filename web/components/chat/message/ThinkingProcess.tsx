'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Loader2, CheckCircle2, Search, Wrench, Image as ImageIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ProcessEvent, RunMetrics, ToolInvocation } from '@/types/chat'

interface ThinkingProcessProps {
  tools?: ToolInvocation[]
  events?: ProcessEvent[]
  metrics?: RunMetrics
  isThinking: boolean
  startedAt?: number
  completedAt?: number
}

export function ThinkingProcess({
  tools = [],
  events = [],
  metrics,
  isThinking,
  startedAt,
  completedAt,
}: ThinkingProcessProps) {
  const [open, setOpen] = useState(false)
  const [userToggled, setUserToggled] = useState(false)

  const hasDetails = tools.length > 0 || events.length > 0

  const durationMs = useMemo(() => {
    const metricDuration = typeof metrics?.duration_ms === 'number' ? metrics.duration_ms : undefined
    if (metricDuration && metricDuration > 0) return metricDuration
    if (startedAt && completedAt && completedAt >= startedAt) return completedAt - startedAt
    return undefined
  }, [metrics?.duration_ms, startedAt, completedAt])

  const durationLabel = useMemo(() => {
    if (!durationMs || durationMs <= 0) return ''
    const seconds = Math.max(1, Math.round(durationMs / 1000))
    return `${seconds}s`
  }, [durationMs])

  const stepCount = useMemo(() => {
    if (tools.length > 0) return tools.length
    const stepTypes = new Set([
      'search',
      'tool',
      'tool_start',
      'tool_result',
      'tool_error',
      'screenshot',
      'research_node_start',
      'research_node_complete',
    ])
    return events.filter((e) => stepTypes.has(e.type)).length
  }, [tools.length, events])

  const displayEvents = useMemo(() => {
    const filtered = events.filter((e) => e.type !== 'done')
    return filtered.slice(-60)
  }, [events])

  useEffect(() => {
    if (userToggled) return
    if (isThinking) setOpen(true)
    else setOpen(false)
  }, [isThinking, userToggled])

  if (!hasDetails && !isThinking) return null

  const headerText = isThinking
    ? `Thinking…${stepCount ? ` · ${stepCount} steps` : ''}`
    : `Thought${durationLabel ? ` for ${durationLabel}` : ''}${stepCount ? ` · ${stepCount} steps` : ''}`

  const toggle = () => {
    if (!hasDetails) return
    setUserToggled(true)
    setOpen((v) => !v)
  }

  return (
    <div className="w-full my-2">
      <button
        type="button"
        onClick={toggle}
        className={cn(
          'group inline-flex items-center gap-2 rounded-full px-3 py-1.5',
          'text-sm text-muted-foreground hover:text-foreground',
          'hover:bg-muted/40 transition-colors duration-150',
          !hasDetails && 'cursor-default hover:bg-transparent'
        )}
        aria-expanded={open}
      >
        <span
          className={cn(
            'flex h-4 w-4 items-center justify-center',
            isThinking ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {isThinking ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
        </span>
        <span className="font-medium">{headerText}</span>
        {hasDetails && (
          <ChevronDown
            className={cn(
              'h-4 w-4 transition-transform duration-200 ease-out',
              open ? 'rotate-180' : 'rotate-0'
            )}
          />
        )}
      </button>

      {hasDetails && (
        <div
          className="grid transition-[grid-template-rows] duration-200 ease-out"
          style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="mt-2 pl-4 ml-2 border-l border-border/60 text-sm text-muted-foreground">
              <div className="space-y-2 py-1">
                {displayEvents.length > 0 ? (
                  displayEvents.map((ev) => <EventRow key={ev.id} ev={ev} />)
                ) : (
                  <FallbackTools tools={tools} />
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EventRow({ ev }: { ev: ProcessEvent }) {
  const kind = ev.type

  if (kind === 'status') {
    return (
      <div className="flex items-start gap-2">
        <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
        <div className="min-w-0">
          <div className="truncate">{String(ev.data?.text || 'Working…')}</div>
        </div>
      </div>
    )
  }

  if (kind === 'search') {
    const query = String(ev.data?.query || '').trim()
    const provider = String(ev.data?.provider || '').trim()
    const count = ev.data?.count
    return (
      <div className="flex items-start gap-2">
        <Search className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Search</span>
            {query ? <span className="ml-2 font-mono text-[12px]">{query}</span> : null}
          </div>
          <div className="text-xs text-muted-foreground">
            {[provider || null, typeof count === 'number' ? `${count} results` : null]
              .filter(Boolean)
              .join(' · ')}
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'screenshot') {
    const pageUrl = String(ev.data?.page_url || ev.data?.pageUrl || '').trim()
    const action = String(ev.data?.action || '').trim()
    return (
      <div className="flex items-start gap-2">
        <ImageIcon className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Screenshot</span>
            {action ? <span className="ml-2">{action}</span> : null}
          </div>
          {pageUrl ? <div className="truncate font-mono text-xs">{pageUrl}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'tool' || kind === 'tool_start' || kind === 'tool_result' || kind === 'tool_error') {
    const toolName = String(ev.data?.name || ev.data?.tool || '').trim() || 'tool'
    const status = String(ev.data?.status || '').trim()
    const args = ev.data?.args
    const query = String(ev.data?.query || args?.query || '').trim()
    const url = String(args?.url || ev.data?.url || ev.data?.page_url || '').trim()

    const hint = query || url

    return (
      <div className="flex items-start gap-2">
        <Wrench className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground/80 truncate">{toolName}</span>
            {status ? (
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {status}
              </span>
            ) : null}
          </div>
          {hint ? <div className="truncate font-mono text-xs">{hint}</div> : null}
        </div>
      </div>
    )
  }

  // Fallback: show type name only (keeps UI stable as backend adds new event kinds)
  return (
    <div className="flex items-start gap-2">
      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
      <div className="min-w-0">
        <div className="truncate font-mono text-xs">{kind}</div>
      </div>
    </div>
  )
}

function FallbackTools({ tools }: { tools: ToolInvocation[] }) {
  if (!tools.length) {
    return <div className="text-xs text-muted-foreground">No process details.</div>
  }
  return (
    <div className="space-y-2">
      {tools.slice(-20).map((tool) => (
        <div key={tool.toolCallId} className="flex items-start gap-2">
          <Wrench className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate font-medium text-foreground/80">{tool.toolName}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {tool.state}
              </span>
            </div>
            {tool.args?.query ? (
              <div className="truncate font-mono text-xs">{String(tool.args.query)}</div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  )
}
