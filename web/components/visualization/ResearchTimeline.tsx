'use client'

import React, { memo, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { CheckCircle2, Circle, Clock, AlertCircle, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'

export interface TimelineStep {
  id: string
  title: string
  description?: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  timestamp?: string
  sources?: Array<{
    title: string
    url: string
    provider?: string
  }>
}

// Memoized status icon getter
function getStatusIcon(status: TimelineStep['status']) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
    case 'in_progress':
      return <Clock className="h-5 w-5 text-primary" />
    case 'failed':
      return <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
    default:
      return <Circle className="h-5 w-5 text-muted-foreground" />
  }
}

function getStatusCardClasses(status: TimelineStep['status']) {
  switch (status) {
    case 'completed':
      return 'border-l-green-500 bg-green-500/5'
    case 'in_progress':
      return 'border-l-primary bg-primary/5'
    case 'failed':
      return 'border-l-red-500 bg-red-500/5'
    default:
      return 'border-l-border bg-card'
  }
}

// Memoized individual timeline step — prevents re-rendering all steps
// when only one step changes status
const TimelineStepItem = memo(function TimelineStepItem({
  step,
  isLast,
  isExpanded,
  onToggleExpand,
}: {
  step: TimelineStep
  isLast: boolean
  isExpanded: boolean
  onToggleExpand: (id: string) => void
}) {
  const hasSources = step.sources && step.sources.length > 0

  return (
    <div className="relative">
      {/* Connecting Line */}
      {!isLast && (
        <div
          className={cn(
            "absolute left-[11px] top-8 w-0.5 h-full -translate-x-1/2",
            step.status === 'completed'
              ? "bg-green-500/40"
              : "bg-border/60"
          )}
        />
      )}

      {/* Step Card */}
      <div
        className={cn(
          "relative flex gap-3 p-3 rounded-xl border border-border/60 border-l-4 transition-colors duration-200",
          getStatusCardClasses(step.status),
        )}
      >
        {/* Status Icon */}
        <div className="flex-shrink-0 pt-0.5">
          {getStatusIcon(step.status)}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="font-medium text-sm truncate">{step.title}</h4>
            {step.timestamp && (
              <span className="text-xs text-muted-foreground">
                {step.timestamp}
              </span>
            )}
          </div>

          {step.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
              {step.description}
            </p>
          )}

          {/* Sources Toggle */}
          {hasSources && (
            <button
              type="button"
              onClick={() => onToggleExpand(step.id)}
              className="flex items-center gap-1 mt-2 text-xs text-primary hover:text-primary/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"
            >
              {isExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              {step.sources!.length} sources
            </button>
          )}

          {/* Expanded Sources */}
          {isExpanded && hasSources && (
            <div className="mt-2 space-y-1.5">
              {step.sources!.map((source, idx) => (
                <a
                  key={idx}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 p-2 rounded-lg border border-border/60 bg-background hover:bg-accent transition-colors group"
                >
                  <span className="flex-1 text-xs truncate">
                    {source.title}
                  </span>
                  {source.provider && (
                    <span className="source-badge">
                      {source.provider}
                    </span>
                  )}
                  <ExternalLink className="h-3 w-3 text-muted-foreground group-hover:text-foreground" />
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
})

interface ResearchTimelineProps {
  steps: TimelineStep[]
  className?: string
}

export function ResearchTimeline({ steps, className }: ResearchTimelineProps) {
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set())

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }, [])

  return (
    <div className={cn("space-y-1", className)}>
      {steps.map((step, index) => (
        <TimelineStepItem
          key={step.id}
          step={step}
          isLast={index === steps.length - 1}
          isExpanded={expandedIds.has(step.id)}
          onToggleExpand={toggleExpand}
        />
      ))}
    </div>
  )
}
