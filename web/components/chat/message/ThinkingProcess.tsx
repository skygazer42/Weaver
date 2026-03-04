'use client'

import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Code,
  Globe,
  Loader2,
  Monitor,
  Wrench,
  XCircle,
} from '@/components/ui/icons'
import { cn } from '@/lib/utils'
import { ToolInvocation } from '@/types/chat'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { showError, showSuccess } from '@/lib/toast-utils'

interface ThinkingProcessProps {
  tools: ToolInvocation[]
  isThinking: boolean
}

type ToolCategory = 'search' | 'code' | 'browser' | 'other'

function normalizeToolName(name: string): string {
  return String(name || '').replace(/_/g, ' ').trim() || 'tool'
}

function categorizeTool(name: string): ToolCategory {
  const lowered = String(name || '').toLowerCase()
  if (lowered.includes('search')) return 'search'
  if (lowered.includes('python') || lowered.includes('code') || lowered.includes('execute')) return 'code'
  if (lowered.includes('browser') || lowered.includes('crawl') || lowered.startsWith('sb_browser_')) return 'browser'
  return 'other'
}

function scoreToolState(state: ToolInvocation['state']): number {
  if (state === 'running') return 0
  if (state === 'failed') return 1
  return 2
}

const CATEGORY_ICON: Record<ToolCategory, typeof Globe> = {
  search: Globe,
  code: Code,
  browser: Monitor,
  other: Wrench,
}

const CATEGORY_COLOR: Record<ToolCategory, string> = {
  search: 'text-emerald-500 dark:text-emerald-400',
  code: 'text-sky-500 dark:text-sky-400',
  browser: 'text-violet-500 dark:text-violet-400',
  other: 'text-slate-500 dark:text-slate-400',
}

const CATEGORY_BG: Record<ToolCategory, string> = {
  search: 'bg-emerald-500/10 dark:bg-emerald-500/15',
  code: 'bg-sky-500/10 dark:bg-sky-500/15',
  browser: 'bg-violet-500/10 dark:bg-violet-500/15',
  other: 'bg-slate-500/10 dark:bg-slate-500/15',
}

export function ThinkingProcess({ tools, isThinking }: ThinkingProcessProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [expandedToolId, setExpandedToolId] = useState<string | null>(null)

  const stats = useMemo(() => {
    const toolList = tools || []
    const byCategory: Record<ToolCategory, number> = { search: 0, code: 0, browser: 0, other: 0 }
    for (const tool of toolList) {
      byCategory[categorizeTool(tool.toolName)] += 1
    }
    const total = toolList.length
    const running = toolList.filter(t => t.state === 'running').length
    const completed = toolList.filter(t => t.state === 'completed').length
    const failed = toolList.filter(t => t.state === 'failed').length
    return { total, running, completed, failed, byCategory }
  }, [tools])

  const sortedTools = useMemo(() => {
    return [...(tools || [])].sort((a, b) => scoreToolState(a.state) - scoreToolState(b.state))
  }, [tools])

  const runningTool = useMemo(() => {
    return (tools || []).find(t => t.state === 'running') || null
  }, [tools])

  if (!tools || tools.length === 0) return null

  const isActive = stats.running > 0 || isThinking
  const hasFailed = stats.failed > 0

  return (
    <Card className="w-full my-3 overflow-hidden border-border/30 rounded-xl animate-fade-in">
      {/* Header */}
      <button
        type="button"
        className={cn(
          "w-full flex items-center justify-between gap-3 px-4 py-3 text-left",
          "cursor-pointer hover:bg-accent/30 transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        )}
        onClick={() => setIsOpen(prev => !prev)}
        aria-expanded={isOpen}
        aria-label={isOpen ? "Collapse activity" : "Expand activity"}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className={cn(
            "flex items-center justify-center size-7 rounded-lg transition-colors duration-200 shrink-0",
            isActive
              ? "bg-primary/10 text-primary"
              : hasFailed
                ? "bg-destructive/10 text-destructive"
                : "bg-muted/50 text-muted-foreground"
          )}>
            {isActive ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : hasFailed ? (
              <AlertTriangle className="w-3.5 h-3.5" />
            ) : (
              <Check className="w-3.5 h-3.5" />
            )}
          </div>

          <div className="flex flex-col gap-0 min-w-0">
            <span className="text-[13px] font-semibold text-foreground">
              Activity
              <span className="ml-2 text-xs font-normal text-muted-foreground tabular-nums">
                {stats.total} tools
              </span>
            </span>
            <span className="text-xs font-medium text-muted-foreground truncate">
              {runningTool
                ? normalizeToolName(runningTool.toolName)
                : hasFailed
                  ? `${stats.completed} done, ${stats.failed} failed`
                  : `${stats.completed} completed`}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {/* Compact category pills - desktop only */}
          {(['search', 'code', 'browser'] as const).map(cat => {
            const count = stats.byCategory[cat]
            if (count === 0) return null
            const CatIcon = CATEGORY_ICON[cat]
            return (
              <span
                key={cat}
                className={cn(
                  "hidden sm:inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium tabular-nums",
                  CATEGORY_BG[cat], CATEGORY_COLOR[cat]
                )}
              >
                <CatIcon className="h-2.5 w-2.5" />
                {count}
              </span>
            )
          })}

          <ChevronDown className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ml-1",
            isOpen && "rotate-180"
          )} />
        </div>
      </button>

      {/* Logs (Collapsible) */}
      {isOpen ? (
        <div className="border-t border-border/30 bg-muted/[0.03] transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]">
          <ScrollArea className="h-60">
            <div className="p-2.5 space-y-1">
              {sortedTools.map((tool) => (
                <LogItem
                  key={tool.toolCallId}
                  tool={tool}
                  isExpanded={expandedToolId === tool.toolCallId}
                  onToggleExpanded={() =>
                    setExpandedToolId(prev => (prev === tool.toolCallId ? null : tool.toolCallId))
                  }
                />
              ))}
            </div>
          </ScrollArea>
        </div>
      ) : null}
    </Card>
  )
}

