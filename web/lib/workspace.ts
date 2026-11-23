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

export interface Workspace {
  id: string
  files: WorkspaceFile[]
  runs: WorkspaceRun[]
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

export function createWorkspaceRunTransport(url: string): DefaultChatTransport<WorkspaceMessage> {
  return new DefaultChatTransport({
    api: url,
    fetch: workspaceRequest,
    prepareSendMessagesRequest: ({ body }) => ({ body: body ?? {} }),
  })
}
