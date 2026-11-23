export interface ToolInvocation {
  toolName: string
  toolCallId: string
  state: 'running' | 'completed' | 'failed'
  args?: any
  result?: any
}

export const RUN_STATUS_LABELS = {
  queued: 'Queued',
  running: 'Running',
  awaiting_approval: 'Awaiting approval',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  insufficient_evidence: 'Insufficient evidence',
} as const

export type RunStatus = keyof typeof RUN_STATUS_LABELS

export interface ApprovalAction {
  id?: string
  name: string
  args?: Record<string, unknown> | string
  description?: string
}

export interface ApprovalPrompt {
  message?: string
  action_requests?: ApprovalAction[]
  tool_calls?: ApprovalAction[]
}

export interface PendingInterrupt extends ApprovalPrompt {
  interrupt_ids?: string[]
  prompts?: ApprovalPrompt[]
}

export interface ChatRun {
  id: string
  searchMode: string
  lastEventId?: number
  assistant?: Message
  interrupt?: PendingInterrupt
}

export interface ProcessEvent {
  id: string
  type: string
  timestamp: number
  data: any
}

export interface RunMetrics {
  run_id?: string
  model?: string
  route?: string
  started_at?: string
  ended_at?: string | null
  duration_ms?: number
  event_count?: number
  nodes_started?: Record<string, number>
  nodes_completed?: Record<string, number>
  errors?: string[]
  cancelled?: boolean
}

export interface MessageSource {
  title: string
  url: string
}

export interface ImageAttachment {
  name?: string
  mime?: string
  data?: string
  preview?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  toolInvocations?: ToolInvocation[]
  sources?: MessageSource[]
  attachments?: ImageAttachment[]
  processEvents?: ProcessEvent[]
  metrics?: RunMetrics
  createdAt?: number
  completedAt?: number
  isStreaming?: boolean
  runStatus?: RunStatus
  artifacts?: Artifact[]
}

export interface ChatSession {
  id: string
  title: string
  date: string // Legacy field, kept for compatibility
  updatedAt: number
  createdAt: number
  tags?: string[]
  isPinned?: boolean
  summary?: string
  searchMode?: string
}

export interface Artifact {
  id: string
  sessionId?: string
  // Backend may emit richer artifact types (e.g. reports/charts) during streaming.
  type: 'code' | 'image' | 'text' | 'file' | 'report' | 'chart' | 'tool_output'
  title: string
  content: string
  image?: string // Base64 image payload (e.g. chart screenshots)
  mimeType?: string
  fileSize?: number
  download_url?: string
  tool_call_id?: string
  createdAt: number
  updatedAt: number
  tags?: string[]
}
