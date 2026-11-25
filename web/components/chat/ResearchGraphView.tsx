'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Check, Circle, CircleAlert, CircleMinus, ExternalLink, FileText, LoaderCircle, Minus, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/lib/i18n/i18n-context'
import { layoutResearchTree, parseStudioSourceUrl, type ResearchNode, type ResearchTree, type StudioTelemetry } from '@/lib/researchStudio'
import { cn } from '@/lib/utils'

const statusStyles = {
  pending: { icon: Circle, label: 'studioPending', color: 'bg-muted text-muted-foreground' },
  in_progress: { icon: LoaderCircle, label: 'studioInProgress', color: 'bg-primary/10 text-primary' },
  completed: { icon: Check, label: 'studioCompleted', color: 'bg-success-surface text-success' },
  failed: { icon: CircleAlert, label: 'studioFailed', color: 'bg-destructive-surface text-destructive' },
  skipped: { icon: CircleMinus, label: 'studioSkipped', color: 'bg-muted text-muted-foreground' },
} as const

function NodeStatus({ status }: { status: ResearchNode['status'] }) {
  const { t } = useI18n()
  const { icon: Icon, label, color } = statusStyles[status]
  return (
    <span className={cn('inline-flex max-w-full items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-medium leading-3', color)}>
      <Icon aria-hidden="true" className={cn('size-3 shrink-0', status === 'in_progress' && 'motion-safe:animate-spin')} />
      <span className="truncate">{t(label)}</span>
    </span>
  )
}

