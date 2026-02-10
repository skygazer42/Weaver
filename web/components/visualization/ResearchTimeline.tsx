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
      return <CheckCircle2 className="h-5 w-5 text-green-500" />
    case 'in_progress':
      return <Clock className="h-5 w-5 text-blue-500 animate-pulse" />
    case 'failed':
      return <AlertCircle className="h-5 w-5 text-red-500" />
    default:
      return <Circle className="h-5 w-5 text-muted-foreground" />
  }
}

function getStatusColor(status: TimelineStep['status']) {
  switch (status) {
    case 'completed':
      return 'from-green-500/20 to-green-500/5'
    case 'in_progress':
      return 'from-blue-500/20 to-blue-500/5'
    case 'failed':
      return 'from-red-500/20 to-red-500/5'
    default:
      return 'from-muted/20 to-muted/5'
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
              ? "bg-gradient-to-b from-green-500/50 to-blue-500/50"
              : "bg-muted/30"
          )}
        />
      )}

      {/* Step Card */}
      <div
        className={cn(
          "relative flex gap-3 p-3 rounded-xl transition-all duration-300",
          "bg-gradient-to-r",
          getStatusColor(step.status),
          step.status === 'in_progress' && "animate-pulse-glow"
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
              onClick={() => onToggleExpand(step.id)}
              className="flex items-center gap-1 mt-2 text-xs text-blue-500 hover:text-blue-600 transition-colors"
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
            <div className="mt-2 space-y-1.5 animate-fade-in">
              {step.sources!.map((source, idx) => (
                <a
                  key={idx}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 p-2 rounded-lg bg-background/50 hover:bg-background/80 transition-colors group"
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

