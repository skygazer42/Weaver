import { useState, useRef, useCallback } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment, ProcessEvent, RunMetrics, MessageSource } from '@/types/chat'
import { getApiBaseUrl } from '@/lib/api'
import { createLegacyChatStreamState, consumeLegacyChatStreamChunk, consumeSseChatStreamChunk } from '@/lib/chatStreamProtocol'
import { StorageService } from '@/lib/storage-service'

interface UseChatStreamProps {
  selectedModel: string
  searchMode: string
}

interface ResearchConnection {
  sessionId: string
  researchId: string
}

function cancelThread(threadId: string) {
  return fetch(getApiBaseUrl() + '/api/chat/cancel/' + encodeURIComponent(threadId), { method: 'POST' })
}

export function cancelResearch(researchId: string) {
  return fetch(getApiBaseUrl() + '/api/chat/sse/' + encodeURIComponent(researchId), { method: 'DELETE' })
}

export function useChatStream({ selectedModel, searchMode }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [pendingInterrupt, setPendingInterrupt] = useState<any>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [isResearchSnapshot, setIsResearchSnapshot] = useState(false)
  
  const abortControllerRef = useRef<AbortController | null>(null)
  const observingResearchRef = useRef(false)
  const researchConnectedRef = useRef(false)
  const stopWhenConnectedRef = useRef(false)
  const researchRef = useRef<ResearchConnection | null>(null)

  const detachChat = useCallback(() => {
    const controller = abortControllerRef.current
    if (!observingResearchRef.current && controller && threadId) {
      void cancelThread(threadId).catch((error) => console.error('Failed to stop chat', error))
    }
    abortControllerRef.current = null
    observingResearchRef.current = false
    researchRef.current = null
    setIsResearchSnapshot(false)
    controller?.abort()
    setIsLoading(false)
  }, [threadId])

  const handleStop = useCallback(async () => {
    const controller = abortControllerRef.current
    const isResearch = observingResearchRef.current
    if (isResearch && !researchConnectedRef.current) {
      stopWhenConnectedRef.current = true
      setCurrentStatus('Stopping Deep Research…')
      return
    }
    // 优先通知后端取消当前线程
    if (threadId) {
      try {
        const response = await cancelThread(threadId)
        if (!response.ok) throw new Error('Cancellation failed')
        if (abortControllerRef.current !== controller) return
        if (isResearch) {
          setCurrentStatus('Stopping Deep Research…')
          return
        }
        setCurrentStatus('已发送取消请求...')
      } catch (err) {
        console.error('取消请求失败', err)
        if (isResearch) {
          if (abortControllerRef.current === controller) setCurrentStatus('Could not stop Deep Research. Try again.')
          return
        }
      }
    }
    // 同时中断前端的 SSE
    if (abortControllerRef.current !== controller) return
    controller?.abort()
    abortControllerRef.current = null
    setIsLoading(false)
    setCurrentStatus('已取消')
    setTimeout(() => setCurrentStatus(''), 3000)
  }, [threadId])

  const readChat = useCallback(async (
    path: string,
    init: RequestInit,
    messageHistory: Message[],
    research?: ResearchConnection,
  ) => {
    const controller = new AbortController()
    abortControllerRef.current?.abort()
    abortControllerRef.current = controller
    observingResearchRef.current = !!research
    researchRef.current = research ?? null
    setIsResearchSnapshot(!!research)
    researchConnectedRef.current = false
    stopWhenConnectedRef.current = false
    setThreadId(null)
    const reconnecting = !!research && init.method !== 'POST'
    setCurrentStatus(reconnecting ? 'Reconnecting to Deep Research…' : '')
    setIsLoading(true)
    const researchId = research?.researchId

    try {
      const url = getApiBaseUrl() + path
      const request = { ...init, signal: controller.signal }
      let response = await fetch(url, request)
      if (reconnecting && response.status === 404) {
        // A reload can reconnect while the original request is reaching the server.
        await new Promise((resolve) => setTimeout(resolve, 500))
        if (controller.signal.aborted) return
        response = await fetch(url, request)
      }
      if (controller.signal.aborted) return

      if (!response.ok) {
        if (research && (reconnecting ? [403, 404].includes(response.status) : response.status < 500 || response.status === 503)) {
          if (StorageService.getResearchId(research.sessionId) === researchId) {
            StorageService.setResearchId(research.sessionId, null)
          }
          setThreadId(null)
          setCurrentStatus(reconnecting ? 'This research run is no longer available.' : 'Could not start Deep Research. Try again.')
          return
        }
        throw new Error('Failed to get response')
      }

      const threadHeader = response.headers.get('X-Thread-ID')
      if (threadHeader) {
        setThreadId(threadHeader)
      }
      researchConnectedRef.current = !!research
      if (researchId && stopWhenConnectedRef.current) {
        void cancelResearch(researchId).then((result) => {
          if (!result.ok) throw new Error('Cancellation failed')
        }).catch(() => {
          if (!controller.signal.aborted) setCurrentStatus('Could not stop Deep Research. Try again.')
        })
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No reader available')
      }

      let assistantMessage: Message = {
        id: 'assistant-' + (researchId || Date.now()),
        role: 'assistant',
        content: '',
        toolInvocations: [],
        processEvents: [],
        createdAt: Date.now(),
        isStreaming: true,
      }

      // Stream-level progress helpers (kept local to this request).
      let searchCount = 0
      let lastAutoStatus = ''
      let lastAutoStatusAt = 0

      const setAutoStatus = (text: string) => {
        const next = String(text || '').trim()
        if (!next) return
        const now = Date.now()
        if (next === lastAutoStatus) return
        // Avoid flickery status spam during fast multi-search fanout.
        if (now - lastAutoStatusAt < 250) return
        lastAutoStatus = next
        lastAutoStatusAt = now
        setCurrentStatus(next)
      }

      console.log('[useChatStream] Creating assistant message:', {
        id: assistantMessage.id,
        role: assistantMessage.role,
        currentMessagesCount: messageHistory.length
      })

      const baseMessages = messageHistory.filter((message) => message.id !== assistantMessage.id)
      setMessages([...baseMessages, assistantMessage])

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

      const streamState = createLegacyChatStreamState()
      const consumeChunk = research ? consumeSseChatStreamChunk : consumeLegacyChatStreamChunk
      let interrupted = false
      let terminal = false
      while (true) {
        const { done, value } = await reader.read()
        if (controller.signal.aborted) return
        const chunk = done ? decoder.decode() : decoder.decode(value, { stream: true })
        const events = consumeChunk(streamState, chunk, { flush: done })

        for (const data of events) {
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
            terminal = true
            setPendingInterrupt(data.data)
            const msg = data.data?.message || data.data?.prompts?.[0]?.message
            setCurrentStatus(msg || 'Approval required before continuing')
            assistantMessage.isStreaming = false
            assistantMessage.completedAt = Date.now()
            pushProcessEvent('interrupt', data.data)
            syncAssistantMessage()
            if (research) {
              assistantMessage.content ||= msg || 'Approval required before running a tool.'
              syncAssistantMessage()
            } else setMessages((prev) => [
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
          } else if (data.type === 'search') {
            searchCount += 1
            const query = String(data.data?.query || '').trim()
            const mode = String(data.data?.mode || '').trim().toLowerCase()
            const epoch = data.data?.epoch

            if (query) {
              if (mode === 'tree') {
                setAutoStatus(`深度调研（树）：第 ${searchCount} 次检索 · ${query}`)
              } else if (typeof epoch === 'number') {
                setAutoStatus(`深度调研：第 ${epoch} 轮检索（${searchCount}）· ${query}`)
              } else {
                setAutoStatus(`检索中（${searchCount}）· ${query}`)
              }
            }

            pushProcessEvent('search', data.data)
            syncAssistantMessage()
          } else if (data.type === 'research_node_start') {
            const nodeId = String(data.data?.node_id || data.data?.nodeId || '').trim()
            const epoch = data.data?.epoch
            if (nodeId.includes('deepsearch')) {
              if (typeof epoch === 'number') {
                setAutoStatus(`深度调研：开始第 ${epoch} 轮…`)
              } else {
                setAutoStatus('深度调研：开始调研…')
              }
            } else if (nodeId) {
              setAutoStatus(`研究节点开始：${nodeId}`)
            }
            pushProcessEvent('research_node_start', data.data)
            syncAssistantMessage()
          } else if (data.type === 'research_node_complete') {
            const nodeId = String(data.data?.node_id || data.data?.nodeId || '').trim()
            const epoch = data.data?.epoch
            if (nodeId.includes('deepsearch')) {
              if (typeof epoch === 'number') {
                setAutoStatus(`深度调研：完成第 ${epoch} 轮，继续…`)
              } else if (nodeId.includes('tree')) {
                setAutoStatus('深度调研：树调研完成，准备生成报告…')
              } else {
                setAutoStatus('深度调研：本轮完成，继续…')
              }
            }
            pushProcessEvent('research_node_complete', data.data)
            syncAssistantMessage()
          } else if (data.type === 'quality_update') {
            const score =
              typeof data.data?.query_coverage_score === 'number'
                ? data.data.query_coverage_score
                : typeof data.data?.citation_coverage_score === 'number'
                  ? data.data.citation_coverage_score
                  : undefined
            if (typeof score === 'number' && score >= 0) {
              const pct = Math.max(0, Math.min(1, score)) * 100
              setAutoStatus(`质量评估：覆盖度 ${pct.toFixed(0)}%`)
            }
            pushProcessEvent('quality_update', data.data)
            syncAssistantMessage()
          } else if (data.type === 'research_tree_update') {
            pushProcessEvent('research_tree_update', data.data)
            syncAssistantMessage()
          } else if (
            [
              'thinking',
              'tool_start',
              'tool_result',
              'tool_error',
              'screenshot',
              'task_update',
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
            terminal = true
            const metrics = (data.data?.metrics || {}) as RunMetrics
            assistantMessage.metrics = metrics
            assistantMessage.isStreaming = false
            if (!assistantMessage.completedAt) assistantMessage.completedAt = Date.now()
            pushProcessEvent('done', data.data)
            syncAssistantMessage()
          } else if (data.type === 'cancelled') {
            terminal = true
            const msg = data.data?.message || 'Task was cancelled'
            assistantMessage.content = assistantMessage.content || msg
            assistantMessage.isStreaming = false
            assistantMessage.completedAt = Date.now()
            pushProcessEvent('cancelled', data.data)
            syncAssistantMessage()
          } else if (data.type === 'error') {
            terminal = true
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
        }

        if (done || interrupted) break
      }

      if (assistantMessage.isStreaming) {
        assistantMessage.isStreaming = false
        if (!assistantMessage.completedAt) assistantMessage.completedAt = Date.now()
        syncAssistantMessage()
      }
      if (research && StorageService.getResearchId(research.sessionId) === researchId) {
        if (!terminal) {
          setCurrentStatus('Research connection lost. Reopen this chat to reconnect.')
          return
        }
        const saved = StorageService.saveSessionMessages(research.sessionId, [...baseMessages, assistantMessage])
        if (saved && !interrupted) StorageService.setResearchId(research.sessionId, null)
        if (!saved) {
          setCurrentStatus('Could not save the research report to this browser. Reopen the chat to retrieve it.')
          return
        }
      }
      setCurrentStatus('')
    } catch (error: any) {
      if (controller.signal.aborted) return
      if (research) {
        setCurrentStatus('Research connection lost. Reopen this chat to reconnect.')
      } else if (error.name === 'AbortError') {
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
      if (abortControllerRef.current === controller) {
        setIsLoading(false)
        abortControllerRef.current = null
        observingResearchRef.current = false
      }
    }
  }, [])

  const processChat = useCallback((messageHistory: Message[], images?: ImageAttachment[], sessionId?: string) => {
    let research: ResearchConnection | undefined
    let path = '/api/chat'
    if (sessionId && ['deep', 'ultra'].includes(searchMode)) {
      const key = Array.from(crypto.getRandomValues(new Uint32Array(4)), (word) =>
        word.toString(16).padStart(8, '0')
      ).join('')
      research = { sessionId, researchId: key }
      StorageService.setResearchId(sessionId, key)
      path = '/api/chat/sse?research_id=' + key
    }
    return readChat(
      path,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: messageHistory.map(({ role, content }) => ({ role, content })),
          stream: true,
          model: selectedModel,
          search_mode: searchMode,
          images: (images || []).map(({ name, mime, data }) => ({ name, mime, data })),
        }),
      },
      messageHistory,
      research,
    )
  }, [readChat, selectedModel, searchMode])

  const resumeResearch = useCallback((sessionId: string, researchId: string, messageHistory: Message[]) => {
    return readChat('/api/chat/sse/' + encodeURIComponent(researchId), {}, messageHistory, { sessionId, researchId })
  }, [readChat])

  const handleApproveInterrupt = useCallback(async () => {
    if (!pendingInterrupt || !threadId) return
    setIsLoading(true)
    setCurrentStatus('Resuming after approval...')
    const research = researchRef.current
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
      const reply: Message = {
        id: 'assistant-' + Date.now(),
        role: 'assistant',
        content: data.content || 'Resumed and completed.',
      }
      if (research) {
        if (StorageService.getResearchId(research.sessionId) === research.researchId) {
          const updated = [...messages, reply]
          StorageService.saveSessionMessages(research.sessionId, updated)
          StorageService.setResearchId(research.sessionId, null)
        }
        if (researchRef.current !== research) return
      }
      setMessages(prev => [...prev, reply])
    } catch (err) {
      if (research && researchRef.current !== research) return
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
      if (!research || researchRef.current === research) {
        setPendingInterrupt(null)
        setIsLoading(false)
        setCurrentStatus('')
      }
    }
  }, [pendingInterrupt, threadId, selectedModel, searchMode, messages])

  return {
    messages,
    setMessages,
    isLoading,
    isResearchSnapshot,
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
    resumeResearch,
    detachChat,
    handleStop,
    handleApproveInterrupt
  }
}
