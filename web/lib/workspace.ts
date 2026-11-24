import { DefaultChatTransport, type UIMessage } from 'ai'
import { getApiBaseUrl } from './api'

export interface WorkspaceFile {
  id: string
  name: string
  size: number
  created_at: string
}

export interface WorkspaceRun {
  id: string
  file_id: string
  model: string
  prompt: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  step: 'queued' | 'sandbox' | 'report' | 'completed' | 'failed'
  error: string | null
  created_at: string
  updated_at: string
}

export interface WorkspaceMetadata {
  name: string
  instructions: string
  decisions: string
}

export interface Workspace extends WorkspaceMetadata {
  id: string
  files: WorkspaceFile[]
  runs: WorkspaceRun[]
}

export type ProjectWorkflow = 'requirements-spec' | 'release-brief'

export interface ProjectTask {
  id: string
  workflow: ProjectWorkflow
  prompt: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'insufficient_evidence' | 'awaiting_approval'
  repository?: string | null
  release_tag?: string | null
  file_ids?: string[] | null
  artifact_id?: string | null
  error?: string | null
  created_at?: string
  schedule_id?: string | null
}

export interface ProjectSchedule {
  id: string
  workflow: ProjectWorkflow
  prompt: string
  repository: string | null
  release_tag: string | null
  repeat_days: 1 | 7
  next_run_at: string
  enabled: boolean
  last_task_id: string | null
}

export interface WorkspaceDeliverable {
  id: string
  task_id: string
  title: string
  content: string
  sources: { id: string; title: string; kind: string; snippet: string; url?: string | null; release_tag?: string | null }[]
  workflow: ProjectWorkflow
  based_on?: string | null
  created_at: string
}

export type WorkspaceMessage = UIMessage<unknown, { run: WorkspaceRun }>

const stepOrder: Record<WorkspaceRun['step'], number> = {
  queued: 0,
  sandbox: 1,
  report: 2,
  completed: 3,
  failed: 3,
}

export function mergeWorkspaceRuns(current: WorkspaceRun[], incoming: WorkspaceRun[]): WorkspaceRun[] {
  const runs = new Map(current.map((run) => [run.id, run]))
  for (const run of incoming) {
    const known = runs.get(run.id)
    if (known) {
      const timestampOrder = run.updated_at.localeCompare(known.updated_at)
      if (timestampOrder < 0 || (timestampOrder === 0 && stepOrder[run.step] < stepOrder[known.step])) continue
    }
    runs.set(run.id, run)
  }
  return Array.from(runs.values()).sort((a, b) => b.created_at.localeCompare(a.created_at))
}

export function getWorkspaceUrl(id?: string): string {
  const root = `${getApiBaseUrl()}/api/workspaces`
  return id ? `${root}/${encodeURIComponent(id)}` : root
}

export async function workspaceRequest(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    const message = Array.isArray(detail) ? detail[0]?.msg : detail
    throw new Error(typeof message === 'string' ? message : `Workspace request failed (${response.status}).`)
  }
  return response
}

export async function uploadWorkspaceFile(workspaceUrl: string, file: File): Promise<WorkspaceFile> {
  const form = new FormData()
  form.set('file', file)
  const response = await workspaceRequest(`${workspaceUrl}/files`, { method: 'POST', body: form })
  return response.json()
}

export function createWorkspaceRunTransport(url: string): DefaultChatTransport<WorkspaceMessage> {
  return new DefaultChatTransport({
    api: url,
    fetch: workspaceRequest,
    prepareSendMessagesRequest: ({ body }) => ({ body: body ?? {} }),
  })
}
