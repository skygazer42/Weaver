'use client'

import React, { useId } from 'react'
import { Boxes, ChevronDown, GitFork, LibraryBig, Monitor, PanelRight, Terminal } from 'lucide-react'
import { ArtifactsPanel } from './ArtifactsPanel'
import { ResearchGraphView } from './ResearchGraphView'
import { SourcesPanelView } from './SourcesPanelView'
import { BrowserViewer } from './BrowserViewer'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/lib/i18n/i18n-context'
import type { BrowserDockMode, ResearchStudioData, StudioTab } from '@/lib/researchStudio'
import { cn } from '@/lib/utils'

const tabs = [
  { id: 'graph', label: 'studioGraph', icon: GitFork },
  { id: 'artifacts', label: 'studioArtifacts', icon: Boxes },
  { id: 'sources', label: 'studioSources', icon: LibraryBig },
  { id: 'live', label: 'studioLive', icon: Monitor },
] as const

interface ResearchStudioPanelProps {
  studio: ResearchStudioData
  activeTab: StudioTab
  onTabChange: (tab: StudioTab) => void
  showHeader?: boolean
  threadId?: string | null
  browserDockMode?: BrowserDockMode
  onUndock?: () => void
  onDock?: () => void
  citation?: { index: number }
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

export function ResearchStudioRail({ studio, activeTab, onTabChange, threadId }: ResearchStudioPanelProps) {
  const { t } = useI18n()
  return (
    <div className="flex flex-col items-center gap-1.5 border-t border-border pt-2">
      {(threadId ? tabs : tabs.slice(0, 3)).map(({ id, label, icon: Icon }) => (
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

export function ResearchStudioPanel({ studio, activeTab, onTabChange, showHeader = true, threadId,
  browserDockMode = 'docked', onUndock, onDock, citation }: ResearchStudioPanelProps) {
  const { t } = useI18n()
  const idPrefix = useId()
  const visibleTabs = threadId ? tabs : tabs.slice(0, 3)
  const counts = { graph: studio.tree?.total_nodes ?? studio.mindMap?.total_nodes ?? 0, artifacts: studio.artifacts.length, sources: studio.sources.length, live: 0 }

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
        className={cn('grid shrink-0 border-b border-border bg-card px-2', threadId ? 'grid-cols-4' : 'grid-cols-3')}
        onKeyDown={event => {
          const index = visibleTabs.findIndex(tab => tab.id === activeTab)
          const next = {
            ArrowRight: (index + 1) % visibleTabs.length,
            ArrowLeft: (index + visibleTabs.length - 1) % visibleTabs.length,
            Home: 0,
            End: visibleTabs.length - 1,
          }[event.key]
          if (next === undefined) return
          event.preventDefault()
          onTabChange(visibleTabs[next].id)
          event.currentTarget.querySelectorAll('button')[next]?.focus()
        }}
      >
        {visibleTabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            id={`${idPrefix}-${id}-tab`}
            type="button"
            role="tab"
            data-studio-tab={id}
            tabIndex={id === activeTab ? 0 : -1}
            aria-selected={id === activeTab}
            aria-controls={`${idPrefix}-${id}-panel`}
            onClick={() => onTabChange(id)}
            className={cn(
              'flex h-11 min-w-0 items-center justify-center gap-1 border-b-2 border-transparent px-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50',
              id === activeTab && 'border-primary text-primary hover:text-primary'
            )}
          >
            <Icon aria-hidden="true" className="hidden size-3.5 shrink-0 min-[380px]:block" />
            <span className="truncate">{t(label)}</span>
            {counts[id] > 0 && <span className={cn('hidden rounded-sm bg-surface-subtle px-1 text-[10px] leading-4 tabular-nums min-[430px]:inline', id === activeTab && 'bg-primary/10')}>{counts[id] > 99 ? '99+' : counts[id]}</span>}
            {id === 'graph' && studio.isResearchActive && <LiveDot />}
          </button>
        ))}
      </div>

      {visibleTabs.map(({ id, icon: Icon }) => (
        <div
          key={id}
          id={`${idPrefix}-${id}-panel`}
          role="tabpanel"
          aria-labelledby={`${idPrefix}-${id}-tab`}
          hidden={id !== activeTab}
          className="min-h-0 flex-1 overflow-hidden"
        >
          {id === 'graph' && (studio.tree || studio.mindMap) && <ResearchGraphView key={studio.researchId} tree={studio.tree} mindMap={studio.mindMap} telemetry={studio.telemetry} />}
          {id === 'sources' && <SourcesPanelView sources={studio.sources} domains={studio.domains} media={studio.media} citation={citation} />}
          {id === 'artifacts' && id === activeTab && counts.artifacts > 0 && <ArtifactsPanel artifacts={studio.artifacts} threadId={threadId} embedded />}
          {id === 'live' && id === activeTab && threadId && <LiveComputer threadId={threadId} dockMode={browserDockMode}
            outputs={studio.artifacts.filter(artifact => artifact.type === 'tool_output')} onUndock={onUndock} onDock={onDock} />}
          {id === activeTab && (id === 'graph' || id === 'artifacts') && counts[id] === 0 && (
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

function LiveComputer({ threadId, dockMode, onUndock, onDock, outputs }: {
  threadId: string
  dockMode: BrowserDockMode
  onUndock?: () => void
  onDock?: () => void
  outputs: ResearchStudioData['artifacts']
}) {
  const { t } = useI18n()
  return (
    <div className="h-full space-y-3 overflow-y-auto overscroll-contain p-3.5">
      {dockMode === 'docked' ? (
        <BrowserViewer threadId={threadId} mode="stream" embedded alwaysShow onUndock={onUndock} />
      ) : (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2">
          <p className="text-xs text-muted-foreground">{t('studioBrowserFloating')}</p>
          <Button type="button" variant="outline" size="sm" onClick={onDock} className="h-8 shrink-0 gap-1.5 px-2 text-xs">
            <PanelRight aria-hidden="true" className="size-3.5" />{t('studioDockBrowser')}
          </Button>
        </div>
      )}
      {outputs.length > 0 && (
        <details className="group rounded-lg border border-border bg-card">
          <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-md px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
            <Terminal aria-hidden="true" className="size-3.5 text-muted-foreground" />
            {t('studioExecutionConsole')}
            <span className="font-mono text-[11px] text-muted-foreground">{outputs.length}</span>
            <ChevronDown aria-hidden="true" className="ml-auto size-3.5 text-muted-foreground group-open:rotate-180" />
          </summary>
          <div className="max-h-60 divide-y divide-border overflow-auto overscroll-contain border-t border-border bg-surface-subtle">
            {outputs.map(artifact => (
              <div key={artifact.id} className="space-y-1.5 px-3 py-2.5">
                <p className="break-words text-xs font-medium text-foreground">{artifact.title}</p>
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-5 text-muted-foreground">{artifact.content}</pre>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
