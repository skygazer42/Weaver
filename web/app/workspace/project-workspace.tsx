'use client'

import { useCallback, useEffect, useRef, useState, type Dispatch, type FormEvent, type SetStateAction } from 'react'
import { CalendarClock, Download, FileText, Loader2, Play } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { getArtifactDownloadUrl } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  getWorkspaceUrl, workspaceRequest, type ProjectSchedule, type ProjectTask, type ProjectWorkflow,
  type Workspace, type WorkspaceDeliverable, type WorkspaceFile,
} from '@/lib/workspace'
import { ProjectFiles, ProjectMetadata } from './project-context'
import { WorkspaceMarkdown } from './workspace-artifacts'

const workflowLabels: Record<ProjectWorkflow, string> = {
  'requirements-spec': 'Requirements spec',
  'release-brief': 'Release brief',
}

const MAX_SOURCE_FILES = 6

const statusLabels: Record<ProjectTask['status'], string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Stopped',
  insufficient_evidence: 'Insufficient evidence',
  awaiting_approval: 'Awaiting approval',
}

const repeatLabels = { 1: 'Every 24 hours', 7: 'Every 7 days' } as const

type ProjectHistory = { tasks: ProjectTask[]; deliverables: WorkspaceDeliverable[]; schedules: ProjectSchedule[] }

function isPending(task: ProjectTask) {
  return task.status === 'queued' || task.status === 'running'
}

function TaskStatus({ status }: { status: ProjectTask['status'] }) {
  return <Badge variant={status === 'failed' ? 'destructive' : 'secondary'}>{statusLabels[status]}</Badge>
}

