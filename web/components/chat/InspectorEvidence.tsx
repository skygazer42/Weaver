'use client'

import { useMemo, useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, Copy, ExternalLink, RefreshCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LoadingInline, LoadingSkeleton } from '@/components/ui/loading'
import { cn } from '@/lib/utils'
import { showError, showSuccess } from '@/lib/toast-utils'
import { useSessionEvidence } from '@/hooks/useSessionEvidence'
import { groupEvidencePassages } from '@/lib/evidence/normalizeEvidence'

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

export function InspectorEvidence({ threadId }: { threadId: string | null }) {
  const { evidence, isLoading, error, refresh } = useSessionEvidence(threadId)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})

  const pages = useMemo(() => {
    return groupEvidencePassages(evidence?.passages ?? [])
  }, [evidence?.passages])

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
        <div className="mt-1 text-xs text-muted-foreground text-pretty">
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
          <div className="text-[11px] text-muted-foreground truncate">
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
          <div className="mt-1 text-xs text-muted-foreground text-pretty">
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
              <div className="text-[11px] text-muted-foreground">Sources</div>
              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
                {evidence.sources?.length ?? 0}
              </div>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/10 p-2">
              <div className="text-[11px] text-muted-foreground">Claims</div>
              <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
                {evidence.claims?.length ?? 0}
              </div>
            </div>
          </div>

          {pages.length === 0 ? (
            <div className="rounded-lg border border-border/60 bg-background p-4">
              <div className="text-xs font-semibold text-foreground">No passages found</div>
              <div className="mt-1 text-xs text-muted-foreground text-pretty">
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
                        <div className="mt-0.5 text-[11px] text-muted-foreground truncate" title={sub}>
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
                              <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
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

