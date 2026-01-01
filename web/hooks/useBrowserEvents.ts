import { useState, useEffect, useRef, useCallback } from 'react'
import { BrowserScreenshot, BrowserEvent } from '@/types/browser'
import { getApiBaseUrl } from '@/lib/api'

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
  currentProgress: number | null
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
  const [currentProgress, setCurrentProgress] = useState<number | null>(null)

  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const lastSeqRef = useRef<number>(0)
  const seenEventIdsRef = useRef<Set<string>>(new Set())

  const clearScreenshots = useCallback(() => {
    setScreenshots([])
    setIsActive(false)
    setCurrentAction(null)
    setCurrentProgress(null)
    lastSeqRef.current = 0
    seenEventIdsRef.current.clear()
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

    const apiUrl = getApiBaseUrl()
    const baseEventUrl = `${apiUrl}/api/events/${threadId}`

    const isBrowserRelatedTool = (tool?: string | null) => {
      if (!tool) return false
      return (
        tool.startsWith('sb_browser') ||
        tool.startsWith('browser_') ||
        tool === 'browser_use' ||
        tool === 'sandbox_web_search' ||
        tool.startsWith('sandbox_search') ||
        tool.startsWith('sandbox_extract_search')
      )
    }

    const connect = () => {
      const cursor = lastSeqRef.current
      const eventUrl = cursor > 0 ? `${baseEventUrl}?last_event_id=${encodeURIComponent(String(cursor))}` : baseEventUrl

      console.log('[useBrowserEvents] Connecting to:', eventUrl)

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
          const seqFromJson = typeof data.seq === 'number' ? data.seq : 0
          const seqFromEvent = event.lastEventId ? Number(event.lastEventId) : 0
          const seq = seqFromJson || seqFromEvent || 0

          // De-dupe buffered events on reconnect.
          if (seq > 0) {
            if (seq <= lastSeqRef.current) return
            lastSeqRef.current = seq
          } else if (data.event_id) {
            if (seenEventIdsRef.current.has(data.event_id)) return
            seenEventIdsRef.current.add(data.event_id)
            if (seenEventIdsRef.current.size > 2000) {
              // Safety valve: bound memory usage.
              seenEventIdsRef.current.clear()
            }
          }

          const looksLikeImageUrl = (u: string) => {
            if (u.startsWith('data:image/')) return true
            if (u.includes('/api/screenshots/')) return true
            return /\.(png|jpg|jpeg|gif|webp)(\?|#|$)/i.test(u)
          }

          // Handle screenshot events
          if (data.type === 'tool_screenshot') {
            const eventData = data.data

            // Construct image URL - prefer URL, fallback to base64
            let imageUrl = eventData.url
            if (imageUrl && !looksLikeImageUrl(imageUrl) && eventData.image) {
              // Backwards-compat: some tools historically used `url` as page URL.
              imageUrl = undefined
            }
            if (!imageUrl && eventData.image) {
              const mimeType = eventData.mime_type
                || (eventData.filename?.toLowerCase().endsWith('.jpg') || eventData.filename?.toLowerCase().endsWith('.jpeg')
                  ? 'image/jpeg'
                  : 'image/png')
              imageUrl = `data:${mimeType};base64,${eventData.image}`
            }
            // If backend returns a relative URL, prefix with API base
            if (imageUrl && imageUrl.startsWith('/')) {
              const base = getApiBaseUrl()
              if (base) {
                imageUrl = `${base}${imageUrl}`
              }
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
            }
          }

          // Handle tool start events
          else if (data.type === 'tool_start') {
            const eventData = data.data
            if (isBrowserRelatedTool(eventData.tool)) {
              setIsActive(true)
              setCurrentAction(eventData.action || eventData.tool || null)
              setCurrentProgress(null)
            }
          }

          // Handle tool progress events
          else if (data.type === 'tool_progress') {
            const eventData = data.data
            if (isBrowserRelatedTool(eventData.tool)) {
              setIsActive(true)
              const msg = eventData.message || eventData.info || eventData.action || null
              setCurrentAction(msg)
              setCurrentProgress(typeof eventData.progress === 'number' ? eventData.progress : null)
            }
          }

          // Handle tool result events
          else if (data.type === 'tool_result') {
            const eventData = data.data
            if (isBrowserRelatedTool(eventData.tool)) {
              setIsActive(false)
              setCurrentAction(null)
              setCurrentProgress(null)
            }
          }

          // Handle tool error events
          else if (data.type === 'tool_error') {
            const eventData = data.data
            if (isBrowserRelatedTool(eventData.tool)) {
              setCurrentAction(eventData.error || 'Tool error')
              setCurrentProgress(null)
              // Keep isActive true briefly so UI can render the error state.
              setIsActive(true)
              setTimeout(() => setIsActive(false), 1500)
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
      setCurrentProgress(null)
      lastSeqRef.current = 0
      seenEventIdsRef.current.clear()
    }
  }, [threadId])

  const latestScreenshot = screenshots.length > 0 ? screenshots[screenshots.length - 1] : null

  return {
    screenshots,
    latestScreenshot,
    isActive,
    currentAction,
    currentProgress,
    clearScreenshots
  }
}
