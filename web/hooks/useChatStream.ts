import { useState, useRef, useCallback, useEffect } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment, PendingInterrupt, StreamEvent } from '@/types/chat'
import { getApiBaseUrl } from '@/lib/api'
import { createAppError } from '@/lib/errors'

interface UseChatStreamProps {
  selectedModel: string
  searchMode: string
}

// Throttle status updates to reduce re-renders
const STATUS_THROTTLE_MS = 150

export function useChatStream({ selectedModel, searchMode }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterrupt | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)

  // Throttled status update
  const lastStatusUpdateRef = useRef<number>(0)
  const pendingStatusRef = useRef<string>('')
  const statusTimerRef = useRef<NodeJS.Timeout | null>(null)

  const clearPendingStatusTimer = useCallback(() => {
    if (statusTimerRef.current) {
      clearTimeout(statusTimerRef.current)
      statusTimerRef.current = null
    }
  }, [])

  const throttledSetStatus = useCallback((text: string) => {
    const now = Date.now()
    if (now - lastStatusUpdateRef.current >= STATUS_THROTTLE_MS) {
      lastStatusUpdateRef.current = now
      setCurrentStatus(text)
    } else {
      // Schedule update
      pendingStatusRef.current = text
      if (!statusTimerRef.current) {
        statusTimerRef.current = setTimeout(() => {
          setCurrentStatus(pendingStatusRef.current)
          lastStatusUpdateRef.current = Date.now()
          statusTimerRef.current = null
        }, STATUS_THROTTLE_MS)
      }
    }
  }, [])

  useEffect(() => {
    return () => {
      clearPendingStatusTimer()
    }
  }, [clearPendingStatusTimer])

  // Use Set for O(1) artifact deduplication
  const artifactIdsRef = useRef(new Set<string>())

  const handleStop = useCallback(async () => {
    if (threadId) {
      try {
        await fetch(
          `${getApiBaseUrl()}/api/chat/cancel/${threadId}`,
          { method: 'POST' }
        )
        setCurrentStatus('Sending cancel request...')
      } catch (err) {
        console.error('Cancel request failed', err)
      }
    }
    clearPendingStatusTimer()
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
    setCurrentStatus('Cancelled')
    setTimeout(() => setCurrentStatus(''), 3000)
  }, [threadId, clearPendingStatusTimer])

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
      if (threadHeader) {
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
      }

      setMessages((prev) => [...prev, assistantMessage])

      const upsertAssistantMessage = () => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantMessage.id ? { ...assistantMessage } : msg)),
        )
      }
      let assistantFlushTimer: NodeJS.Timeout | null = null
      const flushAssistantMessage = () => {
        if (assistantFlushTimer) {
          clearTimeout(assistantFlushTimer)
          assistantFlushTimer = null
        }
        upsertAssistantMessage()
      }
      const scheduleAssistantFlush = () => {
        if (!assistantFlushTimer) {
          assistantFlushTimer = setTimeout(() => {
            assistantFlushTimer = null
            upsertAssistantMessage()
          }, 32)
        }
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
              const data = JSON.parse(line.slice(2)) as StreamEvent

              if (data.type === 'status') {
                throttledSetStatus(data.data.text)
              } else if (data.type === 'text') {
                assistantMessage.content += data.data.content
                scheduleAssistantFlush()
              } else if (data.type === 'message') {
                assistantMessage.content = data.data.content
                flushAssistantMessage()
              } else if (data.type === 'interrupt') {
                flushAssistantMessage()
                interrupted = true
                setPendingInterrupt(data.data)
                const msg = data.data?.message || data.data?.prompts?.[0]?.message
                setCurrentStatus(msg || 'Approval required before continuing')
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
                const toolInvocation: ToolInvocation = {
                  toolCallId: `tool-${Date.now()}-${Math.random()}`,
                  toolName: data.data.name,
                  state: data.data.status === 'completed' ? 'completed' : 'running',
                  args: data.data.query ? { query: data.data.query } : {},
                }

                assistantMessage.toolInvocations = [
                  ...(assistantMessage.toolInvocations || []),
                  toolInvocation,
                ]

                flushAssistantMessage()
              } else if (data.type === 'completion') {
                assistantMessage.content = data.data.content
                flushAssistantMessage()
              } else if (data.type === 'artifact') {
                const newArtifact = data.data as Artifact
                // Use Set for O(1) deduplication
                if (!artifactIdsRef.current.has(newArtifact.id)) {
                  artifactIdsRef.current.add(newArtifact.id)
                  setArtifacts((prev) => [...prev, newArtifact])
                }
              }
            } catch (err) {
              console.error('Error parsing stream data:', err)
            }
          }
        }

        if (interrupted) break
      }

      flushAssistantMessage()
      clearPendingStatusTimer()
      setCurrentStatus('')
    } catch (error: unknown) {
      const appError = createAppError(error)

      if (appError.code !== 'TIMEOUT') {
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: appError.message,
            isError: true,
            retryable: appError.retryable,
          } as Message,
        ])
      }

      console.error('Chat error:', appError)
    } finally {
      clearPendingStatusTimer()
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [selectedModel, searchMode, throttledSetStatus, clearPendingStatusTimer])

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
