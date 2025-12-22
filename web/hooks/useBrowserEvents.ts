import { useState, useEffect, useRef, useCallback } from 'react'
import { BrowserScreenshot, BrowserEvent } from '@/types/browser'

interface UseBrowserEventsProps {
  threadId: string | null
  enabled?: boolean
  maxScreenshots?: number
}

interface UseBrowserEventsReturn {
  screenshots: BrowserScreenshot[]
  latestScreenshot: BrowserScreenshot | null
  isActive: boolean
  currentAction: string | null
  clearScreenshots: () => void
}

/**
 * Hook to subscribe to browser events via SSE
 * Listens to /api/events/{threadId} for real-time browser screenshots
 */
export function useBrowserEvents({
  threadId,
  enabled = true,
  maxScreenshots = 20
}: UseBrowserEventsProps): UseBrowserEventsReturn {
  const [screenshots, setScreenshots] = useState<BrowserScreenshot[]>([])
  const [isActive, setIsActive] = useState(false)
  const [currentAction, setCurrentAction] = useState<string | null>(null)

  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const clearScreenshots = useCallback(() => {
    setScreenshots([])
    setIsActive(false)
    setCurrentAction(null)
  }, [])

  useEffect(() => {
    // Cleanup function
    const cleanup = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
    }

    // Don't connect if disabled or no threadId
    if (!enabled || !threadId) {
      cleanup()
      return
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || ''
    const eventUrl = `${apiUrl}/api/events/${threadId}`

    console.log('[useBrowserEvents] Connecting to:', eventUrl)

    const connect = () => {
      const es = new EventSource(eventUrl)
      eventSourceRef.current = es

      es.onopen = () => {
        console.log('[useBrowserEvents] Connected')
      }

      es.onmessage = (event) => {
        try {
          // Handle keepalive messages
          if (event.data.trim() === '' || event.data.startsWith(':')) {
            return
          }

          const data = JSON.parse(event.data) as BrowserEvent

          // Handle screenshot events
          if (data.type === 'tool_screenshot') {
            const eventData = data.data

            // Construct image URL - prefer URL, fallback to base64
            let imageUrl = eventData.url
            if (!imageUrl && eventData.image) {
              imageUrl = `data:image/png;base64,${eventData.image}`
            }

            if (imageUrl) {
              const newScreenshot: BrowserScreenshot = {
                id: data.event_id || `ss-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                url: imageUrl,
                pageUrl: eventData.page_url,
                action: eventData.action,
                tool: eventData.tool,
                timestamp: data.timestamp ? data.timestamp * 1000 : Date.now(),
                isLive: eventData.image ? true : false
              }

              setScreenshots(prev => {
                // Keep only the last N screenshots
                const updated = [...prev, newScreenshot]
                return updated.slice(-maxScreenshots)
              })

              setIsActive(true)
              setCurrentAction(eventData.action || null)
            }
          }

          // Handle tool start events
          else if (data.type === 'tool_start') {
            const eventData = data.data
            // Check if it's a browser tool
            if (eventData.tool?.startsWith('sb_browser') || eventData.tool?.startsWith('browser_')) {
              setIsActive(true)
              setCurrentAction(eventData.action || eventData.tool || null)
            }
          }

          // Handle tool result events
          else if (data.type === 'tool_result') {
            const eventData = data.data
            if (eventData.tool?.startsWith('sb_browser') || eventData.tool?.startsWith('browser_')) {
              setCurrentAction(null)
            }
          }

        } catch (err) {
          // Ignore parse errors for keepalive or malformed messages
          if (event.data.trim() && !event.data.startsWith(':')) {
            console.warn('[useBrowserEvents] Failed to parse event:', err)
          }
        }
      }

      es.onerror = (error) => {
        console.error('[useBrowserEvents] EventSource error:', error)
        es.close()
        eventSourceRef.current = null

        // Attempt to reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          if (enabled && threadId) {
            console.log('[useBrowserEvents] Attempting to reconnect...')
            connect()
          }
        }, 3000)
      }
    }

    connect()

    return cleanup
  }, [threadId, enabled, maxScreenshots])

  // Reset when threadId changes
  useEffect(() => {
    if (!threadId) {
      setScreenshots([])
      setIsActive(false)
      setCurrentAction(null)
    }
  }, [threadId])

  const latestScreenshot = screenshots.length > 0 ? screenshots[screenshots.length - 1] : null

  return {
    screenshots,
    latestScreenshot,
    isActive,
    currentAction,
    clearScreenshots
  }
}
