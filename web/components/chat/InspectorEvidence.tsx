'use client'

import { useMemo, useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, Copy, ExternalLink, RefreshCcw } from '@/components/ui/icons'
import { Button } from '@/components/ui/button'
import { LoadingInline, LoadingSkeleton } from '@/components/ui/loading'
import { cn } from '@/lib/utils'
import { showError, showSuccess } from '@/lib/toast-utils'
import { useSessionEvidence } from '@/hooks/useSessionEvidence'
import { groupEvidencePassages } from '@/lib/evidence/normalizeEvidence'
import { getClaimStatusCounts, normalizeClaimStatus, type NormalizedClaimStatus } from '@/lib/evidence/normalizeClaims'
import { normalizeQualitySummary } from '@/lib/evidence/normalizeQualitySummary'

function safeDomain(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return ''
  }
}

function normalizePreview(raw: string, maxChars: number): string {
  const text = String(raw || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  if (text.length <= maxChars) return text
  return `${text.slice(0, Math.max(0, maxChars - 1))}…`
}

function clampScore(value: unknown): number | null {
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return Math.max(0, Math.min(1, n))
}

function percent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${Math.round(value * 100)}%`
}

function statusTone(status: NormalizedClaimStatus): string {
  if (status === 'verified') return 'bg-green-500/10 text-green-700 dark:text-green-300 border-green-500/20'
  if (status === 'unsupported') return 'bg-amber-500/10 text-amber-800 dark:text-amber-200 border-amber-500/20'
  if (status === 'contradicted') return 'bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/20'
  return 'bg-muted/30 text-muted-foreground border-border/60'
}

export function InspectorEvidence({ threadId }: { threadId: string | null }) {
  const { evidence, isLoading, error, refresh } = useSessionEvidence(threadId)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const [openClaims, setOpenClaims] = useState<Record<string, boolean>>({})
  const [claimFilter, setClaimFilter] = useState<'all' | NormalizedClaimStatus>('all')

  const pages = useMemo(() => {
    return groupEvidencePassages(evidence?.passages ?? [])
  }, [evidence?.passages])

  const claimCounts = useMemo(() => {
    return getClaimStatusCounts(evidence?.claims ?? [])
  }, [evidence?.claims])

  const filteredClaims = useMemo(() => {
    const claims = evidence?.claims ?? []
    if (claimFilter === 'all') return claims
    return claims.filter((claim) => normalizeClaimStatus((claim as any)?.status) === claimFilter)
  }, [evidence?.claims, claimFilter])

  const quality = useMemo(() => {
    const normalized = normalizeQualitySummary(evidence?.quality_summary)
    const citationCoverage = clampScore(
      (evidence?.quality_summary as any)?.citation_coverage ?? (evidence?.quality_summary as any)?.citation_coverage_score
    )
    return {
      ...normalized,
      citationCoverage,
      queryCoverageScore: typeof normalized.queryCoverageScore === 'number' ? clampScore(normalized.queryCoverageScore) : null,
      freshnessRatio30d: typeof normalized.freshnessRatio30d === 'number' ? clampScore(normalized.freshnessRatio30d) : null,
    }
  }, [evidence?.quality_summary])

  const fetchedMetaByUrl = useMemo(() => {
    const meta = new Map<string, { title?: string; retrievedAt?: string; method?: string }>()

    for (const item of evidence?.fetched_pages ?? []) {
      if (!item || typeof item !== 'object') continue
      const url = String(item.url ?? '').trim()
      if (!url || meta.has(url)) continue
      meta.set(url, {
        title: typeof item.title === 'string' ? item.title : undefined,
        retrievedAt: typeof item.retrieved_at === 'string' ? item.retrieved_at : undefined,
        method: typeof item.method === 'string' ? item.method : undefined,
      })
    }

    // Fallback: infer from passage metadata if fetched_pages is missing.
    for (const passage of evidence?.passages ?? []) {
      const url = String(passage?.url ?? '').trim()
      if (!url || meta.has(url)) continue
      meta.set(url, {
        title: typeof passage.page_title === 'string' ? passage.page_title : undefined,
        retrievedAt: typeof passage.retrieved_at === 'string' ? passage.retrieved_at : undefined,
        method: typeof passage.method === 'string' ? passage.method : undefined,
      })
    }

    return meta
  }, [evidence?.fetched_pages, evidence?.passages])

  const toggleGroup = useCallback((key: string) => {
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const toggleClaim = useCallback((key: string) => {
    setOpenClaims(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const copyText = useCallback(async (text: string) => {
    const value = String(text || '').trim()
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      showSuccess('Quote copied', 'evidence-quote-copy')
    } catch (err) {
      console.warn('[InspectorEvidence] clipboard copy failed:', err)
      showError('Failed to copy quote', 'evidence-quote-copy-error')
    }
  }, [])

  if (!threadId) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/10 p-4">
        <div className="text-xs font-semibold text-foreground">No evidence yet</div>
        <div className="mt-1 text-xs font-medium text-muted-foreground text-pretty">
          Start a chat to generate a session, then evidence passages will appear here.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-foreground">Evidence</div>
          <div className="text-[11px] font-medium text-muted-foreground truncate">
            {pages.length} pages · {(evidence?.passages?.length ?? 0)} passages
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={refresh}
          disabled={isLoading}
          aria-label="Refresh evidence"
          title="Refresh evidence"
        >
          <RefreshCcw className={cn('h-4 w-4', isLoading && 'opacity-60')} />
        </Button>
      </div>

      {error ? (
        <div className="rounded-lg border border-border/60 bg-background p-3">
          <div className="text-xs font-semibold text-foreground">Failed to load evidence</div>
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

      {isLoading && !evidence ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <LoadingSkeleton className="h-14 rounded-lg" />
            <LoadingSkeleton className="h-14 rounded-lg" />
          </div>
          <LoadingSkeleton className="h-20 rounded-lg" />
          <LoadingSkeleton className="h-20 rounded-lg" />
        </div>
      ) : null}

      {!isLoading && evidence ? (
        <>
	          <div className="grid grid-cols-2 gap-2">
	            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
	              <div className="text-[11px] font-medium text-muted-foreground">Sources</div>
	              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
	                {evidence.sources?.length ?? 0}
	              </div>
	            </div>
	            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
	              <div className="text-[11px] font-medium text-muted-foreground">Claims</div>
	              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
	                {evidence.claims?.length ?? 0}
	              </div>
	            </div>
	          </div>

	          <div className="rounded-lg border border-border/60 bg-background p-3">
	            <div className="flex items-start justify-between gap-3">
	              <div className="min-w-0">
	                <div className="text-xs font-semibold text-foreground">Quality</div>
	                <div className="mt-1 text-[11px] font-medium text-muted-foreground text-pretty">
	                  Query coverage, freshness, and budget signals captured during deep research.
	                </div>
	              </div>
	              <div className="flex items-center gap-1.5">
	                <span className="rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] font-medium text-muted-foreground tabular-nums">
	                  Query {percent(quality.queryCoverageScore)}
	                </span>
	                <span className="rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] font-medium text-muted-foreground tabular-nums">
	                  Fresh {percent(quality.freshnessRatio30d)}
	                </span>
	                {typeof quality.citationCoverage === 'number' ? (
	                  <span className="rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] font-medium text-muted-foreground tabular-nums">
	                    Cite {percent(quality.citationCoverage)}
	                  </span>
	                ) : null}
	              </div>
	            </div>

	            <div className="mt-3 grid grid-cols-2 gap-2">
	              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
	                <div className="text-[11px] font-medium text-muted-foreground">Time-sensitive</div>
	                <div className="mt-0.5 text-xs font-medium text-foreground">
	                  {quality.timeSensitive ? 'Yes' : 'No'}
	                </div>
	              </div>
	              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
	                <div className="text-[11px] font-medium text-muted-foreground">Budget stop</div>
	                <div className="mt-0.5 text-xs font-medium text-foreground truncate" title={quality.budgetStopReason || ''}>
	                  {quality.budgetStopReason || '—'}
	                </div>
	              </div>
	              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
	                <div className="text-[11px] font-medium text-muted-foreground">Elapsed</div>
	                <div className="mt-0.5 text-xs font-medium text-foreground tabular-nums">
	                  {typeof quality.elapsedSeconds === 'number' ? `${Math.round(quality.elapsedSeconds)}s` : '—'}
	                </div>
	              </div>
	              <div className="rounded-md border border-border/60 bg-muted/10 p-2">
	                <div className="text-[11px] font-medium text-muted-foreground">Tokens used</div>
	                <div className="mt-0.5 text-xs font-medium text-foreground tabular-nums">
	                  {typeof quality.tokensUsed === 'number' ? quality.tokensUsed.toLocaleString() : '—'}
	                </div>
	              </div>
	            </div>

	            {quality.freshnessWarning ? (
	              <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200 text-pretty">
	                <span className="font-semibold">Warning:</span>{' '}
	                {quality.freshnessWarning === 'low_freshness_for_time_sensitive_query'
	                  ? `Low freshness for a time-sensitive query (${percent(quality.freshnessRatio30d)} within 30 days).`
	                  : quality.freshnessWarning}
	              </div>
	            ) : null}
	          </div>

	          <div className="rounded-lg border border-border/60 bg-background p-3">
	            <div className="flex items-start justify-between gap-3">
	              <div className="min-w-0">
	                <div className="text-xs font-semibold text-foreground">Claims</div>
	                <div className="mt-1 text-[11px] font-medium text-muted-foreground text-pretty">
	                  Deterministic checks that each claim is supported by collected evidence.
	                </div>
	              </div>
	              <div className="flex flex-wrap items-center gap-1.5">
	                <span className={cn('rounded-md border px-2 py-1 text-[11px] tabular-nums', statusTone('verified'))}>
	                  Verified {claimCounts.verified}
	                </span>
	                <span className={cn('rounded-md border px-2 py-1 text-[11px] tabular-nums', statusTone('unsupported'))}>
	                  Unsupported {claimCounts.unsupported}
	                </span>
	                <span className={cn('rounded-md border px-2 py-1 text-[11px] tabular-nums', statusTone('contradicted'))}>
	                  Contradicted {claimCounts.contradicted}
	                </span>
	              </div>
	            </div>

	            <div className="mt-3 flex flex-wrap items-center gap-2">
	              <Button
	                type="button"
	                size="sm"
	                variant={claimFilter === 'all' ? 'soft' : 'outline'}
	                onClick={() => setClaimFilter('all')}
	              >
	                All <span className="ml-1 tabular-nums text-muted-foreground">{claimCounts.total}</span>
	              </Button>
	              <Button
	                type="button"
	                size="sm"
	                variant={claimFilter === 'verified' ? 'soft' : 'outline'}
	                onClick={() => setClaimFilter('verified')}
	              >
	                Verified <span className="ml-1 tabular-nums text-muted-foreground">{claimCounts.verified}</span>
	              </Button>
	              <Button
	                type="button"
	                size="sm"
	                variant={claimFilter === 'unsupported' ? 'soft' : 'outline'}
	                onClick={() => setClaimFilter('unsupported')}
	              >
	                Unsupported <span className="ml-1 tabular-nums text-muted-foreground">{claimCounts.unsupported}</span>
	              </Button>
	              <Button
	                type="button"
	                size="sm"
	                variant={claimFilter === 'contradicted' ? 'soft' : 'outline'}
	                onClick={() => setClaimFilter('contradicted')}
	              >
	                Contradicted <span className="ml-1 tabular-nums text-muted-foreground">{claimCounts.contradicted}</span>
	              </Button>
	              {claimCounts.unknown > 0 ? (
	                <Button
	                  type="button"
	                  size="sm"
	                  variant={claimFilter === 'unknown' ? 'soft' : 'outline'}
	                  onClick={() => setClaimFilter('unknown')}
	                >
	                  Other <span className="ml-1 tabular-nums text-muted-foreground">{claimCounts.unknown}</span>
	                </Button>
	              ) : null}
	            </div>

	            {filteredClaims.length === 0 ? (
	              <div className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3">
	                <div className="text-xs font-semibold text-foreground">No claims</div>
	                <div className="mt-1 text-xs font-medium text-muted-foreground text-pretty">
	                  This session has no extracted claims yet. Run deep research (or enable the research fetcher) to generate evidence-backed claims.
	                </div>
	              </div>
	            ) : (
	              <div className="mt-3 space-y-2">
	                {filteredClaims.map((claim, idx) => {
	                  const status = normalizeClaimStatus((claim as any)?.status)
	                  const key = `${idx}:${String((claim as any)?.claim ?? '')}`
	                  const isOpen = Boolean(openClaims[key])
	                  const evidenceUrls = Array.isArray((claim as any)?.evidence_urls) ? (claim as any).evidence_urls : []
	                  const evidencePassages = Array.isArray((claim as any)?.evidence_passages) ? (claim as any).evidence_passages : []
	                  const notes = typeof (claim as any)?.notes === 'string' ? (claim as any).notes : ''

	                  return (
	                    <div key={key} className="rounded-lg border border-border/60 bg-background overflow-hidden">
	                      <button
	                        type="button"
	                        onClick={() => toggleClaim(key)}
	                        className={cn(
	                          'w-full flex items-start justify-between gap-3 px-3 py-2 text-left',
	                          'hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
	                        )}
	                        aria-expanded={isOpen}
	                        aria-controls={`claim-${key}`}
	                      >
	                        <div className="min-w-0 flex-1">
	                          <div className="flex items-center gap-2">
	                            <span className={cn('inline-flex rounded-md border px-2 py-0.5 text-[11px] font-semibold', statusTone(status))}>
	                              {status}
	                            </span>
	                            <span className="text-[11px] font-medium text-muted-foreground tabular-nums">
	                              {evidenceUrls.length} urls · {evidencePassages.length} passages
	                            </span>
	                          </div>
	                          <div className="mt-1 text-xs text-foreground leading-relaxed text-pretty line-clamp-2">
	                            {String((claim as any)?.claim ?? '').trim() || '—'}
	                          </div>
	                        </div>
	                        <span className="text-muted-foreground mt-1">
	                          {isOpen ? (
	                            <ChevronDown className="h-4 w-4" aria-hidden="true" />
	                          ) : (
	                            <ChevronRight className="h-4 w-4" aria-hidden="true" />
	                          )}
	                        </span>
	                      </button>

	                      {isOpen ? (
	                        <div id={`claim-${key}`} className="border-t border-border/60 px-3 py-3 space-y-3">
	                          {notes ? (
	                            <div className="rounded-md border border-border/60 bg-muted/10 p-2">
	                              <div className="text-[11px] font-semibold text-foreground">Notes</div>
	                              <div className="mt-1 text-xs font-medium text-muted-foreground text-pretty">{notes}</div>
	                            </div>
	                          ) : null}

	                          {evidencePassages.length ? (
	                            <div>
	                              <div className="text-[11px] font-semibold text-foreground">Evidence passages</div>
	                              <div className="mt-2 space-y-2">
	                                {evidencePassages.map((passage: any, pidx: number) => {
	                                  const quote = String(passage?.quote ?? passage?.text ?? '').trim()
	                                  const preview = normalizePreview(quote, 260)
	                                  const passageUrl = String(passage?.url ?? '').trim()
	                                  const snippetHash = String(passage?.snippet_hash ?? '').trim()
	                                  const headingPath = Array.isArray(passage?.heading_path)
	                                    ? passage.heading_path.map(String).map((s: string) => s.trim()).filter(Boolean)
	                                    : []
	                                  const metaLine = [headingPath.length ? headingPath.join(' / ') : null, snippetHash || null]
	                                    .filter(Boolean)
	                                    .join(' · ')

	                                  return (
	                                    <div key={`${key}:${pidx}:${snippetHash || passageUrl}`} className="rounded-md border border-border/60 bg-muted/10 p-2">
	                                      <div className="flex items-start justify-between gap-2">
	                                        <div className="min-w-0 flex-1">
	                                          <div className="text-xs text-foreground leading-relaxed text-pretty">
	                                            {preview || '—'}
	                                          </div>
	                                          {metaLine ? (
	                                            <div className="mt-1 text-[10px] text-muted-foreground font-mono truncate">
	                                              {metaLine}
	                                            </div>
	                                          ) : null}
	                                          {passageUrl ? (
	                                            <a
	                                              href={passageUrl}
	                                              target="_blank"
	                                              rel="noreferrer"
	                                              className="mt-1 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
	                                            >
	                                              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
	                                              <span className="truncate">{passageUrl}</span>
	                                            </a>
	                                          ) : null}
	                                        </div>
	                                        <div className="flex items-center gap-1 shrink-0">
	                                          <Button
	                                            type="button"
	                                            variant="ghost"
	                                            size="icon-sm"
	                                            onClick={() => copyText(quote)}
	                                            aria-label="Copy evidence passage"
	                                            title="Copy evidence passage"
	                                          >
	                                            <Copy className="h-4 w-4" />
	                                          </Button>
	                                        </div>
	                                      </div>
	                                    </div>
	                                  )
	                                })}
	                              </div>
	                            </div>
	                          ) : null}

	                          {evidenceUrls.length ? (
	                            <div>
	                              <div className="text-[11px] font-semibold text-foreground">Evidence URLs</div>
	                              <div className="mt-2 space-y-1">
	                                {evidenceUrls.map((url: any, uidx: number) => {
	                                  const href = String(url ?? '').trim()
	                                  if (!href) return null
	                                  return (
	                                    <a
	                                      key={`${key}:${uidx}:${href}`}
	                                      href={href}
	                                      target="_blank"
	                                      rel="noreferrer"
	                                      className="block truncate rounded-md border border-border/60 bg-muted/10 px-2 py-1 text-[11px] text-primary hover:underline"
	                                    >
	                                      {href}
	                                    </a>
	                                  )
	                                })}
	                              </div>
	                            </div>
	                          ) : null}
	                        </div>
	                      ) : null}
	                    </div>
	                  )
	                })}
	              </div>
	            )}
	          </div>

	          {pages.length === 0 ? (
	            <div className="rounded-lg border border-border/60 bg-background p-4">
	              <div className="text-xs font-semibold text-foreground">No passages found</div>
	              <div className="mt-1 text-xs font-medium text-muted-foreground text-pretty">
	                This session has no evidence passages yet. Try enabling the research fetcher, or run deep research.
	              </div>
	            </div>
	          ) : (
            <div className="space-y-2">
              {pages.map(page => {
                const meta = fetchedMetaByUrl.get(page.url)
                const domain = safeDomain(page.url)
                const title = normalizePreview(meta?.title || domain || page.url, 120)
                const sub = [
                  domain || null,
                  meta?.method ? String(meta.method).toUpperCase() : null,
                  meta?.retrievedAt || null,
                ].filter(Boolean).join(' · ')

                return (
                  <div key={page.url} className="rounded-lg border border-border/60 bg-background overflow-hidden">
                    <div className="flex items-start justify-between gap-2 p-2.5">
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-foreground truncate" title={meta?.title || page.url}>
                          {title}
                        </div>
                        <div className="mt-0.5 text-[11px] font-medium text-muted-foreground truncate" title={sub}>
                          {sub || page.url}
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          asChild
                          aria-label="Open source"
                          title="Open source"
                        >
                          <a href={page.url} target="_blank" rel="noreferrer">
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        </Button>
                      </div>
                    </div>

                    <div className="border-t border-border/60">
                      {page.headings.map(heading => {
                        const groupKey = `${page.url}::${heading.key}`
                        const isOpen = Boolean(openGroups[groupKey])
                        return (
                          <div key={heading.key} className="border-b border-border/60 last:border-b-0">
                            <button
                              type="button"
                              onClick={() => toggleGroup(groupKey)}
                              className={cn(
                                'w-full flex items-center justify-between gap-2 px-2.5 py-2 text-left',
                                'hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                              )}
                              aria-expanded={isOpen}
                              aria-controls={groupKey}
                            >
                              <div className="min-w-0 flex items-center gap-2">
                                <span className="text-muted-foreground">
                                  {isOpen ? (
                                    <ChevronDown className="h-4 w-4" aria-hidden="true" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                                  )}
                                </span>
                                <span className="text-xs font-medium text-foreground truncate" title={heading.key}>
                                  {heading.key}
                                </span>
                              </div>
                              <span className="text-[11px] font-medium text-muted-foreground tabular-nums shrink-0">
                                {heading.passages.length}
                              </span>
                            </button>

                            {isOpen ? (
                              <div id={groupKey} className="px-2.5 pb-2 space-y-2">
                                {heading.passages.map(passage => {
                                  const quote = String(passage.quote ?? '').trim()
                                  const preview = normalizePreview(quote || passage.text, 220)
                                  const key = passage.snippet_hash || `${passage.start_char}:${passage.end_char}`
                                  return (
                                    <div
                                      key={key}
                                      className="rounded-md border border-border/60 bg-muted/10 p-2"
                                    >
                                      <div className="flex items-start justify-between gap-2">
                                        <div className="min-w-0 flex-1">
                                          <div className="text-xs text-foreground leading-relaxed line-clamp-3 text-pretty">
                                            {preview || '—'}
                                          </div>
                                          {passage.snippet_hash ? (
                                            <div className="mt-1 text-[10px] text-muted-foreground font-mono truncate">
                                              {passage.snippet_hash}
                                            </div>
                                          ) : null}
                                        </div>
                                        <div className="flex items-center gap-1 shrink-0">
                                          <Button
                                            type="button"
                                            variant="ghost"
                                            size="icon-sm"
                                            onClick={() => copyText(quote || passage.text)}
                                            aria-label="Copy quote"
                                            title="Copy quote"
                                          >
                                            <Copy className="h-4 w-4" />
                                          </Button>
                                        </div>
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      ) : null}

      {isLoading && evidence ? (
        <LoadingInline text="Refreshing evidence…" />
      ) : null}
    </div>
  )
}
