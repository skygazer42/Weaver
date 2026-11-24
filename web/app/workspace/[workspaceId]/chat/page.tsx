'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { Chat } from '@/components/chat/Chat'
import { Button } from '@/components/ui/button'
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
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <Button variant="outline" size="sm" asChild><Link href="/workspace">Back to workspaces</Link></Button>
      {error ? <p role="alert" className="text-destructive">{error}</p> : <p role="status">Loading project chat…</p>}
    </main>
  )
}

export default function ProjectChatPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  return <ProjectChat key={workspaceId} workspaceId={workspaceId} />
}
