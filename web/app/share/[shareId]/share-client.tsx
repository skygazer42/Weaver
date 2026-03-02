'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getApiBaseUrl } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ExternalLink, Share } from '@/components/ui/icons'

type SharedMessage = {
  role: string
  content: string
}

type SharePayload = {
  id: string
  thread_id: string
  permissions: string
  created_at: string
  expires_at: string | null
  view_count: number
}

type ShareResponse =
  | {
    success: true
    share: SharePayload
    session: null | {
      id: string
      title: string
      messages: SharedMessage[]
    }
  }
  | {
    success: false
    detail?: string
    message?: string
  }

export function ShareClient({ shareId }: { shareId: string }) {
  const safeShareId = String(shareId || '').trim()
  const [data, setData] = useState<ShareResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const apiBase = useMemo(() => getApiBaseUrl(), [])

  useEffect(() => {
    if (!safeShareId) {
      setError('Missing share id')
      setLoading(false)
      return
    }

    let cancelled = false

    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${apiBase}/api/share/${encodeURIComponent(safeShareId)}`)
        if (!res.ok) {
          const text = await res.text().catch(() => '')
          throw new Error(text || `Request failed (${res.status})`)
        }
        const json = (await res.json()) as ShareResponse
        if (!cancelled) setData(json)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load share link')
          setData(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    run()

    return () => {
      cancelled = true
    }
  }, [apiBase, safeShareId])

  const share = data && 'success' in data && data.success ? data.share : null
  const session = data && 'success' in data && data.success ? data.session : null

  return (
    <main className="min-h-dvh bg-background text-foreground">
      <div className="mx-auto max-w-4xl px-4 py-10">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="inline-flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Share className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <h1 className="text-lg font-semibold leading-tight">Shared Session</h1>
                <p className="text-xs text-muted-foreground truncate">
                  Share ID: <span className="font-mono">{safeShareId || '—'}</span>
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm" aria-label="Open Weaver home">
              <Link href="/">
                Open Weaver
                <ExternalLink className="h-4 w-4 ml-2" />
              </Link>
            </Button>
          </div>
        </header>

        <section className="mt-6 rounded-2xl border border-border/50 bg-card p-5">
          {loading ? (
            <div className="text-sm text-muted-foreground">Loading share…</div>
          ) : error ? (
            <div className="text-sm text-destructive whitespace-pre-wrap break-words">{error}</div>
          ) : share ? (
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
                <div>
                  Thread: <span className="font-mono text-foreground">{share.thread_id}</span>
                </div>
                <div>
                  Permission: <span className="font-mono text-foreground">{share.permissions}</span>
                </div>
                <div>
                  Views: <span className="font-mono text-foreground">{share.view_count}</span>
                </div>
              </div>
              {session?.title ? (
                <div className="pt-2">
                  <div className="text-xs font-medium text-muted-foreground">Title</div>
                  <div className="text-base font-semibold text-foreground">{session.title}</div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">No data.</div>
          )}
        </section>

        <section className="mt-6 space-y-4">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Messages
          </h2>

          {!loading && !error && session?.messages?.length ? (
            <div className="space-y-3">
              {session.messages.map((m, idx) => {
                const role = String(m.role || 'unknown').toLowerCase()
                const isUser = role === 'user'
                const isAssistant = role === 'assistant'
                const label = isUser ? 'User' : isAssistant ? 'Assistant' : role
                return (
                  <article
                    key={`${idx}-${role}`}
                    className={cn(
                      'rounded-2xl border border-border/50 bg-card px-4 py-3',
                      isUser && 'bg-muted/20'
                    )}
                  >
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div className="text-xs font-medium text-muted-foreground">{label}</div>
                    </div>
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {String(m.content || '').trim() || '—'}
                      </ReactMarkdown>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <div className="rounded-2xl border border-border/50 bg-card p-5 text-sm text-muted-foreground">
              {loading ? 'Loading…' : 'No messages available for this share.'}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

