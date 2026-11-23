'use client'

import React, { useEffect, useMemo, useState } from 'react'
import {
  ChevronDown,
  Loader2,
  CheckCircle2,
  Search,
  Wrench,
  Image as ImageIcon,
  Sparkles,
  ListTodo,
  TreePine,
  ShieldCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Artifact, ProcessEvent, RunMetrics, ToolInvocation } from '@/types/chat'
import { getArtifactDownloadUrl } from '@/lib/api'

interface ThinkingProcessProps {
  tools?: ToolInvocation[]
  artifacts?: Artifact[]
  events?: ProcessEvent[]
  metrics?: RunMetrics
  isThinking: boolean
  startedAt?: number
  completedAt?: number
}

export function ThinkingProcess({
  tools = [],
  artifacts = [],
  events = [],
  metrics,
  isThinking,
  startedAt,
  completedAt,
}: ThinkingProcessProps) {
  const [open, setOpen] = useState(false)
  const [userToggled, setUserToggled] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const hasDetails = tools.length > 0 || events.length > 0

  useEffect(() => {
    if (!isThinking) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [isThinking])

  const durationMs = useMemo(() => {
    const metricDuration = typeof metrics?.duration_ms === 'number' ? metrics.duration_ms : undefined
    if (metricDuration && metricDuration > 0) return metricDuration
    if (!startedAt) return undefined

    const end = isThinking ? now : completedAt
    if (typeof end === 'number' && end >= startedAt) return end - startedAt
    return undefined
  }, [metrics?.duration_ms, startedAt, completedAt, isThinking, now])

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
    const thoughts = events.filter((e) => e.type === 'thinking').slice(-3)
    const tail = events
      .filter((e) => e.type !== 'done' && e.type !== 'thinking' && (e.type !== 'tool' || tools.length === 0))
      .slice(-60)

    return [...thoughts, ...tail].sort((a, b) => a.timestamp - b.timestamp)
  }, [events, tools.length])

  useEffect(() => {
    if (userToggled) return
    if (isThinking) setOpen(true)
    else setOpen(false)
  }, [isThinking, userToggled])

  if (!hasDetails && !isThinking) return null

  const headerText = isThinking
    ? `Thinking…${durationLabel ? ` · ${durationLabel}` : ''}${stepCount ? ` · ${stepCount} steps` : ''}`
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
          inert={!open}
        >
          <div className="overflow-hidden">
            <div className="mt-2 pl-4 ml-2 border-l border-border/60 text-sm text-muted-foreground">
              <div className="space-y-2 py-1">
                {tools.length > 0 && <ToolRows tools={tools} artifacts={artifacts} />}
                {displayEvents.map((ev) => <EventRow key={ev.id} ev={ev} />)}
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

  if (kind === 'thinking') {
    const text = String(ev.data?.text || '').trim()
    if (!text) return null
    return (
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="whitespace-pre-wrap break-words text-[13px] leading-6 text-foreground/80">
            {text}
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'task_update') {
    const title = String(ev.data?.title || '').trim()
    const status = String(ev.data?.status || '').trim()
    const progress = ev.data?.progress
    const label = title || String(ev.data?.id || 'task')

    return (
      <div className="flex items-start gap-2">
        <ListTodo className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Task</span>
            <span className="ml-2">{label}</span>
            {status ? (
              <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {status}
              </span>
            ) : null}
          </div>
          {typeof progress === 'number' ? (
            <div className="text-xs text-muted-foreground">{Math.round(progress)}%</div>
          ) : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_node_start') {
    const nodeId = String(ev.data?.node_id || ev.data?.nodeId || '').trim()
    const topic = String(ev.data?.topic || '').trim()
    const epoch = ev.data?.epoch
    const depth = ev.data?.depth

    const subtitle = [
      typeof epoch === 'number' ? `epoch ${epoch}` : null,
      typeof depth === 'number' ? `depth ${depth}` : null,
    ]
      .filter(Boolean)
      .join(' · ')

    return (
      <div className="flex items-start gap-2">
        <TreePine className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Research start</span>
            {nodeId ? <span className="ml-2 font-mono text-[12px]">{nodeId}</span> : null}
          </div>
          {subtitle ? <div className="text-xs text-muted-foreground">{subtitle}</div> : null}
          {topic ? <div className="truncate text-xs text-muted-foreground">{topic}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_node_complete') {
    const nodeId = String(ev.data?.node_id || ev.data?.nodeId || '').trim()
    const epoch = ev.data?.epoch
    const summary = String(ev.data?.summary || '').trim()

    const subtitle = typeof epoch === 'number' ? `epoch ${epoch}` : ''

    return (
      <div className="flex items-start gap-2">
        <CheckCircle2 className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Research done</span>
            {nodeId ? <span className="ml-2 font-mono text-[12px]">{nodeId}</span> : null}
            {subtitle ? <span className="ml-2 text-xs text-muted-foreground">{subtitle}</span> : null}
          </div>
          {summary ? (
            <div className="line-clamp-2 text-xs text-muted-foreground">{summary}</div>
          ) : null}
        </div>
      </div>
    )
  }

  if (kind === 'quality_update') {
    const stage = String(ev.data?.stage || '').trim()
    const epoch = ev.data?.epoch
    const score =
      typeof ev.data?.query_coverage_score === 'number'
        ? ev.data.query_coverage_score
        : typeof ev.data?.citation_coverage_score === 'number'
          ? ev.data.citation_coverage_score
          : typeof ev.data?.citation_coverage === 'number'
            ? ev.data.citation_coverage
            : undefined
    const scorePct = typeof score === 'number' ? `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%` : ''

    return (
      <div className="flex items-start gap-2">
        <ShieldCheck className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Quality</span>
            {typeof epoch === 'number' ? <span className="ml-2 text-xs">epoch {epoch}</span> : null}
            {stage ? <span className="ml-2 text-xs text-muted-foreground">{stage}</span> : null}
            {scorePct ? <span className="ml-2 font-mono text-[12px]">{scorePct}</span> : null}
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'research_tree_update') {
    return (
      <div className="flex items-start gap-2">
        <TreePine className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Research tree updated</span>
          </div>
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

function ToolRows({ tools, artifacts }: { tools: ToolInvocation[]; artifacts: Artifact[] }) {
  return (
    <div className="space-y-2">
      {tools.slice(-20).map((tool) => {
        const artifact = artifacts.find(({ tool_call_id }) => tool_call_id === tool.toolCallId)
        const summary = artifact?.content ?? (typeof tool.result === 'string' ? tool.result : null)
        const downloadUrl = getArtifactDownloadUrl(artifact?.download_url)
        return (
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
            {summary && <p className="line-clamp-3 whitespace-pre-wrap break-words text-xs">{summary}</p>}
            {downloadUrl && <a className="text-xs text-primary underline" href={downloadUrl} download>Download full output</a>}
          </div>
        </div>
        )
      })}
    </div>
  )
}
