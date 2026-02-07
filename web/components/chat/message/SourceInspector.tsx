'use client'

import { useMemo, useState } from 'react'
import { ExternalLink, Filter, Link as LinkIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MessageSource } from '@/types/chat'

interface SourceInspectorProps {
  sources: MessageSource[]
  activeCitation?: string | null
  onSelectCitation?: (citation: string | null) => void
  className?: string
}

type SortBy = 'fresh_new' | 'fresh_old' | 'domain'

function normalizeDomain(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.hostname.replace(/^www\./, '')
  } catch {
    return 'unknown'
  }
}

function freshnessLabel(source: MessageSource): string {
  const explicitDays = source.freshnessDays
  if (typeof explicitDays === 'number' && Number.isFinite(explicitDays)) {
    if (explicitDays <= 1) return 'today'
    if (explicitDays <= 7) return `${Math.round(explicitDays)}d`
    if (explicitDays <= 30) return `${Math.round(explicitDays)}d`
    return 'stale'
  }

  if (!source.publishedDate) {
    return 'unknown'
  }

  const ts = Date.parse(source.publishedDate)
  if (Number.isNaN(ts)) {
    return 'unknown'
  }
  const ageDays = Math.max(0, (Date.now() - ts) / (1000 * 60 * 60 * 24))
  if (ageDays <= 1) return 'today'
  if (ageDays <= 30) return `${Math.round(ageDays)}d`
  return 'stale'
}

function freshnessDays(source: MessageSource): number | null {
  if (typeof source.freshnessDays === 'number' && Number.isFinite(source.freshnessDays)) {
    return Math.max(0, source.freshnessDays)
  }
  if (!source.publishedDate) {
    return null
  }
  const ts = Date.parse(source.publishedDate)
  if (Number.isNaN(ts)) {
    return null
  }
  return Math.max(0, (Date.now() - ts) / (1000 * 60 * 60 * 24))
}

export function SourceInspector({
  sources,
  activeCitation,
  onSelectCitation,
  className,
}: SourceInspectorProps) {
  const [domainFilter, setDomainFilter] = useState('all')
  const [providerFilter, setProviderFilter] = useState('all')
  const [sortBy, setSortBy] = useState<SortBy>('fresh_new')

  const normalizedSources = useMemo(() => {
    return sources.map((source, idx) => {
      const domain = source.domain || normalizeDomain(source.url)
      const provider = source.provider || 'unknown'
      const ageDays = freshnessDays(source)
      return {
        ...source,
        domain,
        provider,
        citation: String(idx + 1),
        freshness: freshnessLabel(source),
        freshnessValue: ageDays,
      }
    })
  }, [sources])

  const domainOptions = useMemo(() => {
    const set = new Set(normalizedSources.map(s => s.domain).filter(Boolean))
    return ['all', ...Array.from(set)]
  }, [normalizedSources])

  const providerOptions = useMemo(() => {
    const set = new Set(normalizedSources.map(s => s.provider).filter(Boolean))
    return ['all', ...Array.from(set)]
  }, [normalizedSources])

  const visibleSources = useMemo(() => {
    const filtered = normalizedSources.filter(source => {
      if (domainFilter !== 'all' && source.domain !== domainFilter) return false
      if (providerFilter !== 'all' && source.provider !== providerFilter) return false
      return true
    })

    return filtered.sort((a, b) => {
      if (sortBy === 'domain') {
        return a.domain.localeCompare(b.domain)
      }

      const av = typeof a.freshnessValue === 'number' ? a.freshnessValue : Number.POSITIVE_INFINITY
      const bv = typeof b.freshnessValue === 'number' ? b.freshnessValue : Number.POSITIVE_INFINITY

      if (sortBy === 'fresh_old') {
        return bv - av
      }
      return av - bv
    })
  }, [normalizedSources, domainFilter, providerFilter, sortBy])

  if (!sources || sources.length === 0) {
    return null
  }

  return (
    <div className={cn('mt-3 rounded-xl border bg-muted/20 p-3', className)}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground">
          <Filter className="h-3.5 w-3.5" />
          Source Inspector
        </div>
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="h-7 rounded-md border bg-background px-2 text-xs"
        >
          {domainOptions.map(option => (
            <option key={option} value={option}>
              domain: {option}
            </option>
          ))}
        </select>
        <select
          value={providerFilter}
          onChange={(e) => setProviderFilter(e.target.value)}
          className="h-7 rounded-md border bg-background px-2 text-xs"
        >
          {providerOptions.map(option => (
            <option key={option} value={option}>
              provider: {option}
            </option>
          ))}
        </select>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortBy)}
          className="h-7 rounded-md border bg-background px-2 text-xs"
        >
          <option value="fresh_new">sort: newest</option>
          <option value="fresh_old">sort: oldest</option>
          <option value="domain">sort: domain</option>
        </select>
      </div>

      <div className="space-y-2">
        {visibleSources.map(source => {
          const isActive = activeCitation === source.citation
          const href = source.rawUrl || source.url
          return (
            <div
              key={`${source.citation}-${source.url}`}
              className={cn(
                'rounded-lg border bg-background/80 p-2 transition-colors',
                isActive && 'border-primary/60 bg-primary/5'
              )}
            >
              <button
                type="button"
                className="flex w-full items-start gap-2 text-left"
                onClick={() => onSelectCitation?.(isActive ? null : source.citation)}
              >
                <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-primary/10 px-1 text-[10px] font-semibold text-primary">
                  [{source.citation}]
                </span>
                <span className="flex-1 text-xs font-medium leading-5">{source.title || 'Untitled source'}</span>
              </button>
              <div className="mt-2 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                <span className="rounded bg-muted px-1.5 py-0.5">{source.domain}</span>
                <span className="rounded bg-muted px-1.5 py-0.5">{source.provider}</span>
                <span className="rounded bg-muted px-1.5 py-0.5">freshness: {source.freshness}</span>
              </div>
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
              >
                <LinkIcon className="h-3 w-3" />
                <span className="max-w-[420px] truncate">{href}</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )
        })}
      </div>
    </div>
  )
}
