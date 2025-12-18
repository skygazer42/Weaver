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

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  toolInvocations?: ToolInvocation[]
  sources?: MessageSource[]
}

export interface ChatSession {
  id: string
  title: string
  date: string
}

export interface Artifact {
  id: string
  type: string
  title: string
  content: string
  image?: string
}
