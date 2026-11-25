'use client'

import React, { useMemo, useRef, useState } from 'react'
import { ArrowUpRight, BookOpen, Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/lib/i18n/i18n-context'
import { filterStudioSources, type StudioDomain, type StudioSource } from '@/lib/researchStudio'
import { cn } from '@/lib/utils'

export function SourcesPanelView({ sources, domains }: { sources: StudioSource[]; domains: StudioDomain[] }) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [domain, setDomain] = useState('')
  const results = useRef<HTMLOListElement>(null)
  const filtered = useMemo(() => filterStudioSources(sources, query, domain), [sources, query, domain])
  const options = [{ domain: '', count: sources.length }, ...domains.slice(0, 3)]
  if (domain && !options.some(option => option.domain === domain)) {
    options.push(domains.find(option => option.domain === domain) ?? { domain, count: 0 })
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b border-border bg-card px-3.5 pb-3 pt-3.5">
        <div className="relative">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" value={query} onChange={event => {
            setQuery(event.target.value)
            results.current?.scrollTo(0, 0)
          }} placeholder={t('studioSearchSources')} aria-label={t('studioSearchSources')} className="h-10 pl-9 text-base xl:text-sm" />
        </div>
        <div role="group" aria-label={t('studioFilterDomains')} className="flex gap-1.5 overflow-x-auto pb-1">
          {options.map(option => (
            <button
              key={option.domain}
              type="button"
              title={option.domain || undefined}
              aria-pressed={domain === option.domain}
              onClick={() => {
                setDomain(option.domain)
                results.current?.scrollTo(0, 0)
              }}
              className={cn(
                'flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                domain === option.domain ? 'border-primary/25 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:bg-accent hover:text-foreground'
              )}
            >
              {option.domain || t('studioAllDomains')}
              <span className="tabular-nums">{option.count}</span>
            </button>
          ))}
        </div>
      </div>
      <p role="status" className="sr-only">{t('studioSourceCount').replace('{count}', String(filtered.length))}</p>
      {filtered.length > 0 ? (
        <ol ref={results} className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain p-3.5">
          {filtered.map(source => (
            <li key={source.index}>
              <a href={source.url} target="_blank" rel="noopener noreferrer" className="group flex min-w-0 items-start gap-2.5 rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/50 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                <span className="min-w-8 shrink-0 rounded-sm bg-primary/10 px-1 py-0.5 text-center font-mono text-[11px] font-medium leading-4 tabular-nums text-primary">[{source.index}]</span>
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="block truncate text-[11px] font-medium leading-4 text-muted-foreground">{source.domain}</span>
                  <span className="line-clamp-2 break-words text-sm font-medium leading-5 text-foreground">{source.title || source.url}</span>
                  <span className="block truncate text-xs leading-4 text-muted-foreground">{source.url}</span>
                </span>
                <ArrowUpRight aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground group-hover:text-primary" />
              </a>
            </li>
          ))}
        </ol>
      ) : (
        <div className="grid flex-1 place-content-center justify-items-center gap-2 p-6 text-center text-sm text-muted-foreground">
          <BookOpen aria-hidden="true" className="size-5" />
          <p>{t(sources.length ? 'studioNoMatchingSources' : 'studioNoSources')}</p>
        </div>
      )}
    </div>
  )
}
