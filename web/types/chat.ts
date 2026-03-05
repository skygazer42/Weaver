export interface ToolInvocation {
  toolName: string
  toolCallId: string
  state: 'running' | 'completed' | 'failed'
  args?: any
  result?: any
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
}

export interface Artifact {
  id: string
  sessionId?: string
  // Backend may emit richer artifact types (e.g. reports/charts) during streaming.
  type: 'code' | 'image' | 'text' | 'file' | 'report' | 'chart'
  title: string
  content: string
  image?: string // Base64 image payload (e.g. chart screenshots)
  mimeType?: string
  fileSize?: number
  createdAt: number
  updatedAt: number
  tags?: string[]
}
