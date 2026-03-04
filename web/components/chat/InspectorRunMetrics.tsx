'use client'

import { useMemo } from 'react'
import { RefreshCcw } from '@/components/ui/icons'
import { Button } from '@/components/ui/button'
import { LoadingSkeleton } from '@/components/ui/loading'
import { cn } from '@/lib/utils'
import { useRunMetrics } from '@/hooks/useRunMetrics'

function clampScore(value: unknown): number | null {
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return Math.max(0, Math.min(1, n))
}

function percent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${Math.round(value * 100)}%`
}

function formatDuration(durationMs: unknown): string {
  const ms = Number(durationMs)
  if (!Number.isFinite(ms) || ms < 0) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function countValues(map: unknown): number {
  if (!map || typeof map !== 'object') return 0
  return Object.values(map as Record<string, unknown>).reduce<number>((acc, value) => {
    const n = Number(value)
    return acc + (Number.isFinite(n) ? n : 0)
  }, 0)
}

export function InspectorRunMetrics({ threadId }: { threadId: string | null }) {
  const { metrics, isLoading, error, refresh } = useRunMetrics(threadId)

  const nodesStarted = useMemo(() => countValues(metrics?.nodes_started), [metrics?.nodes_started])
  const nodesCompleted = useMemo(() => countValues(metrics?.nodes_completed), [metrics?.nodes_completed])

  const evidence = metrics?.evidence_summary
  const citationCoverage = clampScore(evidence?.citation_coverage)
  const queryCoverage = clampScore(evidence?.query_coverage_score)
  const freshnessRatio30d = clampScore(evidence?.freshness_ratio_30d)

  if (!threadId) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/10 p-4">
        <div className="text-xs font-semibold text-foreground">No run metrics yet</div>
        <div className="mt-1 text-xs font-medium text-muted-foreground text-pretty">
          Start a chat/research run first, then metrics will appear here.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-foreground">Run metrics</div>
          <div className="text-[11px] font-medium text-muted-foreground truncate">
            {threadId}
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={refresh}
          disabled={isLoading}
          aria-label="Refresh run metrics"
          title="Refresh run metrics"
        >
          <RefreshCcw className={cn('h-4 w-4', isLoading && 'opacity-60')} />
        </Button>
      </div>

      {error ? (
        <div className="rounded-lg border border-border/60 bg-background p-3">
          <div className="text-xs font-semibold text-foreground">Failed to load metrics</div>
          <div className="mt-1 text-xs font-medium text-muted-foreground text-pretty">
            {error}
          </div>
          <div className="mt-3">
            <Button type="button" size="sm" variant="outline" onClick={refresh} disabled={isLoading}>
              Retry
            </Button>
          </div>
        </div>
      ) : null}

      {isLoading && !metrics ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <LoadingSkeleton className="h-14 rounded-lg" />
            <LoadingSkeleton className="h-14 rounded-lg" />
          </div>
          <LoadingSkeleton className="h-20 rounded-lg" />
        </div>
      ) : null}

      {!isLoading && metrics ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
              <div className="text-[11px] font-medium text-muted-foreground">Duration</div>
              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
                {formatDuration(metrics.duration_ms)}
              </div>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
              <div className="text-[11px] font-medium text-muted-foreground">Events</div>
              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
                {metrics.event_count}
              </div>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
              <div className="text-[11px] font-medium text-muted-foreground">Nodes</div>
              <div className="mt-0.5 text-xs font-medium tabular-nums text-foreground">
                {nodesStarted} started · {nodesCompleted} done
              </div>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
              <div className="text-[11px] font-medium text-muted-foreground">Status</div>
              <div className="mt-0.5 text-xs font-medium text-foreground">
                {metrics.cancelled ? 'Cancelled' : (metrics.errors?.length ? 'Completed (with errors)' : 'Completed')}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-foreground">Evidence summary</div>
                <div className="mt-1 text-[11px] font-medium text-muted-foreground text-pretty">
                  Best-effort metrics derived from deep research artifacts (citations, freshness, claim verification).
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] font-medium text-muted-foreground tabular-nums">
                  Cite {percent(citationCoverage)}
                </span>
                <span className="rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] font-medium text-muted-foreground tabular-nums">
                  Query {percent(queryCoverage)}
                </span>
                <span className="rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] font-medium text-muted-foreground tabular-nums">
                  Fresh {percent(freshnessRatio30d)}
                </span>
              </div>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
                <div className="text-[11px] font-medium text-muted-foreground">Sources</div>
                <div className="mt-0.5 text-xs font-medium text-foreground tabular-nums">
                  {evidence?.sources_count ?? 0}
                </div>
              </div>
              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
                <div className="text-[11px] font-medium text-muted-foreground">Unsupported claims</div>
                <div className="mt-0.5 text-xs font-medium text-foreground tabular-nums">
                  {evidence?.unsupported_claims_count ?? 0}
                </div>
              </div>
              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
                <div className="text-[11px] font-medium text-muted-foreground">Claim verifier</div>
                <div className="mt-0.5 text-xs font-medium text-foreground tabular-nums">
                  {typeof evidence?.claim_verifier_verified === 'number' ? evidence.claim_verifier_verified : '—'} verified ·{' '}
                  {typeof evidence?.claim_verifier_unsupported === 'number' ? evidence.claim_verifier_unsupported : '—'} unsupported ·{' '}
                  {typeof evidence?.claim_verifier_contradicted === 'number' ? evidence.claim_verifier_contradicted : '—'} contradicted
                </div>
              </div>
              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
                <div className="text-[11px] font-medium text-muted-foreground">Model / route</div>
                <div className="mt-0.5 text-xs font-medium text-foreground truncate" title={`${metrics.model} · ${metrics.route}`}>
                  {metrics.model} · {metrics.route || '—'}
                </div>
              </div>
            </div>

            {evidence?.freshness_warning ? (
              <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200 text-pretty">
                <span className="font-semibold">Warning:</span>{' '}
                {evidence.freshness_warning}
              </div>
            ) : null}

            {Array.isArray(metrics.errors) && metrics.errors.length ? (
              <div className="mt-3 rounded-lg border border-border/60 bg-muted/10 px-3 py-2 text-xs font-medium text-muted-foreground">
                <div className="font-semibold text-foreground">Errors</div>
                <ul className="mt-1 list-disc pl-4 space-y-1">
                  {metrics.errors.slice(0, 5).map((item, idx) => (
                    <li key={`${idx}-${item}`} className="break-words">
                      {item}
                    </li>
                  ))}
                  {metrics.errors.length > 5 ? (
                    <li className="text-muted-foreground">
                      …and {metrics.errors.length - 5} more
                    </li>
                  ) : null}
                </ul>
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
