'use client'

import React, { useId } from 'react'
import { Boxes, GitFork, LibraryBig } from 'lucide-react'
import { ArtifactsPanel } from './ArtifactsPanel'
import { ResearchGraphView } from './ResearchGraphView'
import { SourcesPanelView } from './SourcesPanelView'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/lib/i18n/i18n-context'
import type { ResearchStudioData, StudioTab } from '@/lib/researchStudio'
import { cn } from '@/lib/utils'

const tabs = [
  { id: 'graph', label: 'studioGraph', icon: GitFork },
  { id: 'artifacts', label: 'studioArtifacts', icon: Boxes },
  { id: 'sources', label: 'studioSources', icon: LibraryBig },
] as const

interface ResearchStudioPanelProps {
  studio: ResearchStudioData
  activeTab: StudioTab
  onTabChange: (tab: StudioTab) => void
  showHeader?: boolean
}

function LiveDot() {
  const { t } = useI18n()
  return (
    <span className="relative flex size-2 shrink-0" title={t('studioResearchActive')}>
      <span aria-hidden="true" className="absolute inset-0 rounded-full bg-primary/60 motion-safe:animate-ping" />
      <span aria-hidden="true" className="size-2 rounded-full bg-primary" />
      <span className="sr-only">{t('studioResearchActive')}</span>
    </span>
  )
}

export function ResearchStudioRail({ studio, activeTab, onTabChange }: ResearchStudioPanelProps) {
  const { t } = useI18n()
  return (
    <div className="flex flex-col items-center gap-1.5 border-t border-border pt-2">
      {tabs.map(({ id, label, icon: Icon }) => (
        <Button key={id} type="button" variant="ghost" size="icon" aria-label={t(label)} title={t(label)} onClick={() => onTabChange(id)}
          className={cn('relative size-9 text-muted-foreground', id === activeTab && 'bg-primary/10 text-primary')}
        >
          <Icon aria-hidden="true" className="size-[17px]" />
          {id === 'graph' && studio.isResearchActive && <span className="absolute right-1 top-1"><LiveDot /></span>}
        </Button>
      ))}
    </div>
  )
}

export function ResearchStudioPanel({ studio, activeTab, onTabChange, showHeader = true }: ResearchStudioPanelProps) {
  const { t } = useI18n()
  const idPrefix = useId()
  const counts = { graph: studio.tree?.total_nodes ?? 0, artifacts: studio.artifacts.length, sources: studio.sources.length }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {showHeader && (
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-card pl-4 pr-12">
          <GitFork aria-hidden="true" className="size-4 text-primary" />
          <h2 className="text-sm font-semibold tracking-tight text-foreground">{t('studioTitle')}</h2>
        </div>
      )}
      <div
        role="tablist"
        aria-label={t('studioTitle')}
        className="grid shrink-0 grid-cols-3 border-b border-border bg-card px-2"
        onKeyDown={event => {
          const index = tabs.findIndex(tab => tab.id === activeTab)
          const next = {
            ArrowRight: (index + 1) % tabs.length,
            ArrowLeft: (index + tabs.length - 1) % tabs.length,
            Home: 0,
            End: tabs.length - 1,
          }[event.key]
          if (next === undefined) return
          event.preventDefault()
          onTabChange(tabs[next].id)
          event.currentTarget.querySelectorAll('button')[next]?.focus()
        }}
      >
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            id={`${idPrefix}-${id}-tab`}
            type="button"
            role="tab"
            tabIndex={id === activeTab ? 0 : -1}
            aria-selected={id === activeTab}
            aria-controls={`${idPrefix}-${id}-panel`}
            onClick={() => onTabChange(id)}
            className={cn(
              'flex h-11 min-w-0 items-center justify-center gap-1.5 border-b-2 border-transparent px-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50 sm:text-sm',
              id === activeTab && 'border-primary text-primary hover:text-primary'
            )}
          >
            <Icon aria-hidden="true" className="hidden size-3.5 shrink-0 min-[380px]:block" />
            <span className="truncate">{t(label)}</span>
            {counts[id] > 0 && <span className={cn('rounded-sm bg-surface-subtle px-1 text-[10px] leading-4 tabular-nums', id === activeTab && 'bg-primary/10')}>{counts[id]}</span>}
            {id === 'graph' && studio.isResearchActive && <LiveDot />}
          </button>
        ))}
      </div>

      {tabs.map(({ id, icon: Icon }) => (
        <div
          key={id}
          id={`${idPrefix}-${id}-panel`}
          role="tabpanel"
          aria-labelledby={`${idPrefix}-${id}-tab`}
          hidden={id !== activeTab}
          className="min-h-0 flex-1 overflow-hidden"
        >
          {id === 'graph' && studio.tree && <ResearchGraphView key={studio.researchId} tree={studio.tree} telemetry={studio.telemetry} />}
          {id === 'sources' && <SourcesPanelView sources={studio.sources} domains={studio.domains} />}
          {id === 'artifacts' && id === activeTab && counts.artifacts > 0 && <ArtifactsPanel artifacts={studio.artifacts} embedded />}
          {id === activeTab && id !== 'sources' && counts[id] === 0 && (
            <div className="grid h-full place-content-center justify-items-center gap-2 p-6 text-center text-sm text-muted-foreground">
              <Icon aria-hidden="true" className="size-5" />
              <p>{t(id === 'graph' ? 'studioNoGraph' : 'studioNoArtifacts')}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
