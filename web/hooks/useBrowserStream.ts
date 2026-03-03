import { useState, useEffect, useRef, useCallback } from 'react'
import { getApiWsBaseUrl } from '@/lib/api'
import type { WsAckMessage } from '@/lib/browser/wsAckTracker'
import { WsAckTracker } from '@/lib/browser/wsAckTracker'

interface UseBrowserStreamProps {
  threadId: string | null
  autoStart?: boolean
  quality?: number
  maxFps?: number
}

interface StreamFrame {
  data: string  // base64 encoded image
  timestamp: number
  source?: string
  metadata?: Record<string, any>
}

interface UseBrowserStreamReturn {
  isConnected: boolean
  isStreaming: boolean
  currentFrame: StreamFrame | null
  fps: number
  error: string | null
  lastAck: WsAckMessage | null
  start: () => void
  stop: () => void
  capture: () => void
  sendInputAction: (action: BrowserWsInputAction) => Promise<WsAckMessage>
}

type BrowserWsMouseButton = 'left' | 'right' | 'middle'

type BrowserWsMouseAction =
  | {
      action: 'mouse'
      type: 'click'
      x: number
      y: number
      button?: BrowserWsMouseButton
      clicks?: number
      id?: string
    }
  | {
      action: 'mouse'
      type: 'move'
      x: number
      y: number
      id?: string
    }
  | {
      action: 'mouse'
      type: 'down' | 'up'
      button?: BrowserWsMouseButton
      id?: string
    }

type BrowserWsScrollAction = {
  action: 'scroll'
  dx: number
  dy: number
  id?: string
}

type BrowserWsKeyboardAction =
  | {
      action: 'keyboard'
      type: 'press'
      key: string
      id?: string
    }
  | {
      action: 'keyboard'
      type: 'type'
      text: string
      id?: string
    }

type BrowserWsNavigateAction = {
  action: 'navigate'
  url: string
  id?: string
}

export type BrowserWsInputAction =
  | BrowserWsMouseAction
  | BrowserWsScrollAction
  | BrowserWsKeyboardAction
  | BrowserWsNavigateAction

/**
 * Hook for WebSocket-based real-time browser streaming.
 * Uses CDP Page.startScreencast for smooth frame updates.
 */
export function useBrowserStream({
  threadId,
  autoStart = false,
  quality = 70,
  maxFps = 5
}: UseBrowserStreamProps): UseBrowserStreamReturn {
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentFrame, setCurrentFrame] = useState<StreamFrame | null>(null)
  const [fps, setFps] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [lastAck, setLastAck] = useState<WsAckMessage | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const ackTrackerRef = useRef(new WsAckTracker())
  const actionSeqRef = useRef(0)
  const frameCountRef = useRef(0)
  const fpsIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Calculate FPS every second
  useEffect(() => {
    fpsIntervalRef.current = setInterval(() => {
      setFps(frameCountRef.current)
      frameCountRef.current = 0
    }, 1000)

    return () => {
      if (fpsIntervalRef.current) {
        clearInterval(fpsIntervalRef.current)
      }
    }
  }, [])

  const connect = useCallback(function connect() {
    if (!threadId) return

    // Clean up existing connection
    if (wsRef.current) {
      ackTrackerRef.current.rejectAll(new Error('WebSocket replaced'))
      wsRef.current.close()
    }

    const wsUrl = getApiWsBaseUrl() + `/api/browser/${threadId}/stream`

    console.log('[useBrowserStream] Connecting to:', wsUrl)

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[useBrowserStream] Connected')
      setIsConnected(true)
      setError(null)

      // Auto-start streaming if enabled
      if (autoStart) {
        ws.send(JSON.stringify({
          action: 'start',
          quality,
          max_fps: maxFps
        }))
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'frame') {
          frameCountRef.current++
          setCurrentFrame({
            data: data.data,
            timestamp: data.timestamp,
            source: typeof data.source === 'string' ? data.source : undefined,
            metadata: data.metadata
          })
        } else if (data.type === 'ack') {
          setLastAck(data as WsAckMessage)
          ackTrackerRef.current.resolve(data as WsAckMessage)
        } else if (data.type === 'status') {
          console.log('[useBrowserStream] Status:', data.message)
          if (data.message === 'Screencast started') {
            setIsStreaming(true)
          } else if (data.message === 'Screencast stopped') {
            setIsStreaming(false)
          }
        } else if (data.type === 'ping') {
          // Keepalive from server (safe to ignore).
        } else if (data.type === 'error') {
          console.error('[useBrowserStream] Error:', data.message)
          setError(data.message)
        }
      } catch (err) {
        console.error('[useBrowserStream] Failed to parse message:', err)
      }
    }

    ws.onerror = (event) => {
      console.error('[useBrowserStream] WebSocket error:', event)
      setError('WebSocket connection error')
    }

    ws.onclose = (event) => {
      console.log('[useBrowserStream] Disconnected:', event.code, event.reason)
      setIsConnected(false)
      setIsStreaming(false)
      ackTrackerRef.current.rejectAll(new Error('WebSocket disconnected'))
      wsRef.current = null

      // Attempt to reconnect after 3 seconds if not intentionally closed
      if (event.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(() => {
          if (threadId) {
            console.log('[useBrowserStream] Attempting to reconnect...')
            connect()
          }
        }, 3000)
      }
    }
  }, [threadId, autoStart, quality, maxFps])

  // Connect when threadId changes
  useEffect(() => {
    const ackTracker = ackTrackerRef.current

    if (threadId) {
      connect()
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        ackTracker.rejectAll(new Error('WebSocket closed'))
        wsRef.current.close(1000, 'Component unmounted')
        wsRef.current = null
      }
    }
  }, [threadId, connect])

  const start = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'start',
        quality,
        max_fps: maxFps
      }))
    }
  }, [quality, maxFps])

  const stop = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }))
    }
  }, [])

  const capture = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'capture' }))
    }
  }, [])

  const sendInputAction = useCallback(async (action: BrowserWsInputAction) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error('Browser stream is not connected')
    }

    const existingId = typeof (action as any)?.id === 'string' ? String((action as any).id).trim() : ''
    const id = existingId || `ui_${Date.now().toString(36)}_${++actionSeqRef.current}`

    const ackPromise = ackTrackerRef.current.waitFor(id)
    ws.send(JSON.stringify({ ...action, id }))
    return await ackPromise
  }, [])

  return {
    isConnected,
    isStreaming,
    currentFrame,
    fps,
    error,
    lastAck,
    start,
    stop,
    capture,
    sendInputAction,
  }
}
