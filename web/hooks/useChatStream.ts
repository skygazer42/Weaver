import { useState, useRef, useCallback, useEffect } from 'react'
import { Message, Artifact, ImageAttachment, PendingInterrupt, StreamEvent } from '@/types/chat'
import {
  getApiBaseUrl,
  getChatStreamProtocol,
  getChatStreamUrl,
  getResearchStreamProtocol,
  getResearchStreamUrl,
} from '@/lib/api'
import { createAppError } from '@/lib/errors'
import { toNullableSearchMode, type SearchMode } from '@/lib/chat-mode'
import { applyToolStreamEvent } from '@/lib/stream/toolInvocations'
import { buildHitlDecisions, isHitlToolApprovalRequest } from '@/lib/hitl'

interface UseChatStreamProps {
  selectedModel: string
  searchMode: SearchMode
}

export type ConnectionState = 'connected' | 'reconnecting' | 'disconnected'

// Throttle status updates to reduce re-renders
const STATUS_THROTTLE_MS = 150
const MAX_STREAM_RETRIES = 3
const RETRY_BASE_DELAY_MS = 1000

export function useChatStream({ selectedModel, searchMode }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterrupt | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('connected')

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

  const consumeStream = useCallback(
    async (response: Response, streamProtocol: 'sse' | 'legacy'): Promise<void> => {
      const threadHeader = response.headers.get('X-Thread-ID') || response.headers.get('x-thread-id')
      if (threadHeader) {
        setThreadId(threadHeader)
      } else if (streamProtocol === 'legacy') {
        // Legacy research stream may not set X-Thread-ID; clear to avoid stale inspector state.
        setThreadId(null)
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

      setMessages((prev: Message[]) => [...prev, assistantMessage])

      const upsertAssistantMessage = () => {
        setMessages((prev: Message[]) =>
          prev.map((msg: Message) => (msg.id === assistantMessage.id ? { ...assistantMessage } : msg)),
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

      const handleStreamEvent = (data: StreamEvent) => {
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
          setMessages((prev: Message[]) => [
            ...prev,
            {
              id: `interrupt-${Date.now()}`,
              role: 'assistant',
              content: msg || 'Approval required before running a tool.',
            },
          ])
        } else if (data.type === 'tool') {
          assistantMessage.toolInvocations = applyToolStreamEvent(
            assistantMessage.toolInvocations || [],
            data.data,
          )
          flushAssistantMessage()
        } else if (data.type === 'completion') {
          assistantMessage.content = data.data.content
          flushAssistantMessage()
        } else if (data.type === 'sources') {
          assistantMessage.sources = data.data.items
          flushAssistantMessage()
        } else if (data.type === 'artifact') {
          const newArtifact = data.data as Artifact
          if (!artifactIdsRef.current.has(newArtifact.id)) {
            artifactIdsRef.current.add(newArtifact.id)
            setArtifacts((prev: Artifact[]) => [...prev, newArtifact])
          }
        } else if (data.type === 'error') {
          const message = data.data.message || 'An error occurred.'
          flushAssistantMessage()
          setCurrentStatus(message)
          setMessages((prev: Message[]) => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: 'assistant',
              content: message,
              isError: true,
              retryable: false,
            } as Message,
          ])
        } else if (data.type === 'done') {
          flushAssistantMessage()
        }
      }

      const parseSseFrame = (frame: string): StreamEvent | null => {
        const lines = frame.split('\n').map((l) => l.trimEnd())
        let eventName = ''
        const dataLines: string[] = []

        for (const line of lines) {
          if (!line) continue
          if (line.startsWith(':')) continue // comment/keepalive

          if (line.startsWith('event:')) {
            eventName = line.slice('event:'.length).trim()
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice('data:'.length).trimStart())
          }
        }

        if (dataLines.length === 0) return null
        const dataText = dataLines.join('\n')

        let parsed: unknown
        try {
          parsed = JSON.parse(dataText) as unknown
        } catch {
          return null
        }

        // Prefer the legacy envelope if present: { type, data }
        if (parsed && typeof parsed === 'object' && 'type' in parsed && 'data' in parsed) {
          return parsed as StreamEvent
        }

        if (!eventName) return null
        return { type: eventName as StreamEvent['type'], data: parsed as any } as StreamEvent
      }

      let interrupted = false
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        if (streamProtocol === 'legacy') {
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const rawLine of lines) {
            const line = rawLine.trim()
            if (!line) continue
            if (!line.startsWith('0:')) continue

            try {
              const data = JSON.parse(line.slice(2)) as StreamEvent
              handleStreamEvent(data)
            } catch (err) {
              console.error('Error parsing stream data:', err)
            }

            if (interrupted) break
          }
        } else {
          buffer = buffer.replace(/\r\n/g, '\n')
          const frames = buffer.split('\n\n')
          buffer = frames.pop() || ''

          for (const frame of frames) {
            const data = parseSseFrame(frame)
            if (data) handleStreamEvent(data)
            if (interrupted) break
          }
        }

        if (interrupted) break
      }

      flushAssistantMessage()
      clearPendingStatusTimer()
      setCurrentStatus('')
    },
    [clearPendingStatusTimer, throttledSetStatus],
  )

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
    setConnectionState('connected')
    let retryCount = 0

    const attemptStream = async (): Promise<void> => {
      abortControllerRef.current = new AbortController()

      try {
        const streamProtocol = getChatStreamProtocol()
        const response = await fetch(
          getChatStreamUrl(),
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              messages: messageHistory.map(m => ({ role: m.role, content: m.content })),
              stream: true,
              model: selectedModel,
              search_mode: toNullableSearchMode(searchMode),
              images: (images || []).map(img => ({
                name: img.name,
                mime: img.mime,
                data: img.data
              }))
            }),
            signal: abortControllerRef.current.signal
          }
        )

        // Transient server errors — retry with backoff
        if (response.status >= 500 && retryCount < MAX_STREAM_RETRIES) {
          retryCount++
          setConnectionState('reconnecting')
          const delay = RETRY_BASE_DELAY_MS * Math.pow(2, retryCount - 1)
          throttledSetStatus(`Reconnecting... (attempt ${retryCount}/${MAX_STREAM_RETRIES})`)
          await new Promise(r => setTimeout(r, delay))
          return attemptStream()
        }

        if (!response.ok) {
          throw new Error('Failed to get response')
        }

        setConnectionState('connected')
        await consumeStream(response, streamProtocol)
      } catch (error: unknown) {
        // Skip retry on user-initiated abort
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        // Retry on network errors
        if (retryCount < MAX_STREAM_RETRIES) {
          retryCount++
          setConnectionState('reconnecting')
          const delay = RETRY_BASE_DELAY_MS * Math.pow(2, retryCount - 1)
          throttledSetStatus(`Connection lost. Reconnecting... (${retryCount}/${MAX_STREAM_RETRIES})`)
          await new Promise(r => setTimeout(r, delay))
          return attemptStream()
        }

        setConnectionState('disconnected')
        const appError = createAppError(error)

        if (appError.code !== 'TIMEOUT') {
          setMessages((prev: Message[]) => [
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
      }
    }

    try {
      await attemptStream()
    } finally {
      clearPendingStatusTimer()
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [selectedModel, searchMode, throttledSetStatus, clearPendingStatusTimer, consumeStream])

  const processResearch = useCallback(async (query: string, images?: ImageAttachment[]) => {
    const safeQuery = String(query || '').trim()
    if (!safeQuery) {
      setMessages((prev: Message[]) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: 'Usage: /research <query>',
          isError: true,
          retryable: false,
        } as Message,
      ])
      return
    }

    setIsLoading(true)
    setConnectionState('connected')
    let retryCount = 0

    const attemptStream = async (): Promise<void> => {
      abortControllerRef.current = new AbortController()

      try {
        const streamProtocol = getResearchStreamProtocol()
        const url = getResearchStreamUrl(safeQuery)

        const response = await fetch(url, {
          method: 'POST',
          headers:
            streamProtocol === 'legacy'
              ? { Accept: 'text/event-stream' }
              : {
                Accept: 'text/event-stream',
                'Content-Type': 'application/json',
              },
          body:
            streamProtocol === 'legacy'
              ? undefined
              : JSON.stringify({
                query: safeQuery,
                model: selectedModel,
                search_mode: toNullableSearchMode(searchMode),
                images: (images || []).map(img => ({
                  name: img.name,
                  mime: img.mime,
                  data: img.data,
                })),
              }),
          signal: abortControllerRef.current.signal,
        })

        // Transient server errors — retry with backoff
        if (response.status >= 500 && retryCount < MAX_STREAM_RETRIES) {
          retryCount++
          setConnectionState('reconnecting')
          const delay = RETRY_BASE_DELAY_MS * Math.pow(2, retryCount - 1)
          throttledSetStatus(`Reconnecting... (attempt ${retryCount}/${MAX_STREAM_RETRIES})`)
          await new Promise(r => setTimeout(r, delay))
          return attemptStream()
        }

        if (!response.ok) {
          throw new Error('Failed to start research stream')
        }

        setConnectionState('connected')
        await consumeStream(response, streamProtocol)
      } catch (error: unknown) {
        // Skip retry on user-initiated abort
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        // Retry on network errors
        if (retryCount < MAX_STREAM_RETRIES) {
          retryCount++
          setConnectionState('reconnecting')
          const delay = RETRY_BASE_DELAY_MS * Math.pow(2, retryCount - 1)
          throttledSetStatus(`Connection lost. Reconnecting... (${retryCount}/${MAX_STREAM_RETRIES})`)
          await new Promise(r => setTimeout(r, delay))
          return attemptStream()
        }

        setConnectionState('disconnected')
        const appError = createAppError(error)

        if (appError.code !== 'TIMEOUT') {
          setMessages((prev: Message[]) => [
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

        console.error('Research error:', appError)
      }
    }

    try {
      await attemptStream()
    } finally {
      clearPendingStatusTimer()
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [clearPendingStatusTimer, consumeStream, searchMode, selectedModel, throttledSetStatus])

  const resumeInterruptWithPayload = useCallback(
    async (resumePayload: unknown) => {
      if (!pendingInterrupt || !threadId) return
      setIsLoading(true)
      setCurrentStatus('Resuming...')
      let interruptedAgain = false
      let resumedToCompletion = false
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/interrupt/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            thread_id: threadId,
            payload: resumePayload,
            model: selectedModel,
            search_mode: toNullableSearchMode(searchMode),
          }),
        })
        if (!res.ok) throw new Error('Failed to resume')

        const data = (await res.json()) as unknown

        // Graph resumed but immediately interrupted again (nested HITL).
        if (data && typeof data === 'object' && !Array.isArray(data)) {
          const record = data as Record<string, unknown>
          if (record.status === 'interrupted' && Array.isArray(record.interrupts)) {
            interruptedAgain = true
            setPendingInterrupt({ prompts: record.interrupts as any[] })
            const msg =
              (record.interrupts?.[0] as any)?.message ||
              'Approval required before continuing.'
            setCurrentStatus(String(msg || 'Approval required before continuing.'))
            setMessages((prev: Message[]) => [
              ...prev,
              {
                id: `interrupt-${Date.now()}`,
                role: 'assistant',
                content: String(msg || 'Approval required before continuing.'),
              },
            ])
            return
          }
        }

        setMessages((prev: Message[]) => [
          ...prev,
          {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: (data as any)?.content || 'Resumed and completed.',
          },
        ])
        resumedToCompletion = true
      } catch (err) {
        console.error('Failed to resume interrupt', err)
        setMessages((prev: Message[]) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: 'Resume failed. Please retry.',
          },
        ])
      } finally {
        setIsLoading(false)
        if (!interruptedAgain && resumedToCompletion) setPendingInterrupt(null)
        if (!interruptedAgain) setCurrentStatus('')
      }
    },
    [pendingInterrupt, threadId, selectedModel, searchMode],
  )

  const handleApproveInterrupt = useCallback(async () => {
    if (!pendingInterrupt || !threadId) return

    const prompt = pendingInterrupt?.prompts?.[0]
    if (isHitlToolApprovalRequest(prompt)) {
      const decisions = buildHitlDecisions(prompt, { type: 'approve' })
      await resumeInterruptWithPayload({ decisions })
      return
    }

    // Generic interrupt approval: resume with empty payload.
    await resumeInterruptWithPayload({})
  }, [pendingInterrupt, threadId, resumeInterruptWithPayload])

  const handleRejectInterrupt = useCallback(
    async (message?: string) => {
      if (!pendingInterrupt || !threadId) return

      const prompt = pendingInterrupt?.prompts?.[0]
      if (!isHitlToolApprovalRequest(prompt)) {
        // Non-tool interrupts don't support reject semantics yet; dismiss.
        setPendingInterrupt(null)
        return
      }

      const decisions = buildHitlDecisions(prompt, {
        type: 'reject',
        message: message || 'User rejected tool execution.',
      })
      await resumeInterruptWithPayload({ decisions })
    },
    [pendingInterrupt, threadId, resumeInterruptWithPayload],
  )

  const handleEditInterrupt = useCallback(
    async (editedArgs: Array<Record<string, unknown> | undefined>) => {
      if (!pendingInterrupt || !threadId) return

      const prompt = pendingInterrupt?.prompts?.[0]
      if (!isHitlToolApprovalRequest(prompt)) return

      const decisions = buildHitlDecisions(prompt, { type: 'edit', editedArgs })
      await resumeInterruptWithPayload({ decisions })
    },
    [pendingInterrupt, threadId, resumeInterruptWithPayload],
  )

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
    connectionState,
    processChat,
    processResearch,
    handleStop,
    handleApproveInterrupt,
    handleRejectInterrupt,
    handleEditInterrupt,
  }
}
