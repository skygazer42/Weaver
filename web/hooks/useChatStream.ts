import { useState, useRef, useCallback } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment, ProcessEvent, RunMetrics, MessageSource } from '@/types/chat'
import { getApiBaseUrl } from '@/lib/api'

interface UseChatStreamProps {
  selectedModel: string
  searchMode: string
}

export function useChatStream({ selectedModel, searchMode }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [pendingInterrupt, setPendingInterrupt] = useState<any>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  
  const abortControllerRef = useRef<AbortController | null>(null)

  const handleStop = useCallback(async () => {
    // 优先通知后端取消当前线程
    if (threadId) {
      try {
        await fetch(
          `${getApiBaseUrl()}/api/chat/cancel/${threadId}`,
          { method: 'POST' }
        )
        setCurrentStatus('已发送取消请求...')
      } catch (err) {
        console.error('取消请求失败', err)
      }
    }
    // 同时中断前端的 SSE
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
    setCurrentStatus('已取消')
    setTimeout(() => setCurrentStatus(''), 3000)
  }, [threadId])

  const processChat = useCallback(async (messageHistory: Message[], images?: ImageAttachment[]) => {
    setIsLoading(true)
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(
        `${getApiBaseUrl()}/api/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            messages: messageHistory.map(m => ({ role: m.role, content: m.content })),
            stream: true,
            model: selectedModel,
            search_mode: searchMode,
            images: (images || []).map(img => ({
              name: img.name,
              mime: img.mime,
              data: img.data
            }))
          }),
          signal: abortControllerRef.current.signal
        }
      )

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const threadHeader = response.headers.get('X-Thread-ID') || response.headers.get('x-thread-id')
      console.log('[useChatStream] Response headers:', {
        'X-Thread-ID': response.headers.get('X-Thread-ID'),
        'x-thread-id': response.headers.get('x-thread-id'),
        threadHeader
      })
      if (threadHeader) {
        console.log('[useChatStream] Setting threadId:', threadHeader)
        setThreadId(threadHeader)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No reader available')
      }

      let assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: '',
        toolInvocations: [],
        processEvents: [],
        createdAt: Date.now(),
        isStreaming: true,
      }

      console.log('[useChatStream] Creating assistant message:', {
        id: assistantMessage.id,
        role: assistantMessage.role,
        currentMessagesCount: messages.length
      })

      setMessages((prev) => [...prev, assistantMessage])

      const pushProcessEvent = (type: string, payload: any) => {
        const now = Date.now()
        const next: ProcessEvent = {
          id: `evt-${now}-${Math.random().toString(16).slice(2)}`,
          type,
          timestamp: now,
          data: payload,
        }

        const prevEvents = assistantMessage.processEvents || []
        const last = prevEvents[prevEvents.length - 1]

        // Simple dedupe to avoid spammy UI.
        if (last?.type === type) {
          if (type === 'status' && last.data?.text && last.data?.text === payload?.text) return
          if (type === 'search' && last.data?.query && last.data?.query === payload?.query) return
        }

        const capped = [...prevEvents, next].slice(-200)
        assistantMessage.processEvents = capped
      }

      const syncAssistantMessage = () => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantMessage.id ? { ...assistantMessage } : msg))
        )
      }

      let interrupted = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter((line) => line.trim())

        for (const line of lines) {
          if (line.startsWith('0:')) {
            try {
              const data = JSON.parse(line.slice(2))

              if (data.type === 'status') {
                setCurrentStatus(data.data.text)
                pushProcessEvent('status', data.data)
                syncAssistantMessage()
              } else if (data.type === 'text') {
                assistantMessage.content += data.data.content
                console.log('[useChatStream] Updating message (text):', {
                  id: assistantMessage.id,
                  role: assistantMessage.role,
                  contentLength: assistantMessage.content.length
                })
                syncAssistantMessage()
              } else if (data.type === 'message') {
                assistantMessage.content = data.data.content
                syncAssistantMessage()
              } else if (data.type === 'interrupt') {
                interrupted = true
                setPendingInterrupt(data.data)
                const msg = data.data?.message || data.data?.prompts?.[0]?.message
                setCurrentStatus(msg || 'Approval required before continuing')
                assistantMessage.isStreaming = false
                assistantMessage.completedAt = Date.now()
                pushProcessEvent('interrupt', data.data)
                syncAssistantMessage()
                setMessages((prev) => [
                  ...prev,
                  {
                    id: `interrupt-${Date.now()}`,
                    role: 'assistant',
                    content: msg || 'Approval required before running a tool.',
                  },
                ])
                break
              } else if (data.type === 'tool') {
                const toolCallId =
                  data.data.toolCallId || `tool-${Date.now()}-${Math.random()}`

                const state: ToolInvocation['state'] =
                  data.data.status === 'completed'
                    ? 'completed'
                    : data.data.status === 'failed'
                      ? 'failed'
                      : 'running'

                const toolInvocation: ToolInvocation = {
                  toolCallId,
                  toolName: data.data.name,
                  state,
                  args: data.data.args || (data.data.query ? { query: data.data.query } : {}),
                }

                const prevTools = assistantMessage.toolInvocations || []
                const existingIndex = prevTools.findIndex((t) => t.toolCallId === toolCallId)
                if (existingIndex >= 0) {
                  const nextTools = [...prevTools]
                  nextTools[existingIndex] = { ...nextTools[existingIndex], ...toolInvocation }
                  assistantMessage.toolInvocations = nextTools
                } else {
                  assistantMessage.toolInvocations = [...prevTools, toolInvocation]
                }

                pushProcessEvent('tool', data.data)
                syncAssistantMessage()
              } else if (
                [
                  'thinking',
                  'tool_start',
                  'tool_result',
                  'tool_error',
                  'search',
                  'screenshot',
                  'task_update',
                  'research_node_start',
                  'research_node_complete',
                  'research_tree_update',
                  'quality_update',
                ].includes(data.type)
              ) {
                pushProcessEvent(data.type, data.data)
                syncAssistantMessage()
              } else if (data.type === 'sources') {
                const items = (data.data?.items || []) as MessageSource[]
                assistantMessage.sources = items
                syncAssistantMessage()
              } else if (data.type === 'completion') {
                assistantMessage.content = data.data.content
                assistantMessage.isStreaming = false
                assistantMessage.completedAt = Date.now()
                syncAssistantMessage()
              } else if (data.type === 'done') {
                const metrics = (data.data?.metrics || {}) as RunMetrics
                assistantMessage.metrics = metrics
                assistantMessage.isStreaming = false
                if (!assistantMessage.completedAt) assistantMessage.completedAt = Date.now()
                pushProcessEvent('done', data.data)
                syncAssistantMessage()
              } else if (data.type === 'cancelled') {
                const msg = data.data?.message || 'Task was cancelled'
                assistantMessage.content = assistantMessage.content || msg
                assistantMessage.isStreaming = false
                assistantMessage.completedAt = Date.now()
                pushProcessEvent('cancelled', data.data)
                syncAssistantMessage()
              } else if (data.type === 'error') {
                const msg = data.data?.message || 'An error occurred'
                assistantMessage.content = assistantMessage.content || msg
                assistantMessage.isStreaming = false
                assistantMessage.completedAt = Date.now()
                pushProcessEvent('error', data.data)
                syncAssistantMessage()
              } else if (data.type === 'artifact') {
                const newArtifact = data.data as Artifact
                setArtifacts((prev) => {
                  if (prev.some(a => a.id === newArtifact.id)) return prev
                  return [...prev, newArtifact]
                })
              }
            } catch (err) {
              console.error('Error parsing stream data:', err)
            }
          }
        }

        if (interrupted) break
      }

      if (assistantMessage.isStreaming) {
        assistantMessage.isStreaming = false
        if (!assistantMessage.completedAt) assistantMessage.completedAt = Date.now()
        syncAssistantMessage()
      }
      setCurrentStatus('')
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('Request aborted')
      } else {
        console.error('Error:', error)
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: 'Sorry, an error occurred. Please try again.',
          },
        ])
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [selectedModel, searchMode])

  const handleApproveInterrupt = useCallback(async () => {
    if (!pendingInterrupt || !threadId) return
    setIsLoading(true)
    setCurrentStatus('Resuming after approval...')
    try {
      const toolCalls = pendingInterrupt?.prompts?.[0]?.tool_calls
      const res = await fetch(
        `${getApiBaseUrl()}/api/interrupt/resume`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            thread_id: threadId,
            payload: { tool_approved: true, tool_calls: toolCalls },
            model: selectedModel,
            search_mode: searchMode
          })
        }
      )
      if (!res.ok) throw new Error('Failed to resume')
      const data = await res.json()
      setMessages(prev => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.content || 'Resumed and completed.',
        }
      ])
    } catch (err) {
      console.error('Failed to resume interrupt', err)
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: 'Resume failed. Please retry.',
        }
      ])
    } finally {
      setPendingInterrupt(null)
      setIsLoading(false)
      setCurrentStatus('')
    }
  }, [pendingInterrupt, threadId, selectedModel, searchMode])

  return {
    messages,
    setMessages,
    isLoading,
    setIsLoading,
    currentStatus,
    setCurrentStatus,
    artifacts,
    setArtifacts,
    pendingInterrupt,
    setPendingInterrupt,
    threadId,
    setThreadId,
    processChat,
    handleStop,
    handleApproveInterrupt
  }
}