export function ProjectWorkspace({ initialWorkspace, files, setFiles }: {
  initialWorkspace: Workspace
  files: WorkspaceFile[]
  setFiles: Dispatch<SetStateAction<WorkspaceFile[]>>
}) {
  const url = getWorkspaceUrl(initialWorkspace.id)
  const [history, setHistory] = useState<ProjectHistory | null>(null)
  const [historyError, setHistoryError] = useState('')
  const historyRequest = useRef<AbortController | null>(null)
  const [taskId, selectTask] = useState<string | null>(null)
  const [progress, setProgress] = useState<{ taskId: string; message: string } | null>(null)
  const [stops, setStops] = useState<Record<string, { pending: boolean; error?: string }>>({})
  const [workflow, setWorkflow] = useState<ProjectWorkflow>('requirements-spec')
  const [prompt, setPrompt] = useState('')
  const [repository, setRepository] = useState('')
  const [releaseTag, setReleaseTag] = useState('')
  const [repeatDays, setRepeatDays] = useState(0)
  const [firstRun, setFirstRun] = useState('')
  const [updatingSchedule, setUpdatingSchedule] = useState(false)
  const [scheduleError, setScheduleError] = useState('')
  const [fileIds, setFileIds] = useState<string[]>([])
  const [revision, setRevision] = useState<WorkspaceDeliverable | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submissionError, setSubmissionError] = useState('')
  const requestId = useRef<{ id: string; body: string } | null>(null)
  const promptInput = useRef<HTMLTextAreaElement>(null)

  const selected = history?.tasks.find((task) => task.id === taskId) ?? history?.tasks[0]
  const activeTaskId = selected && isPending(selected) ? selected.id : null
  const pending = history?.tasks.some(isPending) ?? false
  const scheduled = history?.schedules.some((schedule) => schedule.enabled) ?? false
  const scheduling = !revision && repeatDays !== 0
  const deliverable = history?.deliverables.find((artifact) => artifact.task_id === selected?.id)
  const original = history?.deliverables.find((artifact) => artifact.id === deliverable?.based_on)

  const refresh = useCallback(() => {
    historyRequest.current?.abort()
    const controller = new AbortController()
    historyRequest.current = controller
    const options = { signal: controller.signal, cache: 'no-store' } as const
    return workspaceRequest(`${url}/tasks`, options).then(async (response) => {
      const tasks: ProjectTask[] = await response.json()
      const deliverables: WorkspaceDeliverable[] = await workspaceRequest(`${url}/deliverables`, options).then((res) => res.json())
      const schedules: ProjectSchedule[] = await workspaceRequest(`${url}/schedules`, options).then((res) => res.json())
      if (controller.signal.aborted) return
      setHistory({ tasks, deliverables, schedules })
      setHistoryError('')
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setHistoryError(cause instanceof Error ? cause.message : 'Could not load task history.')
    }).finally(() => {
      if (historyRequest.current === controller) historyRequest.current = null
    })
  }, [url])

  useEffect(() => {
    void refresh()
    return () => historyRequest.current?.abort()
  }, [refresh])

  useEffect(() => {
    if (!pending && !scheduled) return
    const timer = window.setInterval(() => {
      if (!historyRequest.current) void refresh()
    }, pending ? 2000 : 10000)
    return () => window.clearInterval(timer)
  }, [pending, refresh, scheduled])

  useEffect(() => {
    if (!activeTaskId) return
    const events = new EventSource(`${url}/tasks/${encodeURIComponent(activeTaskId)}/events`)
    events.addEventListener('status', (event: MessageEvent<string>) => {
      const { data } = JSON.parse(event.data)
      if (typeof data?.message === 'string') setProgress({ taskId: activeTaskId, message: data.message })
    })
    events.addEventListener('run_status', (event: MessageEvent<string>) => {
      const { data } = JSON.parse(event.data)
      if (data?.status === 'queued' || data?.status === 'running') return
      events.close()
      void refresh()
    })
    return () => events.close()
  }, [activeTaskId, refresh, url])

  async function runTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || !prompt.trim()) return
    const startsAt = scheduling ? new Date(firstRun) : null
    if (startsAt && !Number.isFinite(startsAt.getTime())) {
      setSubmissionError('Choose when the first task should run.')
      return
    }
    const payload = {
      workflow,
      prompt: prompt.trim(),
      file_ids: fileIds.length ? fileIds : undefined,
      repository: workflow === 'release-brief' ? repository.trim() || undefined : undefined,
      release_tag: workflow === 'release-brief' ? releaseTag.trim() || undefined : undefined,
      artifact_id: revision?.id,
      ...(startsAt && { repeat_days: repeatDays, first_run_at: startsAt.toISOString() }),
    }
    const body = JSON.stringify(payload)
    if (requestId.current?.body !== body) {
      const bytes = crypto.getRandomValues(new Uint8Array(16))
      const id = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
      requestId.current = { body, id }
    }
    setSubmitting(true)
    setSubmissionError('')
    try {
      const response = await workspaceRequest(`${url}/${scheduling ? 'schedules' : 'tasks'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, request_id: requestId.current.id }),
      })
      if (scheduling) {
        setRepeatDays(0)
        setFirstRun('')
      } else {
        const task: ProjectTask = await response.json()
        setHistory((current) => ({
          tasks: [task, ...(current?.tasks.filter(({ id }) => id !== task.id) ?? [])],
          deliverables: current?.deliverables ?? [],
          schedules: current?.schedules ?? [],
        }))
        selectTask(task.id)
      }
      requestId.current = null
      setPrompt('')
      setRevision(null)
      void refresh()
    } catch (cause) {
      setSubmissionError(cause instanceof Error ? cause.message : 'Could not submit the task.')
    } finally {
      setSubmitting(false)
    }
  }

  async function changeSchedule(schedule: ProjectSchedule, action: 'toggle' | 'delete') {
    setUpdatingSchedule(true)
    setScheduleError('')
    try {
      await workspaceRequest(`${url}/schedules/${encodeURIComponent(schedule.id)}`, action === 'delete'
        ? { method: 'DELETE' }
        : {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: !schedule.enabled }),
        })
      await refresh()
    } catch (cause) {
      setScheduleError(cause instanceof Error ? cause.message : 'Could not update the schedule.')
    } finally {
      setUpdatingSchedule(false)
    }
  }

  function revise(artifact: WorkspaceDeliverable, task: ProjectTask) {
    setRevision(artifact)
    setWorkflow(artifact.workflow)
    setRepository(task.repository ?? '')
    const release = artifact.sources.find((source) => source.kind === 'github_release')
    setReleaseTag(release?.release_tag ?? task.release_tag ?? '')
    setFileIds(task.file_ids ?? [])
    setPrompt('')
    setSubmissionError('')
    promptInput.current?.focus()
  }

  async function stopTask(id: string) {
    setStops((current) => ({ ...current, [id]: { pending: true } }))
    try {
      await workspaceRequest(`${url}/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' })
      void refresh()
    } catch (cause) {
      const error = cause instanceof Error ? cause.message : 'Could not stop the task.'
      setStops((current) => ({ ...current, [id]: { pending: false, error } }))
    }
  }

  return (
    <div className="space-y-5">
      <ProjectMetadata initial={initialWorkspace} url={url} />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader className="p-5">
              <h2 className="text-lg font-semibold tracking-tight">{revision ? 'Revise deliverable' : 'New task'}</h2>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              <form onSubmit={runTask}>
                <fieldset disabled={submitting} className="space-y-4">
                  {revision ? (
                    <div className="flex items-start justify-between gap-2 rounded-md bg-muted p-2.5 text-sm">
                      <p className="min-w-0 break-words">{revision.title}</p>
                      <Button type="button" variant="ghost" size="sm" className="-my-1 shrink-0" onClick={() => setRevision(null)}>Cancel revision</Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Label htmlFor="project-workflow">Workflow</Label>
                      <select id="project-workflow" value={workflow} onChange={(event) => setWorkflow(event.target.value as ProjectWorkflow)}
                        className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:ring-2 focus-visible:ring-ring">
                        {Object.entries(workflowLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </div>
                  )}
                  {workflow === 'release-brief' && (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="project-repository">GitHub repository</Label>
                        <Input id="project-repository" value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repository" required={!revision} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="project-release-tag">Release tag</Label>
                        <Input id="project-release-tag" value={releaseTag} onChange={(event) => setReleaseTag(event.target.value)} placeholder="Latest release" />
                      </div>
                    </>
                  )}
                  <div className="space-y-2">
                    <Label htmlFor="project-prompt">Task prompt</Label>
                    <Textarea ref={promptInput} id="project-prompt" value={prompt} maxLength={4000} required
                      onChange={(event) => setPrompt(event.target.value)} placeholder={revision ? 'What would you like to change?' : 'Describe what the deliverable should cover.'} />
                  </div>
                  {files.length > 0 && (
                    <details className="space-y-2 text-sm">
                      <summary className="w-fit cursor-pointer font-medium">Source files · {fileIds.length || 'Recent documents'}</summary>
                      <p className="text-xs text-muted-foreground">Choose up to {MAX_SOURCE_FILES} files.</p>
                      <ul aria-label="Source files" className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
                        {files.map((file) => {
                          const selected = fileIds.includes(file.id)
                          return (
                            <li key={file.id}>
                              <label className="flex items-start gap-2 break-words">
                                <input className="mt-0.5 shrink-0" type="checkbox" checked={selected} disabled={!selected && fileIds.length >= MAX_SOURCE_FILES} onChange={(event) => {
                                  const checked = event.target.checked
                                  setFileIds((current) => checked ? [...current, file.id] : current.filter((id) => id !== file.id))
                                }} />
                                <span className="min-w-0">{file.name}</span>
                              </label>
                            </li>
                          )
                        })}
                      </ul>
                    </details>
                  )}
                  {!revision && (
                    <div className="space-y-2">
                      <Label htmlFor="project-repeat">Repeat</Label>
                      <select id="project-repeat" value={repeatDays} onChange={(event) => setRepeatDays(Number(event.target.value))}
                        className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:ring-2 focus-visible:ring-ring">
                        <option value={0}>Run once now</option>
                        <option value={1}>{repeatLabels[1]}</option>
                        <option value={7}>{repeatLabels[7]}</option>
                      </select>
                    </div>
                  )}
                  {scheduling && (
                    <div className="space-y-2">
                      <Label htmlFor="project-first-run">First run (local time)</Label>
                      <Input id="project-first-run" type="datetime-local" value={firstRun}
                        onChange={(event) => setFirstRun(event.target.value)} required />
                    </div>
                  )}
                  {submissionError && <p role="alert" className="break-words text-sm text-destructive">{submissionError}</p>}
                  <Button type="submit" className="w-full gap-2" disabled={!prompt.trim() || (scheduling && !firstRun)}>
                    {submitting ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : scheduling ? <CalendarClock className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
                    {submitting ? 'Submitting…' : scheduling ? 'Schedule task' : 'Run task'}
                  </Button>
                </fieldset>
              </form>
            </CardContent>
          </Card>

          {history && history.schedules.length > 0 && (
            <Card role="region" aria-labelledby="project-schedules-title" aria-busy={updatingSchedule}>
              <CardHeader className="p-5">
                <h2 id="project-schedules-title" className="text-lg font-semibold tracking-tight">Scheduled tasks</h2>
              </CardHeader>
              <CardContent className="space-y-3 px-5 pb-5">
                {scheduleError && <p role="alert" className="break-words text-sm text-destructive">{scheduleError}</p>}
                <ul className="max-h-96 space-y-2 overflow-y-auto">
                  {history.schedules.map((schedule) => (
                    <li key={schedule.id} className="space-y-2 rounded-md border p-3 text-sm">
                      <p className="break-words font-medium">{schedule.prompt}</p>
                      <p className="break-words text-xs text-muted-foreground">
                        {workflowLabels[schedule.workflow]}{schedule.repository && <> · {schedule.repository}{schedule.release_tag && <> · {schedule.release_tag}</>}</>} · {repeatLabels[schedule.repeat_days]}
                      </p>
                      {schedule.enabled ? (
                        <p className="text-xs">Next run <time dateTime={schedule.next_run_at}>{new Date(schedule.next_run_at).toLocaleString()}</time></p>
                      ) : <Badge variant="secondary">Paused</Badge>}
                      <div className="flex flex-wrap gap-1">
                        {schedule.last_task_id && (
                          <Button type="button" variant="outline" size="sm" onClick={() => {
                            selectTask(schedule.last_task_id)
                            void refresh()
                          }}>View latest run</Button>
                        )}
                        <Button type="button" variant="ghost" size="sm" disabled={updatingSchedule} onClick={() => void changeSchedule(schedule, 'toggle')}>
                          {schedule.enabled ? 'Pause' : 'Resume'}
                        </Button>
                        <Button type="button" variant="ghost" size="sm" disabled={updatingSchedule} onClick={() => void changeSchedule(schedule, 'delete')}>
                          Delete schedule
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <ProjectFiles files={files} url={url} onUpload={(file) => setFiles((current) => [file, ...current.filter(({ id }) => id !== file.id)])} />

          <Card>
            <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 p-5">
              <h2 className="text-lg font-semibold tracking-tight">Task history</h2>
              <Button type="button" variant="ghost" size="sm" onClick={() => void refresh()}>Refresh tasks</Button>
            </CardHeader>
            <CardContent className="space-y-3 px-5 pb-5">
              {historyError && <p role="alert" className="break-words text-sm text-destructive">{historyError}</p>}
              {!history && !historyError && <p role="status" className="text-sm text-muted-foreground">Loading tasks…</p>}
              {history?.tasks.length === 0 && <p className="text-sm text-muted-foreground">No tasks yet.</p>}
              {history && history.tasks.length > 0 && (
                <ul className="-mx-1 max-h-96 space-y-2 overflow-y-auto p-1">
                  {history.tasks.map((task) => (
                    <li key={task.id}>
                      <button type="button" aria-pressed={selected?.id === task.id} onClick={() => selectTask(task.id)} className={cn(
                        'grid w-full gap-1 rounded-md border p-3 text-left text-sm hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                        selected?.id === task.id && 'border-foreground/30 bg-muted',
                      )}>
                        <span className="break-words font-medium">{task.prompt}</span>
                        <span className="text-xs text-muted-foreground">
                          {workflowLabels[task.workflow]}{task.schedule_id && ' · Scheduled'}{task.created_at && <> · <time dateTime={task.created_at}>{new Date(task.created_at).toLocaleString()}</time></>}
                        </span>
                        <span className="w-fit"><TaskStatus status={task.status} /></span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="min-w-0">
          <CardHeader className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold tracking-tight">Task results</h2>
          </CardHeader>
          <CardContent className="space-y-5 px-5 pb-5 sm:px-6 sm:pb-6">
            {selected ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div role="status" className="flex flex-wrap items-center gap-2">
                    {activeTaskId && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />}
                    <TaskStatus status={selected.status} />
                    {activeTaskId && progress?.taskId === activeTaskId && <span className="text-sm text-muted-foreground">{progress.message}</span>}
                  </div>
                  {activeTaskId && <Button type="button" variant="outline" size="sm" disabled={stops[selected.id]?.pending} onClick={() => void stopTask(selected.id)}>
                    {stops[selected.id]?.pending ? 'Stopping…' : 'Stop task'}
                  </Button>}
                </div>
                <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{selected.prompt}</p>
                {activeTaskId && stops[selected.id]?.error && <p role="alert" className="break-words text-sm text-destructive">{stops[selected.id].error}</p>}
                {selected.status === 'failed' && <p role="alert" className="break-words text-sm text-destructive">{selected.error || 'Task failed.'}</p>}
                {selected.status === 'insufficient_evidence' && <p className="text-sm text-muted-foreground">Add more source material and run the task again.</p>}
                {deliverable && (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <h3 className="min-w-0 break-words font-semibold">{deliverable.title}</h3>
                      <div className="flex flex-wrap gap-2">
                        <Button type="button" variant="outline" size="sm" disabled={submitting} onClick={() => revise(deliverable, selected)}>Revise</Button>
                        <Button variant="outline" size="sm" asChild>
                          <a href={`${url}/deliverables/${encodeURIComponent(deliverable.id)}/download`} className="gap-2">
                            <Download className="h-4 w-4" aria-hidden="true" />Download Markdown
                          </a>
                        </Button>
                      </div>
                    </div>
                    {original && <p className="break-words text-sm text-muted-foreground">
                      Revised from <button type="button" className="underline underline-offset-2" onClick={() => selectTask(original.task_id)}>{original.title}</button>
                    </p>}
                    <WorkspaceMarkdown content={deliverable.content.replace(/^# [^\r\n]+\r?\n/, '')} />
                    {deliverable.sources.length > 0 && (
                      <section aria-labelledby="project-sources-heading" className="space-y-3">
                        <h3 id="project-sources-heading" className="font-semibold">Sources</h3>
                        <ul className="divide-y rounded-md border">
                          {deliverable.sources.map((source) => {
                            const sourceUrl = source.url?.startsWith('https://github.com/')
                              ? source.url
                              : getArtifactDownloadUrl(source.url ?? undefined)
                            return (
                              <li key={source.id} className="space-y-1 p-3 text-sm">
                                <p className="break-words font-medium">
                                  <code className="mr-2 rounded bg-muted px-1 text-xs font-normal">{source.id}</code>
                                  {sourceUrl ? <a href={sourceUrl} className="underline underline-offset-2">{source.title}</a> : source.title}
                                </p>
                                {source.snippet && <p className="whitespace-pre-wrap break-words text-muted-foreground">{source.snippet}</p>}
                              </li>
                            )
                          })}
                        </ul>
                      </section>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-md border border-dashed bg-muted/30 p-6 text-center">
                <FileText className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p className="text-sm text-muted-foreground">Run a task to see its deliverable and sources here.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
