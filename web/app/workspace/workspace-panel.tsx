'use client'

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useChat } from '@ai-sdk/react'
import { FileSpreadsheet, Loader2, Play } from 'lucide-react'
import { badgeVariants } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { usePublicModels } from '@/hooks/usePublicModels'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import {
  createWorkspaceRunTransport, getWorkspaceUrl, mergeWorkspaceRuns, workspaceRequest,
  type Workspace, type WorkspaceFile, type WorkspaceMessage, type WorkspaceRun,
} from '@/lib/workspace'
import { WorkspaceArtifacts } from './workspace-artifacts'

const stepLabels: Record<WorkspaceRun['step'], string> = {
  queued: 'Queued',
  sandbox: 'Analyzing CSV in sandbox',
  report: 'Writing report',
  completed: 'Completed',
  failed: 'Failed',
}

const selectClass = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50'

function isPending(run: WorkspaceRun) {
  return run.status === 'queued' || run.status === 'running'
}

function RunStatus({ run }: { run: WorkspaceRun }) {
  return (
    <span className={badgeVariants({ variant: run.status === 'failed' ? 'destructive' : 'secondary', className: 'w-fit max-w-full' })}>
      {stepLabels[run.step]}
    </span>
  )
}

export function WorkspacePanel({ initialWorkspace }: { initialWorkspace: Workspace }) {
  const { language, t } = useI18n()
  const { models, isLoading: loadingModels } = usePublicModels()
  const dateFormat = useMemo(() => new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'medium' }), [language])
  const [files, setFiles] = useState(initialWorkspace.files)
  const [runs, setRuns] = useState(() => mergeWorkspaceRuns([], initialWorkspace.runs))
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [savedFileId, setSavedFileId] = useState('')
  const [upload, setUpload] = useState<File | null>(null)
  const [chosenModel, setChosenModel] = useState('')
  const [prompt, setPrompt] = useState('')
  const [phase, setPhase] = useState<'uploading' | 'running' | null>(null)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const receivedRun = useRef(false)

  const workspaceUrl = getWorkspaceUrl(initialWorkspace.id)
  const transport = useMemo(() => createWorkspaceRunTransport(`${workspaceUrl}/runs`), [workspaceUrl])
  const { sendMessage, setMessages } = useChat<WorkspaceMessage>({
    id: initialWorkspace.id,
    transport,
    onData(part) {
      if (part.type !== 'data-run') return
      const run = part.data
      setRuns((current) => mergeWorkspaceRuns(current, [run]))
      if (!receivedRun.current) {
        receivedRun.current = true
        setSelectedRunId(run.id)
      }
    },
    onError(error) {
      setSubmissionError(error.message)
    },
  })

  const fileId = savedFileId || files[0]?.id || ''
  const model = chosenModel || models?.default || ''
  const modelOptions = models ? Array.from(new Set([models.default, ...models.options].filter(Boolean))) : []
  const submitting = phase !== null
  const pendingRuns = runs.some(isPending)
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? runs[0]
  const fileName = (id: string) => files.find((file) => file.id === id)?.name || id

  const refreshRuns = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await workspaceRequest(workspaceUrl, { signal, cache: 'no-store' })
      const snapshot: Workspace = await response.json()
      if (signal?.aborted) return
      setRuns((current) => mergeWorkspaceRuns(current, snapshot.runs))
      setFiles((current) => {
        const knownIds = new Set(snapshot.files.map((file) => file.id))
        return [...current.filter((file) => !knownIds.has(file.id)), ...snapshot.files]
      })
      setRefreshError(null)
    } catch (cause) {
      if (!signal?.aborted) setRefreshError(cause instanceof Error ? cause.message : 'Could not refresh runs.')
    }
  }, [workspaceUrl])

  useEffect(() => {
    if (!pendingRuns || submitting) return
    const controller = new AbortController()
    let timer = window.setTimeout(poll, 1500)

    async function poll() {
      await refreshRuns(controller.signal)
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 1500)
    }

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [pendingRuns, submitting, refreshRuns])

  async function refreshHistory() {
    setRefreshing(true)
    await refreshRuns()
    setRefreshing(false)
  }

  function clearUpload() {
    if (fileInput.current) fileInput.current.value = ''
    setUpload(null)
  }

  async function runAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || (!upload && !fileId)) return
    setSubmissionError(null)
    setPhase(upload ? 'uploading' : 'running')

    try {
      let runFileId = fileId
      if (upload) {
        const form = new FormData()
        form.set('file', upload)
        const response = await workspaceRequest(`${workspaceUrl}/files`, { method: 'POST', body: form })
        const saved: WorkspaceFile = await response.json()
        setFiles((current) => [saved, ...current])
        setSavedFileId(saved.id)
        clearUpload()
        runFileId = saved.id
        setPhase('running')
      }

      receivedRun.current = false
      setMessages([])
      const focus = prompt.trim()
      await sendMessage({ text: focus || 'Analyze CSV' }, {
        body: { file_id: runFileId, model: model || undefined, prompt: focus || undefined },
      })
      if (!receivedRun.current) await refreshRuns()
    } catch (cause) {
      setSubmissionError(cause instanceof Error ? cause.message : 'Could not start the analysis.')
    } finally {
      setPhase(null)
    }
  }

  return (
    <div className="space-y-5">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
        Workspace ID <code className="break-all rounded bg-muted px-2 py-1 font-mono text-xs text-foreground">{initialWorkspace.id}</code>
      </p>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader className="p-5">
              <h2 className="text-lg font-semibold tracking-tight">New analysis</h2>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              <form onSubmit={runAnalysis} className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <Label htmlFor="workspace-upload">Upload CSV</Label>
                    {upload && <Button type="button" variant="ghost" size="sm" onClick={clearUpload} disabled={submitting}>Clear file</Button>}
                  </div>
                  <Input ref={fileInput} id="workspace-upload" type="file" accept=".csv,text/csv" aria-describedby="workspace-upload-limit" disabled={submitting} onChange={(event) => setUpload(event.target.files?.[0] ?? null)} />
                  <p id="workspace-upload-limit" className="text-xs text-muted-foreground">Up to 5 MiB</p>
                </div>

                {files.length > 0 && (
                  <div className="space-y-2">
                    <Label htmlFor="workspace-saved-file">Saved CSV</Label>
                    <select id="workspace-saved-file" value={upload ? '' : fileId} disabled={submitting} className={selectClass} onChange={(event) => {
                      setSavedFileId(event.target.value)
                      clearUpload()
                    }}>
                      {upload && <option value="" disabled>Using new upload</option>}
                      {files.map((file) => <option key={file.id} value={file.id}>{file.name}</option>)}
                    </select>
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="workspace-model">{t('model')}</Label>
                  <select id="workspace-model" value={model} onChange={(event) => setChosenModel(event.target.value)} disabled={loadingModels || submitting || modelOptions.length === 0} className={selectClass}>
                    {modelOptions.length > 0 ? modelOptions.map((item) => <option key={item} value={item}>{item}</option>) : (
                      <option value="">{loadingModels ? t('loading') : 'Server default'}</option>
                    )}
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="workspace-prompt">Analysis focus <span className="font-normal text-muted-foreground">(optional)</span></Label>
                  <Textarea id="workspace-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={submitting} placeholder="For example, compare revenue by region." />
                </div>

                {submissionError && <p role="alert" className="break-words text-sm text-destructive">{submissionError}</p>}
                <Button type="submit" disabled={submitting || loadingModels || (!upload && !fileId)} className="w-full gap-2">
                  {submitting ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
                  {phase === 'uploading' ? 'Uploading CSV…' : phase === 'running' ? 'Running analysis…' : 'Run analysis'}
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 p-5">
              <h2 className="text-lg font-semibold tracking-tight">Run history</h2>
              <Button type="button" variant="ghost" size="sm" disabled={refreshing} onClick={() => void refreshHistory()}>{refreshing ? 'Refreshing…' : 'Refresh'}</Button>
            </CardHeader>
            <CardContent className="space-y-3 px-5 pb-5">
              {refreshError && <p role="status" className="break-words text-sm text-destructive">{refreshError}</p>}
              {runs.length > 0 ? (
                <ul className="-mx-1 max-h-80 space-y-2 overflow-y-auto p-1">
                  {runs.map((run) => (
                    <li key={run.id}>
                      <button type="button" aria-pressed={selectedRun?.id === run.id} onClick={() => setSelectedRunId(run.id)} className={cn(
                        'grid w-full gap-1 rounded-md border p-3 text-left text-sm hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                        selectedRun?.id === run.id && 'border-foreground/30 bg-muted',
                      )}>
                        <span className="min-w-0 break-words font-medium">{fileName(run.file_id)}</span>
                        <time dateTime={run.created_at} className="text-xs text-muted-foreground">{dateFormat.format(new Date(run.created_at))}</time>
                        <RunStatus run={run} />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted-foreground">No runs yet.</p>}
            </CardContent>
          </Card>
        </div>

        <Card className="min-w-0">
          <CardHeader className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold tracking-tight">Run results</h2>
            {selectedRun && <CardDescription className="break-words">{fileName(selectedRun.file_id)} · {selectedRun.model}</CardDescription>}
          </CardHeader>
          <CardContent className="px-5 pb-5 sm:px-6 sm:pb-6">
            {selectedRun ? (
              <div className="space-y-5">
                <div role="status" className="flex flex-wrap items-center gap-2">
                  {isPending(selectedRun) && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />}
                  <RunStatus run={selectedRun} />
                </div>
                {selectedRun.prompt && <p className="break-words text-sm text-muted-foreground">{selectedRun.prompt}</p>}
                {selectedRun.status === 'failed' && <p role="alert" className="break-words rounded-md border border-destructive/40 p-3 text-sm text-destructive">{selectedRun.error || 'Analysis failed.'}</p>}
                {selectedRun.status === 'completed' && <WorkspaceArtifacts key={selectedRun.id} url={`${workspaceUrl}/runs/${encodeURIComponent(selectedRun.id)}/artifacts`} />}
              </div>
            ) : (
              <div className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-md border border-dashed bg-muted/30 p-6 text-center">
                <FileSpreadsheet className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p role={submitting ? 'status' : undefined} className="text-sm text-muted-foreground">
                  {submitting ? 'Preparing analysis…' : 'Run an analysis to see its report and chart here.'}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