function Telemetry({ telemetry }: { telemetry: StudioTelemetry }) {
  const { t } = useI18n()
  const { completedNodes, totalNodes, totalSources, coveragePct, freshnessPct, uniqueDomains } = telemetry
  const metrics = [
    { label: t('studioNodesDone'), value: totalNodes === undefined ? undefined : `${completedNodes ?? 0}/${totalNodes}` },
    { label: t('studioSources'), value: totalSources },
    { label: t('studioCoverage'), value: coveragePct === undefined ? undefined : `${coveragePct}%` },
    { label: t('studioFreshness'), value: freshnessPct === undefined ? undefined : `${freshnessPct}%` },
    { label: t('studioDomains'), value: uniqueDomains },
  ].filter(({ value }) => value !== undefined)

  return (
    <dl aria-label={t('studioTelemetry')} className="flex shrink-0 divide-x divide-border rounded-md border border-border bg-card py-2.5">
      {metrics.map(({ label, value }) => (
        <div key={label} className="flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 text-center">
          <dt className="text-[11px] leading-4 text-muted-foreground">{label}</dt>
          <dd className="text-sm font-semibold leading-5 tabular-nums text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function NodeInspector({ node }: { node: ResearchNode }) {
  const { t } = useI18n()
  const sources = (node.sources ?? []).map(parseStudioSourceUrl).filter(url => url !== null)
  return (
    <section aria-label={t('studioInspector')} className="min-h-0 max-h-[min(37%,14rem)] shrink-0 space-y-3 overflow-y-auto rounded-lg border border-border bg-card p-3.5">
      <header className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-xs font-medium text-muted-foreground">{t('studioInspector')}</h3>
          <NodeStatus status={node.status} />
        </div>
        <p className="break-words text-sm font-semibold leading-5 text-foreground">
          {node.epoch !== undefined && <span className="mr-1.5 text-primary">{t('studioEpoch').replace('{count}', String(node.epoch))} ·</span>}
          {node.topic}
        </p>
      </header>
      {!!node.queries?.length && (
        <div>
          <h4 className="mb-1.5 text-xs font-medium text-foreground">{t('studioQueries')}</h4>
          <ul className="flex flex-wrap gap-1.5">
            {node.queries.map((query, index) => <li key={index} className="max-w-full break-words rounded bg-surface-subtle px-2 py-1 text-xs text-muted-foreground">{query}</li>)}
          </ul>
        </div>
      )}
      {node.summary_preview && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-foreground">{t('studioSummary')}</h4>
          <p className="whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground">{node.summary_preview}</p>
        </div>
      )}
      {sources.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-foreground">{t('studioSources')}</h4>
          <ul className="space-y-1">
            {sources.map((url, index) => (
              <li key={index}>
                <a href={url.href} target="_blank" rel="noopener noreferrer" title={url.href} className="flex min-w-0 items-center gap-1.5 rounded-sm text-xs leading-5 text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                  <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
                  <span className="truncate">{url.host}{url.pathname}{url.search}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      {!node.queries?.length && !node.summary_preview && sources.length === 0 && (
        <p className="text-xs leading-5 text-muted-foreground">{t('studioNoNodeDetails')}</p>
      )}
    </section>
  )
}

export function ResearchGraphView({ tree, telemetry }: { tree: ResearchTree; telemetry: StudioTelemetry }) {
  const { t } = useI18n()
  const [selectedId, setSelectedId] = useState<string>()
  const [zoom, setZoom] = useState<number>()
  const [viewportWidth, setViewportWidth] = useState(0)
  const viewport = useRef<HTMLDivElement>(null)
  const layout = useMemo(() => layoutResearchTree(tree), [tree])
  const selected = layout.nodes.find(({ node }) => node.id === selectedId)?.node
    ?? layout.nodes.find(({ node }) => node.id === tree.root_id)?.node
    ?? layout.nodes[0]?.node

  useEffect(() => {
    const element = viewport.current
    if (!element) return
    const observer = new ResizeObserver(() => setViewportWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  if (!selected) return null

  const activePath = new Set<string>([selected.id])
  const parents = new Map(layout.edges.map(edge => [edge.to, edge.from]))
  for (let parent = parents.get(selected.id); parent; parent = parents.get(parent)) activePath.add(parent)
  const fit = viewportWidth ? Math.max(0.75, Math.min(1, (viewportWidth - 2) / layout.width)) : 1
  const scale = zoom ?? fit
  const changeZoom = (step: number) => setZoom(Math.min(1.75, Math.max(0.5, Math.round((scale + step) * 100) / 100)))

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3.5">
      <Telemetry telemetry={telemetry} />
      <section aria-label={t('studioGraph')} className="flex min-h-36 max-h-[55dvh] flex-col overflow-hidden rounded-lg border border-border bg-surface-subtle">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border bg-card py-1 pl-3 pr-1.5">
          <h3 className="text-xs font-medium text-foreground">{t('studioTree')}</h3>
          <div role="group" aria-label={t('studioZoom')} className="flex items-center gap-0.5">
            <Button type="button" variant="ghost" size="icon" className="size-8" aria-label={t('studioZoomOut')} title={t('studioZoomOut')} onClick={() => changeZoom(-0.15)} disabled={scale <= 0.5}>
              <Minus aria-hidden="true" className="size-3.5" />
            </Button>
            <span className="min-w-8 text-center text-[11px] tabular-nums text-muted-foreground">{Math.round(scale * 100)}%</span>
            <Button type="button" variant="ghost" size="icon" className="size-8" aria-label={t('studioZoomIn')} title={t('studioZoomIn')} onClick={() => changeZoom(0.15)} disabled={scale >= 1.75}>
              <Plus aria-hidden="true" className="size-3.5" />
            </Button>
            <Button type="button" variant="ghost" size="sm" className="h-8 border-l border-border px-2 text-xs text-primary" aria-label={t('studioFitGraph')} title={t('studioFitGraph')} onClick={() => {
              setZoom(undefined)
              viewport.current?.scrollTo(0, 0)
            }}>
              {t('studioFit')}
            </Button>
          </div>
        </div>
        <div
          ref={viewport}
          tabIndex={0}
          role="region"
          aria-label={t('studioGraphCanvas')}
          className="overflow-auto overscroll-contain bg-[radial-gradient(circle,hsl(var(--muted-foreground)/0.25)_1px,transparent_1px)] bg-[length:14px_14px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50"
        >
          <div className="relative mx-auto overflow-hidden" style={{ width: layout.width * scale, height: layout.height * scale }}>
            <div className="absolute left-0 top-0 origin-top-left" style={{ width: layout.width, height: layout.height, transform: `scale(${scale})` }}>
              <svg aria-hidden="true" className="pointer-events-none absolute inset-0" width={layout.width} height={layout.height}>
                {layout.edges.map(({ from, to, path }) => {
                  const active = activePath.has(from) && activePath.has(to)
                  return <path key={to} d={path} fill="none" className={active ? 'stroke-primary' : 'stroke-muted-foreground/45'} strokeWidth={active ? 2 : 1.5} />
                })}
              </svg>
              {layout.nodes.map(({ node, x, y, width, height }) => (
                <button
                  key={node.id}
                  type="button"
                  aria-pressed={node.id === selected.id}
                  onClick={() => setSelectedId(node.id)}
                  title={node.topic}
                  style={{ left: x, top: y, width, height }}
                  className={cn(
                    'absolute flex flex-col items-start justify-between rounded-md border bg-card px-2 py-1.5 text-left shadow-xs transition-colors hover:border-primary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    node.id === selected.id ? 'border-primary ring-1 ring-primary/25' : activePath.has(node.id) ? 'border-primary/50' : 'border-border'
                  )}
                >
                  <div className="flex w-full items-center gap-1">
                    <NodeStatus status={node.status} />
                    {node.epoch !== undefined && <span aria-label={t('studioEpoch').replace('{count}', String(node.epoch))} className="ml-auto shrink-0 text-[10px] leading-3 tabular-nums text-muted-foreground">{node.epoch}</span>}
                  </div>
                  <span className="line-clamp-2 max-w-full break-words text-xs font-semibold leading-[15px] text-foreground">{node.topic}</span>
                  <span className="flex gap-1 text-[10px] font-medium leading-3 tabular-nums text-muted-foreground">
                    <span className="inline-flex items-center gap-0.5 rounded-sm bg-surface-subtle px-1 py-px" aria-label={t('studioFindingCount').replace('{count}', String(node.findings_count))} title={t('studioFindingCount').replace('{count}', String(node.findings_count))}>
                      <FileText aria-hidden="true" className="size-2.5" />{node.findings_count}
                    </span>
                    <span className="inline-flex items-center gap-0.5 rounded-sm bg-surface-subtle px-1 py-px" aria-label={t('studioSourceCount').replace('{count}', String(node.sources_count))} title={t('studioSourceCount').replace('{count}', String(node.sources_count))}>
                      <BookOpen aria-hidden="true" className="size-2.5" />{node.sources_count}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>
      <NodeInspector key={selected.id} node={selected} />
    </div>
  )
}