function LogItem({
  tool,
  isExpanded,
  onToggleExpanded,
}: {
  tool: ToolInvocation
  isExpanded: boolean
  onToggleExpanded: () => void
}) {
  const isRunning = tool.state === 'running'
  const category = categorizeTool(tool.toolName)
  const query = typeof tool.args?.query === 'string' ? tool.args.query : null
  const url = typeof tool.args?.url === 'string' ? tool.args.url : null
  const path = typeof tool.args?.path === 'string' ? tool.args.path : null
  const command = typeof tool.args?.command === 'string' ? tool.args.command : null
  const code = typeof tool.args?.code === 'string' ? tool.args.code : null

  const copyPayload = (() => {
    if (command) return command
    if (code) return code
    if (url) return url
    if (query) return query
    if (path) return path
    try {
      return JSON.stringify(tool.args || {}, null, 2)
    } catch {
      return String(tool.args || '')
    }
  })()

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(copyPayload)
      showSuccess('Copied', 'tool-activity-copy')
    } catch {
      showError('Copy failed', 'tool-activity-copy-failed')
    }
  }

  const preview = (() => {
    if (query) return `"${query}"`
    if (url) return url
    if (path) return path
    if (command) return command
    if (code) return code.slice(0, 100) + (code.length > 100 ? '...' : '')

    const args = tool.args || {}
    const keys = Object.keys(args)
    if (keys.length === 0) return null
    try {
      const text = JSON.stringify(args)
      return text.length > 140 ? text.slice(0, 140) + '...' : text
    } catch {
      return null
    }
  })()

  const details = (() => {
    const args = tool.args || {}
    try {
      const text = JSON.stringify(args, null, 2)
      if (text && text !== '{}') return text
    } catch {
      // ignore
    }
    if (code) return code
    if (command) return command
    return null
  })()

  return (
    <div className="group rounded-lg hover:bg-accent/30 transition-colors duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]">
      <div
        role="button"
        tabIndex={0}
        className="flex gap-2.5 p-2 text-left cursor-pointer"
        onClick={onToggleExpanded}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggleExpanded()
          }
        }}
        aria-expanded={isExpanded}
        aria-label={isExpanded ? "Collapse tool details" : "Expand tool details"}
      >
        <div className="flex flex-col items-center gap-1 pt-1">
          <div
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              tool.state === 'failed'
                ? "bg-red-500"
                : isRunning
                  ? "bg-primary animate-pulse"
                  : CATEGORY_COLOR[category].replace('text-', 'bg-').replace(/dark:text-\S+/, '')
            )}
          />
          <div className="w-px h-full bg-border/30 group-last:hidden" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0 flex items-center gap-1.5">
              <span className="text-[11px] font-mono font-medium text-muted-foreground shrink-0">
                {normalizeToolName(tool.toolName)}
              </span>
              {preview ? (
                <span className="text-xs font-medium text-muted-foreground truncate">
                  {preview}
                </span>
              ) : null}
            </div>

            <div className="flex items-center gap-1 shrink-0">
              {isRunning ? (
                <Loader2 className="h-3 w-3 animate-spin text-primary" />
              ) : tool.state === 'failed' ? (
                <XCircle className="h-3 w-3 text-destructive" />
              ) : (
                <Check className="h-3 w-3 text-muted-foreground" />
              )}

              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="size-6 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/40 opacity-0 group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation()
                  handleCopy()
                }}
                aria-label="Copy tool details"
                title="Copy"
              >
                <ClipboardCopy className="h-3 w-3" />
              </Button>

              {isExpanded ? (
                <ChevronDown className="h-3 w-3 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
              )}
            </div>
          </div>
        </div>
      </div>

      {isExpanded && details ? (
        <div className="px-2 pb-2 pl-6">
          <div className="rounded-md border border-border/30 bg-muted/[0.03] p-2 font-mono text-xs font-medium leading-5 text-muted-foreground overflow-x-auto whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
            {details}
          </div>
        </div>
      ) : null}
    </div>
  )
}
