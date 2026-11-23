'use client'

import { useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import { ArrowLeft, FileSpreadsheet, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getWorkspaceUrl, workspaceRequest, type Workspace } from '@/lib/workspace'
import { WorkspacePanel } from './workspace-panel'

const STORAGE_KEY = 'weaver-workspace-id'

export default function WorkspacePage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [openedCount, setOpenedCount] = useState(0)
  const [openId, setOpenId] = useState('')
  const [loading, setLoading] = useState(true)
  const [request, setRequest] = useState<'open' | 'create' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const savedId = localStorage.getItem(STORAGE_KEY)
    const restore = savedId
      ? workspaceRequest(getWorkspaceUrl(savedId), { signal: controller.signal, cache: 'no-store' }).then((res) => res.json())
      : Promise.resolve(null)
    restore.then((saved) => {
      if (!controller.signal.aborted) setWorkspace(saved)
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
    <main className="min-h-screen bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/" className="gap-2"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Back to chat</Link>
          </Button>
          {workspace && (
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void loadWorkspace()} className="gap-2">
              <Plus className="h-4 w-4" aria-hidden="true" />{request === 'create' ? 'Creating…' : 'New workspace'}
            </Button>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-7 sm:px-8 sm:py-10">
        <div className="mb-7 flex flex-col justify-between gap-5 border-b pb-6 lg:flex-row lg:items-end">
          <div>
            <FileSpreadsheet className="mb-3 h-6 w-6" aria-hidden="true" />
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">CSV Agent Workbench</h1>
            <p className="mt-2 text-sm text-muted-foreground">Analyze a CSV and download a Markdown report and an SVG chart.</p>
          </div>
          <div className="w-full min-w-0 max-w-sm">
            <form onSubmit={openWorkspace} className="space-y-2">
              <Label htmlFor="workspace-id">Open by workspace ID</Label>
              <div className="flex gap-2">
                <Input id="workspace-id" value={openId} onChange={(event) => setOpenId(event.target.value)} disabled={busy} className="min-w-0 font-mono" />
                <Button type="submit" variant="outline" disabled={busy || !openId.trim()}>{request === 'open' ? 'Opening…' : 'Open'}</Button>
              </div>
            </form>
          </div>
        </div>

        {error && <p role="alert" className="mb-5 rounded-md border border-destructive/40 bg-background p-3 text-sm text-destructive">{error}</p>}
        {workspace ? (
          <WorkspacePanel key={`${workspace.id}-${openedCount}`} initialWorkspace={workspace} />
        ) : loading ? (
          <p role="status" className="text-sm text-muted-foreground">Loading workspace…</p>
        ) : (
          <Card>
            <CardContent className="grid justify-items-start gap-4 p-6 sm:p-8">
              <h2 className="text-lg font-semibold">Start an analysis workspace</h2>
              <p className="text-sm text-muted-foreground">Each workspace keeps its CSV files and run history together.</p>
              <Button type="button" disabled={busy} onClick={() => void loadWorkspace()}>{request === 'create' ? 'Creating…' : 'Create workspace'}</Button>
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  )
}
