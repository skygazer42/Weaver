'use client'

import { useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { ArrowLeft, FileSpreadsheet, FolderOpen, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { getWorkspaceUrl, workspaceRequest, type Workspace } from '@/lib/workspace'
import { ProjectWorkspace } from './project-workspace'
import { WorkspacePanel } from './workspace-panel'

const STORAGE_KEY = 'weaver-workspace-id'
type WorkspaceView = 'project' | 'csv'

function WorkspaceContent({ workspace, view }: { workspace: Workspace; view: WorkspaceView }) {
  const [files, setFiles] = useState(workspace.files)

  return (
    <>
      <div hidden={view !== 'project'}>
        <ProjectWorkspace initialWorkspace={workspace} files={files} setFiles={setFiles} />
      </div>
      <div hidden={view !== 'csv'}>
        <WorkspacePanel initialWorkspace={workspace} files={files} setFiles={setFiles} />
      </div>
    </>
  )
}

export default function WorkspacePage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [view, setView] = useState<WorkspaceView>('project')
  const [openedCount, setOpenedCount] = useState(0)
  const [openId, setOpenId] = useState('')
  const [loading, setLoading] = useState(true)
  const [request, setRequest] = useState<'open' | 'create' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const requestedId = new URLSearchParams(window.location.search).get('workspace_id')
    const savedId = requestedId || localStorage.getItem(STORAGE_KEY)
    const restore = savedId
      ? workspaceRequest(getWorkspaceUrl(savedId), { signal: controller.signal, cache: 'no-store' }).then((res) => res.json())
      : Promise.resolve(null)
    restore.then((saved) => {
      if (controller.signal.aborted) return
      if (requestedId && saved) localStorage.setItem(STORAGE_KEY, saved.id)
      setWorkspace(saved)
    }).catch((cause: Error) => {
      if (controller.signal.aborted) return
      setOpenId(savedId ?? '')
      setError(cause.message)
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [])

  async function loadWorkspace(id?: string) {
    setRequest(id ? 'open' : 'create')
    setError(null)
    try {
      const response = await workspaceRequest(getWorkspaceUrl(id), id ? { cache: 'no-store' } : { method: 'POST' })
      const next: Workspace = await response.json()
      localStorage.setItem(STORAGE_KEY, next.id)
      const currentUrl = new URL(window.location.href)
      if (currentUrl.searchParams.has('workspace_id')) {
        currentUrl.searchParams.set('workspace_id', next.id)
        window.history.replaceState(null, '', currentUrl)
      }
      setWorkspace(next)
      setOpenedCount((count) => count + 1)
      setOpenId('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not open the workspace.')
    } finally {
      setRequest(null)
    }
  }

  function openWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const id = openId.trim()
    if (id) void loadWorkspace(id)
  }

  const busy = loading || request !== null

  return (
    <main className="min-h-dvh bg-surface-subtle/50">
      <header className="sticky top-0 z-30 h-14 border-b border-border/80 bg-background/90 backdrop-blur-md">
        <div className="mx-auto flex h-full max-w-7xl items-center justify-between gap-2 px-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-2 sm:gap-4">
            <div className="flex shrink-0 items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md border border-border/70 bg-white shadow-xs">
                <Image src="/logo.png" alt="" width={24} height={24} />
              </div>
              <span className="sr-only text-base font-semibold tracking-tight sm:not-sr-only">Weaver</span>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/" className="gap-1.5"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />Back to chat</Link>
            </Button>
          </div>
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void loadWorkspace()} className="gap-2">
            <Plus className="h-4 w-4" aria-hidden="true" />{request === 'create' ? 'Creating…' : 'New workspace'}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-8 sm:py-6">
        <div className="mb-4 flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          {view === 'project' ? (
            <div className="flex items-center gap-2.5">
              <FolderOpen className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Project workspace</h1>
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-2.5">
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">CSV Agent Workbench</h1>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">Analyze a CSV and download a Markdown report and an SVG chart.</p>
            </div>
          )}
          <div className="w-full min-w-0 lg:w-auto">
            <form onSubmit={openWorkspace} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
              <Label htmlFor="workspace-id" className="shrink-0 text-xs text-muted-foreground">Open by workspace ID</Label>
              <div className="flex min-w-0 gap-2 sm:max-w-sm">
                <Input id="workspace-id" value={openId} onChange={(event) => setOpenId(event.target.value)} disabled={busy} className="h-9 min-w-0 font-mono tabular-nums sm:w-48" />
                <Button type="submit" size="sm" variant="outline" className="h-9" disabled={busy || !openId.trim()}>{request === 'open' ? 'Opening…' : 'Open'}</Button>
              </div>
            </form>
          </div>
        </div>

        {error && <p role="alert" className="mb-4 break-words rounded-lg border border-destructive-border bg-destructive-surface p-3 text-sm text-destructive">{error}</p>}
        {workspace ? (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div role="group" aria-label="Workspace view" className="inline-flex flex-wrap gap-1 rounded-lg border border-border/70 bg-surface-subtle p-1">
                <Button type="button" variant="ghost" size="sm" className={cn('h-8', view === 'project' ? 'bg-card text-foreground shadow-xs hover:bg-card' : 'text-muted-foreground')} aria-pressed={view === 'project'} onClick={() => setView('project')}>Project workflows</Button>
                <Button type="button" variant="ghost" size="sm" className={cn('h-8', view === 'csv' ? 'bg-card text-foreground shadow-xs hover:bg-card' : 'text-muted-foreground')} aria-pressed={view === 'csv'} onClick={() => setView('csv')}>CSV analysis</Button>
              </div>
              <p className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
                Workspace ID <code className="break-all rounded-md border border-border/70 bg-card px-2 py-1 font-mono tabular-nums text-foreground">{workspace.id}</code>
              </p>
            </div>
            <WorkspaceContent key={`${workspace.id}-${openedCount}`} workspace={workspace} view={view} />
          </>
        ) : loading ? (
          <p role="status" className="rounded-lg border border-border/80 bg-card p-5 text-sm text-muted-foreground shadow-surface">Loading workspace…</p>
        ) : (
          <Card className="border-border/80 bg-card shadow-surface">
            <CardContent className="grid justify-items-start gap-3 p-5 sm:p-6">
              <h2 className="text-base font-semibold tracking-tight">Start a workspace</h2>
              <p className="text-sm text-muted-foreground">Keep project context, files, and task results together.</p>
              <Button type="button" disabled={busy} onClick={() => void loadWorkspace()}>{request === 'create' ? 'Creating…' : 'Create workspace'}</Button>
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  )
}
