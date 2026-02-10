export interface ToolInvocation {
  toolName: string
  toolCallId: string
  state: 'running' | 'completed' | 'failed'
  args?: Record<string, unknown>
  result?: Record<string, unknown>
}

export interface MessageSource {
  title: string
  url: string
  rawUrl?: string
  domain?: string
  provider?: string
  publishedDate?: string
  freshnessDays?: number | null
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

// ──────────────────────────────────────────────
// Interrupt Types (replaces scattered `any`)
// ──────────────────────────────────────────────

export interface InterruptPrompt {
  message?: string
  tool_calls?: Array<{ id: string; name: string; args?: Record<string, unknown> }>
}

export interface PendingInterrupt {
  message?: string
  prompts?: InterruptPrompt[]
}

// ──────────────────────────────────────────────
// Stream Event Discriminated Union
// ──────────────────────────────────────────────

export type StreamEvent =
  | { type: 'status'; data: { text: string } }
  | { type: 'text'; data: { content: string } }
  | { type: 'message'; data: { content: string } }
  | { type: 'completion'; data: { content: string } }
  | { type: 'interrupt'; data: PendingInterrupt }
  | { type: 'tool'; data: { name: string; status: string; query?: string } }
  | { type: 'artifact'; data: Artifact }

// ──────────────────────────────────────────────
// Research Visualization Types
// ──────────────────────────────────────────────

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
  freshness?: number
  queryCoverage?: number
  warning?: string
}

export interface ResearchTree {
  rootId: string
  nodes: Record<string, ResearchNode>
}

export interface ResearchEvent {
  type: 'research_node_start' | 'research_node_complete' | 'research_tree_update' | 'search'
  data: Record<string, unknown>
  timestamp: number
}

