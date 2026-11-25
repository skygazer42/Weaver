'use client'

import React, { useRef, useState, useCallback, useEffect } from 'react'
import {
  Loader2,
  Globe,
  X,
  Maximize2,
  Minimize2,
  ExternalLink,
  Play,
  Pause,
  Camera,
  Images,
  GripVertical,
  CornerDownLeft
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { BrowserScreenshot } from '@/types/browser'
import { useBrowserEvents } from '@/hooks/useBrowserEvents'
import { useBrowserStream } from '@/hooks/useBrowserStream'

interface BrowserViewerProps {
  threadId: string | null
  className?: string
  onClose?: () => void
  defaultExpanded?: boolean
  mode?: 'events' | 'stream'  // 'events' = SSE screenshots, 'stream' = WebSocket live
  alwaysShow?: boolean  // Always show the viewer, even without screenshots
  draggable?: boolean
  onDragHandlePointerDown?: (e: React.PointerEvent) => void
  onDragHandleDoubleClick?: () => void
  isDragging?: boolean
}

/**
 * Real-time browser viewer component
 * Displays browser screenshots as they're captured during agent operations
 */
export function BrowserViewer({
  threadId,
  className,
  onClose,
  defaultExpanded = true,
  mode = 'events',
  alwaysShow = false,
  draggable = false,
  onDragHandlePointerDown,
  onDragHandleDoubleClick,
  isDragging = false
}: BrowserViewerProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [selectedScreenshot, setSelectedScreenshot] = useState<BrowserScreenshot | null>(null)
  const [viewerMode, setViewerMode] = useState<'events' | 'stream'>(mode)
  const [isInteracting, setIsInteracting] = useState(false)
  const [urlDraft, setUrlDraft] = useState('')
  const [isEditingUrl, setIsEditingUrl] = useState(false)
  const [interactionContext, setInteractionContext] = useState({ threadId, viewerMode })
  const isLiveMode = viewerMode === 'stream'
  const liveViewportRef = useRef<HTMLDivElement | null>(null)
  const liveImageRef = useRef<HTMLImageElement | null>(null)

  // SSE-based screenshot events
  const {
    screenshots,
    latestScreenshot,
    isActive: isEventsActive,
    currentAction,
    currentProgress,
    clearScreenshots
  } = useBrowserEvents({
    threadId,
    enabled: viewerMode === 'events',
    maxScreenshots: 100
  })

  // WebSocket-based live streaming
  const {
    isConnected,
    isStreaming,
    isStarting,
    currentFrame,
    fps,
    updatesFps,
    error: streamError,
    start: startStream,
    stop: stopStream,
    capture: captureFrame,
    sendAction
  } = useBrowserStream({
    threadId: isLiveMode ? threadId : null,
    autoStart: true,
    quality: 55,
    maxFps: 12
  })

  const pendingWheelRef = useRef({ dx: 0, dy: 0 })
  const wheelTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (wheelTimerRef.current) {
        clearTimeout(wheelTimerRef.current)
        wheelTimerRef.current = null
      }
    }
  }, [])

  const isActive = isLiveMode ? (isStreaming || isStarting) : isEventsActive

  if (interactionContext.threadId !== threadId || interactionContext.viewerMode !== viewerMode) {
    setInteractionContext({ threadId, viewerMode })
    setIsInteracting(false)
    setIsEditingUrl(false)
  }

  const handleClose = useCallback(() => {
    if (isLiveMode) {
      stopStream()
    }
    clearScreenshots()
    onClose?.()
  }, [isLiveMode, stopStream, clearScreenshots, onClose])

  const toggleExpand = useCallback(() => {
    setIsExpanded(prev => !prev)
  }, [])

  const toggleMode = useCallback(() => {
    setViewerMode(prev => (prev === 'events' ? 'stream' : 'events'))
  }, [])

  // Determine what to display
  const displayScreenshot = selectedScreenshot || latestScreenshot
  const liveImageUrl = currentFrame ? `data:image/jpeg;base64,${currentFrame.data}` : null
  const liveMetaUrlRaw = (currentFrame?.metadata?.url || currentFrame?.metadata?.page_url || '') as string
  const liveMetaTitleRaw = (currentFrame?.metadata?.title || '') as string
  const liveMetaUrl = typeof liveMetaUrlRaw === 'string' ? liveMetaUrlRaw : ''
  const liveMetaTitle = typeof liveMetaTitleRaw === 'string' ? liveMetaTitleRaw : ''

  const addressUrl = isLiveMode ? liveMetaUrl : (displayScreenshot?.pageUrl || '')
  const addressLabel = addressUrl || (isLiveMode ? 'Live Browser' : 'Browser')
  const canOpenAddressUrl = addressUrl.startsWith('http://') || addressUrl.startsWith('https://')
  const isBlankLivePage =
    isLiveMode &&
    Boolean(liveImageUrl) &&
    (!liveMetaUrl ||
      liveMetaUrl === 'about:blank' ||
      liveMetaUrl.startsWith('about:blank') ||
      liveMetaUrl.startsWith('chrome://') ||
      liveMetaUrl.startsWith('edge://'))

  const displayedUrl = isEditingUrl ? urlDraft : (canOpenAddressUrl ? addressUrl : '')

  const sendNavigate = useCallback(
    (url: string) => {
      let target = (url || '').trim()
      if (!target) return
      if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(target)) {
        target = `https://${target}`
      }
      sendAction({ action: 'navigate', url: target })
    },
    [sendAction]
  )

  const normalizePoint = useCallback((clientX: number, clientY: number) => {
    const img = liveImageRef.current
    if (!img) return null
    const rect = img.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    const x = (clientX - rect.left) / rect.width
    const y = (clientY - rect.top) / rect.height
    const xClamped = Math.max(0, Math.min(1, x))
    const yClamped = Math.max(0, Math.min(1, y))
    return { x: xClamped, y: yClamped }
  }, [])

  const handleLiveClick = useCallback(
    (e: React.MouseEvent) => {
      if (!isLiveMode || !isConnected) return
      const pt = normalizePoint(e.clientX, e.clientY)
      if (!pt) return
      setIsInteracting(true)
      liveViewportRef.current?.focus()
      sendAction({ action: 'mouse', type: 'click', x: pt.x, y: pt.y, button: 'left', clicks: 1 })
    },
    [isLiveMode, isConnected, normalizePoint, sendAction]
  )

  const handleLiveWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!isLiveMode || !isConnected) return
      if (!isInteracting) return
      e.preventDefault()
      e.stopPropagation()
      const dx = Math.round(e.deltaX)
      const dy = Math.round(e.deltaY)
      if (!dx && !dy) return
      pendingWheelRef.current.dx += dx
      pendingWheelRef.current.dy += dy
      if (!wheelTimerRef.current) {
        wheelTimerRef.current = setTimeout(() => {
          wheelTimerRef.current = null
          const { dx: totalDx, dy: totalDy } = pendingWheelRef.current
          pendingWheelRef.current = { dx: 0, dy: 0 }
          if (totalDx || totalDy) {
            sendAction({ action: 'scroll', dx: totalDx, dy: totalDy })
          }
        }, 50)
      }
    },
    [isLiveMode, isConnected, isInteracting, sendAction]
  )

  const keyToPress = (key: string): string | null => {
    if (key === 'Enter') return 'Enter'
    if (key === 'Tab') return 'Tab'
    if (key === 'Backspace') return 'Backspace'
    if (key === 'Delete') return 'Delete'
    if (key === 'ArrowUp') return 'ArrowUp'
    if (key === 'ArrowDown') return 'ArrowDown'
    if (key === 'ArrowLeft') return 'ArrowLeft'
    if (key === 'ArrowRight') return 'ArrowRight'
    if (key === 'Home') return 'Home'
    if (key === 'End') return 'End'
    if (key === 'PageUp') return 'PageUp'
    if (key === 'PageDown') return 'PageDown'
    return null
  }

  const handleLiveKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isLiveMode || !isConnected) return
      if (!isInteracting) return

      if (e.key === 'Escape') {
        setIsInteracting(false)
        return
      }

      // Avoid hijacking global shortcuts.
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const pressKey = keyToPress(e.key)
      if (pressKey) {
        e.preventDefault()
        sendAction({ action: 'keyboard', type: 'press', key: pressKey })
        return
      }

      if (e.key && e.key.length === 1) {
        e.preventDefault()
        sendAction({ action: 'keyboard', type: 'type', text: e.key })
      }
    },
    [isLiveMode, isConnected, isInteracting, sendAction]
  )

  // Don't render if no screenshots/frames and not active (unless alwaysShow is true)
  if (!alwaysShow) {
    if (!isLiveMode && screenshots.length === 0 && !isEventsActive) {
      return null
    }
    if (isLiveMode && !isConnected && !currentFrame) {
      return null
    }
  }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-lg border border-border/80 bg-card shadow-elevated transition-[width] duration-200',
        isExpanded ? 'w-[480px] max-w-[calc(100vw-2rem)]' : 'w-80 max-w-[calc(100vw-2rem)]',
        className
      )}
    >
      <div
        onPointerDown={draggable ? onDragHandlePointerDown : undefined}
        onDoubleClick={draggable ? onDragHandleDoubleClick : undefined}
        title={draggable ? 'Drag to move · Double-click to reset position' : undefined}
        className={cn(
          'flex items-center gap-1 border-b border-border/80 bg-surface-subtle px-2 py-2 select-none',
          draggable && (isDragging ? 'cursor-grabbing' : 'cursor-grab')
        )}
      >
        {draggable && (
          <span aria-hidden="true" className="flex h-7 w-4 shrink-0 items-center justify-center text-muted-foreground/70">
            <GripVertical className="h-3.5 w-3.5" />
          </span>
        )}
        <Button type="button" variant="ghost" size="icon" onClick={handleClose} aria-label="Close browser viewer" className="h-7 w-7 shrink-0 text-muted-foreground">
          <X className="h-3.5 w-3.5" />
        </Button>

        <div className="flex h-7 min-w-0 flex-1 items-center gap-2 rounded-md border border-border/80 bg-card px-2 text-xs focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-ring/25">
          <Globe aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          {isLiveMode ? (
            <form
              className="flex min-w-0 flex-1 items-center gap-1"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setIsEditingUrl(false)
              }}
              onSubmit={(event) => {
                event.preventDefault()
                sendNavigate(displayedUrl)
                setIsEditingUrl(false)
              }}
            >
              <input
                aria-label="Browser address"
                value={displayedUrl}
                onChange={(event) => setUrlDraft(event.target.value)}
                onFocus={() => {
                  setUrlDraft(displayedUrl)
                  setIsEditingUrl(true)
                }}
                placeholder={canOpenAddressUrl ? '' : 'Enter URL'}
                className={cn('min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground', isEditingUrl ? 'text-foreground' : 'text-muted-foreground')}
              />
              <button type="submit" aria-label="Navigate browser" className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                <CornerDownLeft className="h-3.5 w-3.5" />
              </button>
            </form>
          ) : <span className="truncate text-muted-foreground" title={addressLabel}>{addressLabel}</span>}
          {canOpenAddressUrl && (
            <a href={addressUrl} target="_blank" rel="noopener noreferrer" aria-label="Open browser page in new tab" className="shrink-0 rounded text-muted-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>

        <Button type="button" variant="ghost" size="icon" onClick={toggleMode} aria-label={isLiveMode ? 'Switch to screenshots' : 'Switch to live view'} title={isLiveMode ? 'Switch to screenshots' : 'Switch to live view'} className="h-7 w-7 shrink-0 text-muted-foreground">
          {isLiveMode ? <Images className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </Button>
        {isLiveMode && isConnected && (
          <>
            <Button type="button" variant="ghost" size="icon" onClick={isStreaming ? stopStream : startStream} aria-label={isStreaming ? 'Pause browser stream' : 'Start browser stream'} title={isStreaming ? 'Pause stream' : 'Start stream'} className="h-7 w-7 shrink-0 text-muted-foreground">
              {isStreaming ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            </Button>
            <Button type="button" variant="ghost" size="icon" onClick={captureFrame} aria-label="Capture browser frame" title="Capture frame" className="h-7 w-7 shrink-0 text-muted-foreground">
              <Camera className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
        <Button type="button" variant="ghost" size="icon" onClick={toggleExpand} aria-label={isExpanded ? 'Collapse browser viewer' : 'Expand browser viewer'} className="h-7 w-7 shrink-0 text-muted-foreground">
          {isExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {(isActive || (isLiveMode && isStreaming)) && (
        <div
          onPointerDown={draggable ? onDragHandlePointerDown : undefined}
          onDoubleClick={draggable ? onDragHandleDoubleClick : undefined}
          className={cn(
            'flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-border/70 bg-surface-subtle/50 px-3 py-1.5 text-[11px] tabular-nums text-muted-foreground select-none',
            draggable && (isDragging ? 'cursor-grabbing' : 'cursor-grab')
          )}
        >
          {isActive && (
            <span className="flex min-w-0 items-center gap-1.5">
              <Loader2 aria-hidden="true" className="h-3 w-3 shrink-0 animate-spin text-primary" />
              <span className="truncate">{currentAction || 'Working…'}{typeof currentProgress === 'number' ? ` (${currentProgress}%)` : ''}</span>
            </span>
          )}
          {isLiveMode && isStreaming && (fps > 0 || updatesFps > 0) && (
            <span className="whitespace-nowrap font-mono">
              RX {fps} FPS · UI {updatesFps} upd/s{fps > 0 && updatesFps === 0 ? ' · static' : ''}
            </span>
          )}
        </div>
      )}

      {/* Browser Content */}
      {isExpanded && (
        <>
          {/* Main Screenshot/Frame Display */}
          <div className="relative bg-surface-subtle">
            <div className="max-h-[60vh] min-h-[240px] overflow-auto">
              {/* Live stream mode */}
              {isLiveMode ? (
                liveImageUrl ? (
                  <div
                    className={cn(
                      'relative outline-none',
                      isInteracting ? 'ring-2 ring-primary/40 ring-offset-2 ring-offset-background' : ''
                    )}
                    ref={liveViewportRef}
                    tabIndex={0}
                    onKeyDown={handleLiveKeyDown}
                    onWheel={handleLiveWheel}
                  >
                    <img
                      src={liveImageUrl}
                      alt="Live browser view"
                      className="block w-full h-auto bg-white cursor-crosshair"
                      ref={liveImageRef}
                      onClick={handleLiveClick}
                      draggable={false}
                    />

                    <div className="absolute top-2 left-2">
                      <div className="rounded-md border border-border/80 bg-card/95 px-2 py-1 text-[11px] text-muted-foreground shadow-xs backdrop-blur-sm">
                        {isInteracting ? (
                          <span>
                            Control: <span className="text-foreground/80">ON</span> · Press{' '}
                            <span className="font-mono">Esc</span> to exit
                          </span>
                        ) : (
                          <span>Click the view to control · Scroll + type supported</span>
                        )}
                      </div>
                    </div>

                    {/* If the sandbox browser hasn't navigated anywhere yet, the live view is literally blank.
                        Show a subtle explanation so users don't assume the stream is broken. */}
                    {isBlankLivePage && (
                      <div className="absolute inset-x-0 bottom-0 p-3">
                        <div className="rounded-lg border bg-background/80 backdrop-blur px-3 py-2 text-xs text-muted-foreground shadow-sm">
                          <div className="font-medium text-foreground/80">Live view is ready</div>
                          <div className="mt-0.5">
                            No page has been opened yet. Deep search often uses API search and may not navigate the
                            browser.
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => setViewerMode('events')}
                              className="text-primary hover:underline underline-offset-2"
                            >
                              Switch to screenshots
                            </button>
                            {liveMetaTitle ? (
                              <span className="truncate font-mono text-[10px] opacity-80">{liveMetaTitle}</span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : !isConnected ? (
                  <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                    <div className="text-center">
                      <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-60" />
                      <p className="text-sm">Connecting to live view...</p>
                      <p className="text-xs mt-1 opacity-70">
                        First run can take up to ~1 minute to start the sandbox browser.
                      </p>
                    </div>
                  </div>
                ) : isStarting ? (
                  <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                    <div className="text-center">
                      <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-60" />
                      <p className="text-sm">Starting live view...</p>
                      <p className="text-xs mt-1 opacity-70">
                        Waiting for the first frame. If this takes too long, check the error banner below.
                      </p>
                    </div>
                  </div>
                ) : isStreaming ? (
                  <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                    <div className="text-center">
                      <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-60" />
                      <p className="text-sm">Waiting for first frame...</p>
                      <p className="text-xs mt-1 opacity-70">This can take a bit if the sandbox is cold-starting.</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                    <div className="text-center">
                      <Play className="w-8 h-8 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">Live view is paused</p>
                      <p className="text-xs mt-1 opacity-70">Click play to resume streaming.</p>
                    </div>
                  </div>
                )
              ) : displayScreenshot ? (
                /* Screenshot mode */
                <img
                  src={displayScreenshot.url}
                  alt={`Browser screenshot - ${displayScreenshot.action || 'view'}`}
                  className="block w-full h-auto bg-white"
                  loading="lazy"
                />
              ) : (
                <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                  <div className="text-center">
                    <Globe className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Waiting for browser activity...</p>
                    <button
                      type="button"
                      onClick={() => setViewerMode('stream')}
                      className="mt-2 text-xs text-primary hover:underline underline-offset-2"
                    >
                      Switch to live view
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Action Badge */}
            {!isLiveMode && displayScreenshot?.action && (
              <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/60 text-white text-xs rounded">
                {displayScreenshot.action}
              </div>
            )}

            {/* Live Indicator */}
            {(isLiveMode && isStreaming) || displayScreenshot?.isLive ? (
              <div className="absolute right-2 top-2 flex items-center gap-1.5 rounded-md border border-success-border bg-success-surface px-2 py-1 text-[11px] font-semibold tracking-wide text-success">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-success" />
                LIVE
              </div>
            ) : null}

            {/* Stream Error */}
            {isLiveMode && streamError && (
              <div role="alert" className="absolute bottom-2 left-2 right-2 rounded-md border border-destructive-border bg-destructive-surface px-3 py-2 text-xs text-destructive">
                {streamError}
              </div>
            )}
          </div>

          {/* Screenshot Timeline - only show in events mode */}
          {!isLiveMode && screenshots.length > 1 && (
            <div className="border-t border-border/70 bg-surface-subtle p-2">
              <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-thin">
                {screenshots.map((ss, index) => (
                  <button
                    key={ss.id}
                    type="button"
                    aria-label={`View screenshot ${index + 1}`}
                    aria-pressed={selectedScreenshot?.id === ss.id || (!selectedScreenshot && index === screenshots.length - 1)}
                    onClick={() => setSelectedScreenshot(ss)}
                    className={cn(
                      'relative shrink-0 overflow-hidden rounded-md border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                      'hover:border-primary/50',
                      (selectedScreenshot?.id === ss.id || (!selectedScreenshot && index === screenshots.length - 1))
                        ? 'border-primary ring-1 ring-primary/30'
                        : 'border-transparent'
                    )}
                    title={`${ss.action || 'Screenshot'} - ${new Date(ss.timestamp).toLocaleTimeString()}`}
                  >
                    <img
                      src={ss.url}
                      alt={`Screenshot ${index + 1}`}
                      className="h-12 w-auto object-cover"
                      loading="lazy"
                    />
                    {/* Action label */}
                    {ss.action && (
                      <div className="absolute bottom-0 inset-x-0 bg-black/60 text-white text-[10px] px-1 truncate">
                        {ss.action}
                      </div>
                    )}
                  </button>
                ))}
              </div>
              <div className="mt-1 text-center text-[11px] tabular-nums text-muted-foreground">
                {screenshots.length} screenshot{screenshots.length !== 1 ? 's' : ''}
              </div>
            </div>
          )}
        </>
      )}

      {/* Collapsed View - Show mini preview */}
      {!isExpanded && ((isLiveMode && liveImageUrl) || displayScreenshot) && (
        <button
          type="button"
          aria-label="Expand browser preview"
          className="block h-24 w-full transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset"
          onClick={toggleExpand}
        >
          <img
            src={isLiveMode && liveImageUrl ? liveImageUrl : displayScreenshot?.url || ''}
            alt="Browser preview"
            className="w-full h-full object-cover"
          />
        </button>
      )}
    </div>
  )
}

/**
 * Draggable floating browser viewer anchored to the bottom-left by default.
 * Uses GPU-accelerated translate3d and clamps within its container bounds.
 */
export function FloatingBrowserViewer({
  threadId,
  onClose,
  mode = 'stream',
  defaultExpanded = true,
  alwaysShow = true,
  defaultPosition = 'bottom-left'
}: {
  threadId: string | null
  onClose?: () => void
  mode?: 'events' | 'stream'
  defaultExpanded?: boolean
  alwaysShow?: boolean
  defaultPosition?: 'bottom-left' | 'bottom-right'
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    originX: number
    originY: number
    minX: number
    maxX: number
    minY: number
    maxY: number
  } | null>(null)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)

  const handleDragPointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return
    if ((e.target as HTMLElement).closest('button, a, input, textarea, select, form')) return
    const el = containerRef.current
    const parent = el?.offsetParent as HTMLElement | null
    if (!el || !parent) return

    e.preventDefault()
    const elRect = el.getBoundingClientRect()
    const parentRect = parent.getBoundingClientRect()
    const pad = 12
    const minX = parentRect.left + pad - (elRect.left - offset.x)
    const maxX = Math.max(minX, parentRect.right - pad - (elRect.right - offset.x))
    const minY = parentRect.top + pad - (elRect.top - offset.y)
    const maxY = Math.max(minY, parentRect.bottom - pad - (elRect.bottom - offset.y))

    dragStateRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      originX: offset.x,
      originY: offset.y,
      minX,
      maxX,
      minY,
      maxY
    }
    setIsDragging(true)
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }, [offset.x, offset.y])

  const handleDragPointerMove = useCallback((e: React.PointerEvent) => {
    const drag = dragStateRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    const nextX = Math.max(drag.minX, Math.min(drag.maxX, drag.originX + (e.clientX - drag.startX)))
    const nextY = Math.max(drag.minY, Math.min(drag.maxY, drag.originY + (e.clientY - drag.startY)))
    setOffset({ x: nextX, y: nextY })
  }, [])

  const handleDragPointerEnd = useCallback((e: React.PointerEvent) => {
    const drag = dragStateRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    dragStateRef.current = null
    setIsDragging(false)
  }, [])

  const resetPosition = useCallback(() => {
    setOffset({ x: 0, y: 0 })
  }, [])

  return (
    <div
      ref={containerRef}
      onPointerMove={handleDragPointerMove}
      onPointerUp={handleDragPointerEnd}
      onPointerCancel={handleDragPointerEnd}
      style={{ transform: `translate3d(${offset.x}px, ${offset.y}px, 0)` }}
      className={cn(
        'absolute bottom-3 z-40 max-h-[calc(100%-1.5rem)] max-w-[calc(100%-2rem)] rounded-lg shadow-elevated will-change-transform',
        defaultPosition === 'bottom-left' ? 'left-4' : 'right-4',
        isDragging && 'select-none'
      )}
    >
      <BrowserViewer
        threadId={threadId}
        className="w-[460px] max-w-full"
        defaultExpanded={defaultExpanded}
        alwaysShow={alwaysShow}
        mode={mode}
        onClose={onClose}
        draggable={true}
        isDragging={isDragging}
        onDragHandlePointerDown={handleDragPointerDown}
        onDragHandleDoubleClick={resetPosition}
      />
    </div>
  )
}
