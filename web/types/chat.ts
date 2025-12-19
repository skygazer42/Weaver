export interface ToolInvocation {
  toolName: string
  toolCallId: string
  state: 'running' | 'completed' | 'failed'
  args?: any
  result?: any
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
  type: 'code' | 'image' | 'text' | 'file'
  title: string
  content: string
  mimeType?: string
  fileSize?: number
  createdAt: number
  updatedAt: number
  tags?: string[]
}
