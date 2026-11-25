import { useState, useRef, useCallback, useEffect } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment, ProcessEvent, RunMetrics, MessageSource, ChatRun, PendingInterrupt, RUN_STATUS_LABELS, RunStatus } from '@/types/chat'
import { getApiBaseUrl } from '@/lib/api'
import { createLegacyChatStreamState, consumeLegacyChatStreamChunk, consumeSseChatStreamChunk } from '@/lib/chatStreamProtocol'
import { StorageService } from '@/lib/storage-service'

interface UseChatStreamProps {
  selectedModel: string
  reasoningModel?: string
  searchMode: string
  workspaceId?: string
}

interface RunConnection {
  sessionId: string
  run: ChatRun
}

function cancelThread(threadId: string) {
  return fetch(getApiBaseUrl() + '/api/chat/cancel/' + encodeURIComponent(threadId), { method: 'POST' })
}

export function cancelRun(runId: string) {
  return fetch(getApiBaseUrl() + '/api/chat/sse/' + encodeURIComponent(runId), { method: 'DELETE' })
}

const isTerminalStatus = (status: RunStatus | undefined) =>
  status === 'completed' || status === 'failed' || status === 'cancelled' || status === 'insufficient_evidence'

export function useChatStream({ selectedModel, reasoningModel, searchMode, workspaceId }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterrupt | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [isRunSnapshot, setIsRunSnapshot] = useState(false)
  const [connectionLost, setConnectionLost] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [isDeciding, setIsDeciding] = useState(false)
  
  const abortControllerRef = useRef<AbortController | null>(null)
  const connectedRef = useRef(false)
  const stoppingRef = useRef(false)
  const stopWhenConnectedRef = useRef(false)
  const runRef = useRef<RunConnection | null>(null)
  const decisionRef = useRef<symbol | null>(null)

  useEffect(() => () => abortControllerRef.current?.abort(), [])

  const detachChat = useCallback(() => {
    const controller = abortControllerRef.current
    if (!runRef.current && controller && threadId) {
      void cancelThread(threadId).catch((error) => console.error('Failed to stop chat', error))
    }
    abortControllerRef.current = null
    runRef.current = null
    decisionRef.current = null
    stoppingRef.current = false
    stopWhenConnectedRef.current = false
    setIsRunSnapshot(false)
    setConnectionLost(false)
    setIsDeciding(false)
    setIsStopping(false)
    controller?.abort()
    setIsLoading(false)
  }, [threadId])

  const requestStop = useCallback(async (connection: RunConnection, beforeHeaders = false) => {
    try {
      let response = await cancelRun(connection.run.id)
      if (response.status === 404 && beforeHeaders && runRef.current === connection) {
        if (!connectedRef.current && abortControllerRef.current) {
          stopWhenConnectedRef.current = true
          return false
        }
        response = await cancelRun(connection.run.id)
      }
      if (!response.ok) throw new Error('Cancellation failed')
      return true
    } catch {
      if (runRef.current === connection) {
        stoppingRef.current = false
        setIsStopping(false)
        setCurrentStatus('Could not stop this run. Try again.')
      }
      return false
    }
  }, [])

  const readChat = useCallback(async (
    path: string,
    init: RequestInit,
    messageHistory: Message[],
    connection?: RunConnection,
  ) => {
    const controller = new AbortController()
    abortControllerRef.current?.abort()
    abortControllerRef.current = controller
    runRef.current = connection ?? null
    setIsRunSnapshot(!!connection)
    setConnectionLost(false)
    connectedRef.current = false
    setThreadId(null)
    const reconnecting = !!connection && init.method !== 'POST'
    setCurrentStatus(reconnecting && !stoppingRef.current ? 'Reconnecting…' : '')
    setIsLoading(true)
    const run = connection?.run

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
        if (connection && (reconnecting ? [403, 404].includes(response.status) : response.status < 500 || response.status === 503)) {
          if (StorageService.getRun(connection.sessionId, workspaceId)?.id === run?.id) {
            StorageService.setRun(connection.sessionId, null, workspaceId)
          }
          runRef.current = null
          stoppingRef.current = false
          stopWhenConnectedRef.current = false
          setIsStopping(false)
          setPendingInterrupt(null)
          setCurrentStatus(reconnecting ? 'This run is no longer available.' : 'Could not start this run. Try again.')
          return
        }
        throw new Error('Failed to get response')
      }

      const threadHeader = response.headers.get('X-Thread-ID')
      if (threadHeader) {
        setThreadId(threadHeader)
      }
      connectedRef.current = true
      if (connection && stopWhenConnectedRef.current) {
        stopWhenConnectedRef.current = false
        void requestStop(connection)
      }
      setCurrentStatus(stoppingRef.current ? 'Stopping…' : '')

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No reader available')
      }

      let assistantMessage: Message = {
        id: 'assistant-' + (run?.id || Date.now()),
        role: 'assistant',
        content: '',
        toolInvocations: [],
        processEvents: [],
        createdAt: Date.now(),
        ...run?.assistant,
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

      const baseMessages = messageHistory.filter((message) => message.id !== assistantMessage.id)
      setMessages([...baseMessages, { ...assistantMessage }])

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
      const consumeChunk = run ? consumeSseChatStreamChunk : consumeLegacyChatStreamChunk
      let interrupted = Boolean(run?.interrupt)
      let terminal = isTerminalStatus(assistantMessage.runStatus)
      let receivedRunStatus = Boolean(assistantMessage.runStatus)
      while (true) {
        const { done, value } = await reader.read()
        if (controller.signal.aborted) return
        const chunk = done ? decoder.decode() : decoder.decode(value, { stream: true })
        const events = consumeChunk(streamState, chunk, { flush: done })

        for (const data of events) {
          if (run && data.id !== undefined) {
            if (data.id <= (run.lastEventId ?? 0)) continue
            run.lastEventId = data.id
          }
          if (data.type === 'run_status') {
            const status = data.data?.status as RunStatus
            if (!Object.hasOwn(RUN_STATUS_LABELS, status)) continue
            receivedRunStatus = true
            terminal = isTerminalStatus(status)
            assistantMessage.runStatus = status
            if (status !== 'awaiting_approval' && interrupted) {
              interrupted = false
              if (run) delete run.interrupt
              setPendingInterrupt(null)
            }
            syncAssistantMessage()
          } else if (data.type === 'status') {
            setCurrentStatus(data.data.text)
            pushProcessEvent('status', data.data)
            syncAssistantMessage()
          } else if (data.type === 'text') {
            assistantMessage.content += data.data.content
            syncAssistantMessage()
          } else if (data.type === 'message') {
            assistantMessage.content = data.data.content
            syncAssistantMessage()
          } else if (data.type === 'interrupt') {
            interrupted = true
            if (run) run.interrupt = data.data
            setPendingInterrupt(data.data)
            assistantMessage.isStreaming = false
            if (run) assistantMessage.runStatus = 'awaiting_approval'
            pushProcessEvent('interrupt', data.data)
            syncAssistantMessage()
            if (!run) break
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
              result: data.data.result ?? data.data.summary,
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
            if (!receivedRunStatus && !interrupted) {
              terminal = true
              if (run) assistantMessage.runStatus ??= 'completed'
            }
            const metrics = (data.data?.metrics || {}) as RunMetrics
            assistantMessage.metrics = metrics
            assistantMessage.isStreaming = false
            if (!assistantMessage.completedAt) assistantMessage.completedAt = Date.now()
            pushProcessEvent('done', data.data)
            syncAssistantMessage()
          } else if (data.type === 'cancelled') {
            if (!receivedRunStatus) {
              terminal = true
              if (run) assistantMessage.runStatus = 'cancelled'
            }
            const msg = data.data?.message || 'Task was cancelled'
            assistantMessage.content = assistantMessage.content || msg
            assistantMessage.isStreaming = false
            assistantMessage.completedAt = Date.now()
            pushProcessEvent('cancelled', data.data)
            syncAssistantMessage()
          } else if (data.type === 'error') {
            if (!receivedRunStatus) {
              terminal = true
              if (run) assistantMessage.runStatus = 'failed'
            }
            const msg = data.data?.message || 'An error occurred'
            assistantMessage.content = assistantMessage.content || msg
            assistantMessage.isStreaming = false
            assistantMessage.completedAt = Date.now()
            pushProcessEvent('error', data.data)
            syncAssistantMessage()
          } else if (data.type === 'artifact') {
            const newArtifact = data.data as Artifact
            const artifacts = assistantMessage.artifacts ?? []
            if (!artifacts.some(({ id }) => id === newArtifact.id)) {
              assistantMessage.artifacts = [...artifacts, newArtifact]
              syncAssistantMessage()
            }
          }
        }

        if (run && connection && events.length > 0) {
          run.assistant = assistantMessage
          StorageService.saveRunSnapshot(connection.sessionId, run, workspaceId)
        }
        if (done || (!run && interrupted)) break
      }

      if (assistantMessage.isStreaming) {
        assistantMessage.isStreaming = false
        if (!assistantMessage.completedAt) assistantMessage.completedAt = Date.now()
        syncAssistantMessage()
      }
      if (connection && run) {
        if (terminal) {
          stoppingRef.current = false
          setIsStopping(false)
        }
        if (!terminal && !interrupted) {
          setConnectionLost(true)
          setCurrentStatus('Connection lost.')
          return
        }
        if (terminal && StorageService.getRun(connection.sessionId, workspaceId)?.id === run.id) {
          const saved = StorageService.saveSessionMessages(connection.sessionId, [...baseMessages, assistantMessage], workspaceId)
          if (saved) StorageService.setRun(connection.sessionId, null, workspaceId)
          else {
            setConnectionLost(true)
            setCurrentStatus('Could not save this reply to browser history.')
            return
          }
        }
        if (terminal) runRef.current = null
      }
      setCurrentStatus('')
    } catch (error: any) {
      if (controller.signal.aborted) return
      if (connection) {
        setConnectionLost(true)
        setCurrentStatus('Connection lost.')
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
      }
    }
  }, [requestStop, workspaceId])

  const processChat = useCallback((messageHistory: Message[], images?: ImageAttachment[], sessionId?: string, mode = searchMode) => {
    let connection: RunConnection | undefined
    let path = '/api/chat'
    if (sessionId && ['agent', 'deep_agent', 'deep', 'ultra'].includes(mode)) {
      const id = Array.from(crypto.getRandomValues(new Uint32Array(4)), (word) =>
        word.toString(16).padStart(8, '0')
      ).join('')
      const run = { id, searchMode: mode }
      connection = { sessionId, run }
      StorageService.setRun(sessionId, run, workspaceId)
      path = '/api/chat/sse?research_id=' + id
    }
    return readChat(
      path,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: messageHistory.map(({ role, content }) => ({ role, content })),
          conversation_id: sessionId,
          workspace_id: workspaceId,
          stream: true,
          model: selectedModel,
          ...(reasoningModel && { reasoning_model: reasoningModel }),
          search_mode: mode,
          images: (images || []).map(({ name, mime, data }) => ({ name, mime, data })),
        }),
      },
      messageHistory,
      connection,
    )
  }, [readChat, selectedModel, reasoningModel, searchMode, workspaceId])

  const reconnect = useCallback((connection: RunConnection, messageHistory: Message[]) => {
    const { run } = connection
    setPendingInterrupt(run.interrupt ?? null)
    const headers = run.lastEventId ? { 'Last-Event-ID': String(run.lastEventId) } : undefined
    return readChat('/api/chat/sse/' + encodeURIComponent(run.id), { headers }, messageHistory, connection)
  }, [readChat])

  const resumeRun = useCallback((sessionId: string, run: ChatRun, messageHistory: Message[]) => {
    StorageService.markRunViewed(sessionId, workspaceId)
    return reconnect({ sessionId, run }, messageHistory)
  }, [reconnect, workspaceId])

  const handleStop = useCallback(async () => {
    const controller = abortControllerRef.current
    const connection = runRef.current
    if (connection) {
      if (stoppingRef.current || decisionRef.current) return
      stoppingRef.current = true
      setIsStopping(true)
      const accepted = await requestStop(connection, !!controller && !connectedRef.current)
      if (accepted && runRef.current === connection && !abortControllerRef.current) {
        await reconnect(connection, messages)
      }
      return
    }

    if (!controller) return
    if (threadId) {
      try {
        await cancelThread(threadId)
      } catch (error) {
        console.error('Failed to stop chat', error)
      }
    }
    if (abortControllerRef.current !== controller) return
    controller.abort()
    abortControllerRef.current = null
    setIsLoading(false)
    setCurrentStatus('Cancelled')
  }, [messages, reconnect, requestStop, threadId])

  const decideInterrupt = useCallback(async (approved: boolean) => {
    if (!pendingInterrupt || !threadId || decisionRef.current || stoppingRef.current) return
    const decision = Symbol()
    decisionRef.current = decision
    setIsDeciding(true)
    setIsLoading(true)
    setCurrentStatus('Submitting decision…')
    const connection = runRef.current
    try {
      const prompts = pendingInterrupt.prompts ?? [pendingInterrupt]
      const toolCalls = prompts.flatMap((prompt) => prompt.tool_calls ?? prompt.action_requests ?? [])
      const res = await fetch(
        `${getApiBaseUrl()}/api/interrupt/resume`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            thread_id: threadId,
            payload: {
              tool_approved: approved,
              tool_calls: toolCalls,
              interrupt_ids: pendingInterrupt.interrupt_ids,
            },
            model: selectedModel,
            ...(reasoningModel && { reasoning_model: reasoningModel }),
            search_mode: connection?.run.searchMode ?? searchMode
          })
        }
      )
      if (!res.ok && !(res.status === 409 && connection)) throw new Error('Failed to resume')
      if (decisionRef.current !== decision) return
      if (connection) {
        delete connection.run.interrupt
        StorageService.saveRunSnapshot(connection.sessionId, connection.run, workspaceId)
        decisionRef.current = null
        setIsDeciding(false)
        await reconnect(connection, messages)
        return
      }
      const data = await res.json()
      if (decisionRef.current !== decision) return
      if (data.status === 'interrupted') {
        setPendingInterrupt({ prompts: data.interrupts })
        setCurrentStatus('')
        return
      }
      const reply: Message = {
        id: 'assistant-' + Date.now(),
        role: 'assistant',
        content: data.content || 'Resumed and completed.',
      }
      setMessages(prev => [...prev, reply])
      setPendingInterrupt(null)
      setCurrentStatus('')
    } catch (err) {
      if (decisionRef.current !== decision) return
      console.error('Failed to resume interrupt', err)
      setCurrentStatus('Could not submit this decision. Try again.')
    } finally {
      if (decisionRef.current === decision) {
        decisionRef.current = null
        setIsDeciding(false)
        setIsLoading(false)
      }
    }
  }, [pendingInterrupt, threadId, selectedModel, reasoningModel, searchMode, messages, reconnect, workspaceId])

  return {
    messages,
    setMessages,
    isLoading,
    isRunSnapshot,
    connectionLost,
    isDeciding,
    isStopping,
    currentStatus,
    setCurrentStatus,
    pendingInterrupt,
    setPendingInterrupt,
    threadId,
    setThreadId,
    processChat,
    resumeRun,
    detachChat,
    handleStop,
    decideInterrupt,
  }
}
