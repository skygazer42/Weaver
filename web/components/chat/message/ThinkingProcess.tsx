'use client'

import React, { useEffect, useId, useMemo, useState } from 'react'
import {
  CheckCircle2,
  ChevronDown,
  FileText,
  Globe,
  Loader2,
  Search,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Artifact, ProcessEvent, RunMetrics, ToolInvocation } from '@/types/chat'
import { getArtifactDownloadUrl } from '@/lib/api'
import { normalizeThinkingProcess, type ThinkingStep } from '@/lib/thinkingProcess'
import { useI18n } from '@/lib/i18n/i18n-context'

interface ThinkingProcessProps {
  tools?: ToolInvocation[]
  artifacts?: Artifact[]
  events?: ProcessEvent[]
  metrics?: RunMetrics
  isThinking: boolean
  startedAt?: number
  completedAt?: number
}

const TASK_STATE_LABELS = {
  pending: 'taskPending',
  running: 'taskRunning',
  completed: 'taskCompleted',
  failed: 'taskFailed',
  cancelled: 'taskCancelled',
} as const

function formatMessage(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce(
    (message, [key, value]) => message.replaceAll(`{${key}}`, String(value)),
    template,
  )
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
  const { t } = useI18n()
  const detailsId = useId()
  const [openOverride, setOpenOverride] = useState<boolean | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const normalized = useMemo(
    () => normalizeThinkingProcess({ events, tools, artifacts }),
    [artifacts, events, tools],
  )
  const hasDetails = normalized.stepCount > 0
  const open = openOverride ?? isThinking

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
  }, [completedAt, isThinking, metrics?.duration_ms, now, startedAt])

  const durationLabel = durationMs && durationMs > 0
    ? formatMessage(t('thinkingDuration'), { seconds: Math.max(1, Math.round(durationMs / 1000)) })
    : ''

  if (!hasDetails && !isThinking && !durationLabel && tools.length === 0 && events.length === 0 && artifacts.length === 0) return null

  const stepCount = normalized.stepCount
  const baseHeader = isThinking
    ? [t('thinkingInProgress'), durationLabel].filter(Boolean).join(' · ')
    : durationLabel
      ? formatMessage(t('thoughtFor'), { duration: durationLabel })
      : t('thinkingComplete')
  const stepLabel = stepCount
    ? formatMessage(t(stepCount === 1 ? 'thinkingStep' : 'thinkingSteps'), { count: stepCount })
    : ''
  const headerText = [baseHeader, stepLabel].filter(Boolean).join(' · ')
  const Header = hasDetails ? 'button' : 'div'

  const toggle = () => {
    if (hasDetails) setOpenOverride(!open)
  }

  return (
    <div className="my-2 w-full overflow-hidden rounded-xl border border-border/70 bg-surface-subtle/75 [&_svg]:shrink-0">
      <Header
        type={hasDetails ? 'button' : undefined}
        onClick={hasDetails ? toggle : undefined}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left',
          'text-sm text-muted-foreground transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset',
          hasDetails && 'cursor-pointer hover:bg-accent/40 hover:text-foreground active:bg-accent/60',
        )}
        aria-expanded={hasDetails ? open : undefined}
        aria-controls={hasDetails ? detailsId : undefined}
      >
        <span className={cn('flex h-4 w-4 items-center justify-center', isThinking ? 'text-primary' : 'text-muted-foreground')}>
          {isThinking ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
        </span>
        <span className="flex-1 text-xs font-medium tabular-nums">{headerText}</span>
        {hasDetails ? (
          <ChevronDown
            className={cn('h-4 w-4 transition-transform duration-200 ease-out', open ? 'rotate-180' : 'rotate-0')}
            aria-hidden="true"
          />
        ) : null}
      </Header>

      {hasDetails ? (
        <div
          id={detailsId}
          className="grid transition-[grid-template-rows] duration-200 ease-out"
          style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
          inert={!open}
        >
          <div className="overflow-hidden">
            <div className="mx-4 mb-4 mt-1 border-l border-border/70 pl-4 text-sm text-muted-foreground">
              <div className="space-y-3 py-1">
                {normalized.steps.map((step) => <TimelineRow key={step.id} step={step} />)}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function TimelineRow({ step }: { step: ThinkingStep }) {
  const { t } = useI18n()
  const Icon = step.kind === 'search'
    ? Search
    : step.kind === 'reading'
      ? Globe
      : step.kind === 'artifact'
        ? FileText
        : step.kind === 'milestone' || step.kind === 'quality'
          ? CheckCircle2
          : Sparkles

  const progress = step.progress !== undefined ? `${Math.round(step.progress)}%` : ''
  const title = step.kind === 'search'
    ? t('searchSources')
    : step.kind === 'reading'
      ? step.count
        ? step.count === 1
          ? t('readReferencePage')
          : formatMessage(t('readReferencePages'), { count: step.count })
        : t('readPage')
      : step.kind === 'quality'
        ? t('qualityReview')
        : step.kind === 'task'
          ? t(step.state ? TASK_STATE_LABELS[step.state] : 'taskProgress')
          : step.kind === 'status'
            ? t('progressUpdate')
            : step.kind === 'artifact'
              ? step.title || t('outputArtifact')
              : step.kind === 'thinking'
                ? t('thinkingText')
                : step.phase === 'started'
                  ? t('researchStarted')
                  : step.phase === 'completed'
                    ? t('researchCompleted')
                    : t('researchUpdated')

  const detail = step.kind === 'thinking'
    ? step.text
    : step.kind === 'search'
      ? step.query
      : step.kind === 'reading'
        ? step.page
        : step.kind === 'artifact'
          ? step.summary
          : step.title || step.summary || step.text

  const downloadUrl = step.kind === 'artifact' ? getArtifactDownloadUrl(step.downloadUrl) : undefined

  return (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 h-4 w-4 text-muted-foreground/70" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="break-words font-medium text-foreground/80">{title}</span>
          {detail ? <span className="min-w-0 break-words text-[13px] leading-5 text-muted-foreground [overflow-wrap:anywhere]">{detail}</span> : null}
          {progress ? <span className="ml-auto shrink-0 font-mono text-xs tabular-nums text-muted-foreground">{progress}</span> : null}
        </div>
        {step.kind === 'thinking' ? null : step.summary && detail !== step.summary ? (
          <div className="line-clamp-2 text-xs text-muted-foreground">{step.summary}</div>
        ) : null}
        {downloadUrl ? (
          <a
            className="mt-1 inline-flex text-xs text-primary underline underline-offset-2"
            href={downloadUrl}
            download
          >
            {t('downloadFullOutput')}
          </a>
        ) : null}
      </div>
    </div>
  )
}
