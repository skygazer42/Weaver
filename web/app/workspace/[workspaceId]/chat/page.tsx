'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { AlertCircle, Loader2 } from 'lucide-react'
import { Chat } from '@/components/chat/Chat'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { getWorkspaceUrl, workspaceRequest, type Workspace } from '@/lib/workspace'

function ProjectChat({ workspaceId }: { workspaceId: string }) {
  const [project, setProject] = useState<Pick<Workspace, 'id' | 'name'> | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    workspaceRequest(getWorkspaceUrl(workspaceId), { signal: controller.signal, cache: 'no-store' })
      .then((response) => response.json())
      .then((workspace: Workspace) => {
        if (!controller.signal.aborted) setProject({ id: workspace.id, name: workspace.name })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not open project chat.')
      })
    return () => controller.abort()
  }, [workspaceId])

  if (project) return <main className="h-screen"><Chat project={project} /></main>
  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-subtle/50 p-4 sm:p-6">
      <div className={cn('w-full max-w-md space-y-4 rounded-lg border bg-card p-6 shadow-surface', error ? 'border-destructive-border' : 'border-border/80')}>
        {error ? (
          <>
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5 shrink-0" aria-hidden="true" />
              <h1 className="text-base font-semibold tracking-tight">Could not open project chat</h1>
            </div>
            <p role="alert" className="break-words rounded-md border border-destructive-border bg-destructive-surface p-3 text-sm text-destructive">{error}</p>
          </>
        ) : (
          <div role="status" className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 shrink-0 motion-safe:animate-spin" aria-hidden="true" />Loading project chat…
          </div>
        )}
        <Button variant="outline" size="sm" asChild><Link href="/workspace">Back to workspaces</Link></Button>
      </div>
    </main>
  )
}

export default function ProjectChatPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  return <ProjectChat key={workspaceId} workspaceId={workspaceId} />
}
