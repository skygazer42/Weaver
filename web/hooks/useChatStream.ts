import { useState, useRef, useCallback } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment } from '@/types/chat'

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
          `${process.env.NEXT_PUBLIC_API_URL}/api/chat/cancel/${threadId}`,
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
  }, [threadId])

  const processChat = useCallback(async (messageHistory: Message[], images?: ImageAttachment[]) => {
    setIsLoading(true)
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/chat`,
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
      }

      console.log('[useChatStream] Creating assistant message:', {
        id: assistantMessage.id,
        role: assistantMessage.role,
        currentMessagesCount: messages.length
      })

      setMessages((prev) => [...prev, assistantMessage])

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
              } else if (data.type === 'text') {
                assistantMessage.content += data.data.content
                console.log('[useChatStream] Updating message (text):', {
                  id: assistantMessage.id,
                  role: assistantMessage.role,
                  contentLength: assistantMessage.content.length
                })
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'message') {
                assistantMessage.content = data.data.content
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'interrupt') {
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

                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'completion') {
                assistantMessage.content = data.data.content
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
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
        `${process.env.NEXT_PUBLIC_API_URL}/api/interrupt/resume`,
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
