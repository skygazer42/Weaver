'use client'

import { useRef, useState, type FormEvent } from 'react'
import Link from 'next/link'
import { FileText, MessageSquare, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { uploadWorkspaceFile, workspaceRequest, type WorkspaceFile, type WorkspaceMetadata } from '@/lib/workspace'

export function ProjectMetadata({ initial, url }: { initial: WorkspaceMetadata & { id: string }; url: string }) {
  const [project, setProject] = useState(initial)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function saveProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const fields = new FormData(event.currentTarget)
    const changes = Object.fromEntries(
      [...fields].filter(([field, value]) => value !== project[field as keyof WorkspaceMetadata]),
    )
    setSaving(true)
    setError('')
    try {
      const response = await workspaceRequest(url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      })
      setProject(await response.json())
      setEditing(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save project details.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="gap-3 space-y-0 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <h2 className="min-w-0 break-words text-base font-semibold tracking-tight sm:text-lg">{project.name}</h2>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Button asChild size="sm">
          <Link href={`/workspace/${encodeURIComponent(initial.id)}/chat`} className="gap-2">
            <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />Chat in project
          </Link>
        </Button>
        <Dialog open={editing} onOpenChange={(open) => {
          if (saving) return
          setError('')
          setEditing(open)
        }}>
          <DialogTrigger asChild>
            <Button type="button" size="sm" variant="outline" className="shrink-0 gap-2">
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />Edit project
            </Button>
          </DialogTrigger>
          <DialogContent className="flex max-h-[85dvh] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
            <DialogHeader className="shrink-0 border-b border-border/80 px-6 py-4 pr-12">
              <DialogTitle>Edit project details</DialogTitle>
              <DialogDescription>Instructions and decisions give each task the same project context.</DialogDescription>
            </DialogHeader>
            <form onSubmit={saveProject} className="flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
                <fieldset disabled={saving} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="project-name">Project name</Label>
                    <Input id="project-name" name="name" defaultValue={project.name} required maxLength={120} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="project-instructions">Project instructions</Label>
                    <Textarea id="project-instructions" name="instructions" defaultValue={project.instructions} maxLength={4000} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="project-decisions">Project decisions</Label>
                    <Textarea id="project-decisions" name="decisions" defaultValue={project.decisions} maxLength={4000} />
                  </div>
                </fieldset>
                {error && <p role="alert" className="break-words rounded-lg border border-destructive-border bg-destructive-surface p-3 text-sm text-destructive">{error}</p>}
              </div>
              <DialogFooter className="shrink-0 border-t border-border/80 bg-surface-subtle/50 px-6 py-3.5">
                <DialogClose asChild><Button type="button" variant="outline" disabled={saving}>Cancel</Button></DialogClose>
                <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save project'}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
        </div>
      </CardHeader>
      {(project.instructions || project.decisions) && (
        <CardContent className="px-4 pb-4 sm:px-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {project.instructions && (
              <div className="min-w-0 space-y-1 rounded-md border border-border/60 bg-surface-subtle/60 p-3">
                <dt className="font-medium">Project instructions</dt>
                <dd className="whitespace-pre-wrap break-words text-muted-foreground">{project.instructions}</dd>
              </div>
            )}
            {project.decisions && (
              <div className="min-w-0 space-y-1 rounded-md border border-border/60 bg-surface-subtle/60 p-3">
                <dt className="font-medium">Project decisions</dt>
                <dd className="whitespace-pre-wrap break-words text-muted-foreground">{project.decisions}</dd>
              </div>
            )}
          </dl>
        </CardContent>
      )}
    </Card>
  )
}

export function ProjectFiles({ files, url, onUpload }: {
  files: WorkspaceFile[]
  url: string
  onUpload: (file: WorkspaceFile) => void
}) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)

  async function upload(file?: File) {
    if (!file || uploading) return
    setUploading(true)
    setError('')
    try {
      onUpload(await uploadWorkspaceFile(url, file))
      if (input.current) input.current.value = ''
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not upload the file.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card>
      <CardHeader className="mb-4 rounded-t-lg border-b border-border/70 bg-surface-subtle/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold tracking-tight">Project files</h2>
      </CardHeader>
      <CardContent className="space-y-4 px-5 pb-5">
        <div className="space-y-2">
          <Label htmlFor="project-file">Add project file</Label>
          <Input ref={input} id="project-file" type="file" accept=".csv,.md,.txt,.pdf,.docx" disabled={uploading}
            className="h-auto min-h-9 py-1.5 file:mr-3 file:rounded file:border-0 file:bg-surface-subtle file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-foreground"
            aria-describedby="project-file-types" onChange={(event) => void upload(event.target.files?.[0])} />
          <p id="project-file-types" className="text-xs text-muted-foreground">CSV, Markdown, text, PDF, or DOCX · Up to 5 MiB</p>
          {uploading && <p role="status" className="text-sm text-muted-foreground">Uploading file…</p>}
          {error && (
            <div className="space-y-2 rounded-lg border border-destructive-border bg-destructive-surface p-3">
              <p role="alert" className="break-words text-sm text-destructive">{error}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => void upload(input.current?.files?.[0])}>Retry upload</Button>
            </div>
          )}
        </div>
        {files.length > 0 && (
          <ul className="max-h-48 divide-y divide-border/60 overflow-y-auto rounded-md border border-border/70 text-sm">
            {files.map((file) => (
              <li key={file.id} className="flex items-start gap-2 px-3 py-2.5 transition-colors hover:bg-surface-subtle/60">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <a className="min-w-0 break-words rounded-sm underline decoration-border underline-offset-4 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50" href={`${url}/files/${encodeURIComponent(file.id)}`}>{file.name}</a>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
