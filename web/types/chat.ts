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
  // Error state
  isError?: boolean
  retryable?: boolean
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
  type: 'code' | 'image' | 'text' | 'file' | 'report' | 'chart'
  title: string
  content: string
  // Base64 payload for image-like artifacts (charts, screenshots, etc.)
  image?: string
  mimeType?: string
  fileSize?: number
  createdAt: number
  updatedAt: number
  tags?: string[]
}

// Research Visualization Types
export interface ResearchNode {
  id: string
  topic: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  depth: number
  parentId: string | null
  childrenIds: string[]
  sources: ResearchSource[]
  summary: string
}

export interface ResearchSource {
  title: string
  url: string
  provider?: string
  score?: number
}

export interface ResearchQualityMetrics {
  coverage: number
  citation: number
  consistency: number
}

export interface ResearchTree {
  rootId: string
  nodes: Record<string, ResearchNode>
}

export interface ResearchEvent {
  type: 'research_node_start' | 'research_node_complete' | 'research_tree_update' | 'search'
  data: any
  timestamp: number
}
