import { useState, useEffect, useRef, useCallback } from 'react'
import { getApiWsBaseUrl } from '@/lib/api'

interface UseBrowserStreamProps {
  threadId: string | null
  autoStart?: boolean
  quality?: number
  maxFps?: number
}

interface StreamFrame {
  data: string  // base64 encoded image
  timestamp: number
  metadata?: Record<string, any>
}

interface UseBrowserStreamReturn {
  isConnected: boolean
  isStreaming: boolean
  isStarting: boolean
  currentFrame: StreamFrame | null
  fps: number
  error: string | null
  start: () => void
  stop: () => void
  capture: () => void
  sendAction: (payload: Record<string, any>) => void
}

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
  const [isStarting, setIsStarting] = useState(false)
  const [currentFrame, setCurrentFrame] = useState<StreamFrame | null>(null)
  const [fps, setFps] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const frameCountRef = useRef(0)
  const fpsIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const readWsMessage = useCallback(async (raw: unknown): Promise<string | null> => {
    if (typeof raw === 'string') return raw
    if (raw instanceof Blob) return await raw.text()
    if (raw instanceof ArrayBuffer) return new TextDecoder().decode(raw)
    if (ArrayBuffer.isView(raw)) return new TextDecoder().decode(raw.buffer)
    return null
  }, [])

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

  const connect = useCallback(() => {
    if (!threadId) return

    // Clean up existing connection
    if (wsRef.current) {
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
        setIsStarting(true)
        ws.send(JSON.stringify({
          action: 'start',
          quality,
          max_fps: maxFps
        }))
      }
    }

    ws.onmessage = async (event) => {
      try {
        const raw = await readWsMessage(event.data)
        if (!raw) return
        const data = JSON.parse(raw)

        if (data.type === 'frame') {
          frameCountRef.current++
          setCurrentFrame({
            data: data.data,
            timestamp: data.timestamp,
            metadata: data.metadata
          })
          setIsStarting(false)
        } else if (data.type === 'status') {
          console.log('[useBrowserStream] Status:', data.message)
          if (data.message === 'Screencast started') {
            setIsStarting(false)
            setIsStreaming(true)
          } else if (data.message === 'Screencast stopped') {
            setIsStarting(false)
            setIsStreaming(false)
          } else if (data.message === 'Screencast already running') {
            setIsStarting(false)
            setIsStreaming(true)
          }
        } else if (data.type === 'error') {
          console.error('[useBrowserStream] Error:', data.message)
          setError(data.message)
          setIsStarting(false)
        } else if (data.type === 'ping') {
          // keepalive - ignore
        }
      } catch (err) {
        console.error('[useBrowserStream] Failed to parse message:', err)
      }
    }

    ws.onerror = (event) => {
      console.error('[useBrowserStream] WebSocket error:', event)
      setError('WebSocket connection error')
      setIsStarting(false)
    }

    ws.onclose = (event) => {
      console.log('[useBrowserStream] Disconnected:', event.code, event.reason)
      setIsConnected(false)
      setIsStreaming(false)
      setIsStarting(false)
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
    if (threadId) {
      connect()
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted')
        wsRef.current = null
      }
    }
  }, [threadId, connect])

  const start = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setIsStarting(true)
      wsRef.current.send(JSON.stringify({
        action: 'start',
        quality,
        max_fps: maxFps
      }))
    }
  }, [quality, maxFps])

  const stop = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setIsStarting(false)
      wsRef.current.send(JSON.stringify({ action: 'stop' }))
    }
  }, [])

  const capture = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'capture' }))
    }
  }, [])

  return {
    isConnected,
    isStreaming,
    isStarting,
    currentFrame,
    fps,
    error,
    start,
    stop,
    capture,
    sendAction: (payload: Record<string, any>) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(payload))
      }
    }
  }
}
