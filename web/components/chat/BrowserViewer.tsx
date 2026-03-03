'use client'

import React, { useState, useCallback, useEffect, useReducer, useRef } from 'react'
import Image from 'next/image'
import {
  Loader2,
  Globe,
  Maximize2,
  Minimize2,
  ExternalLink,
  Play,
  Pause,
  Camera,
  CursorClick,
  Check,
  XCircle,
} from '@/components/ui/icons'
import { cn } from '@/lib/utils'
import { BrowserScreenshot } from '@/types/browser'
import { useBrowserEvents } from '@/hooks/useBrowserEvents'
import { useBrowserStream } from '@/hooks/useBrowserStream'
import { toPlaywrightKeyboardAction } from '@/lib/browser/keyboard'

interface BrowserViewerProps {
  threadId: string | null
  className?: string
  onClose?: () => void
  defaultExpanded?: boolean
  mode?: 'events' | 'stream'  // 'events' = SSE screenshots, 'stream' = WebSocket live
  alwaysShow?: boolean  // Always show the viewer, even without screenshots
}

interface BrowserViewerState {
  isExpanded: boolean
  selectedScreenshot: BrowserScreenshot | null
  viewerMode: 'events' | 'stream'
  controlEnabled: boolean
}

type BrowserViewerAction =
  | { type: 'SET_EXPANDED'; payload: boolean }
  | { type: 'TOGGLE_EXPAND' }
  | { type: 'SET_SELECTED_SCREENSHOT'; payload: BrowserScreenshot | null }
  | { type: 'SET_MODE'; payload: 'events' | 'stream' }
  | { type: 'TOGGLE_MODE' }
  | { type: 'SET_CONTROL'; payload: boolean }
  | { type: 'TOGGLE_CONTROL' }

function browserViewerReducer(state: BrowserViewerState, action: BrowserViewerAction): BrowserViewerState {
  switch (action.type) {
    case 'SET_EXPANDED':
      return { ...state, isExpanded: action.payload }
    case 'TOGGLE_EXPAND':
      return { ...state, isExpanded: !state.isExpanded }
    case 'SET_SELECTED_SCREENSHOT':
      return { ...state, selectedScreenshot: action.payload }
    case 'SET_MODE':
      return { ...state, viewerMode: action.payload }
    case 'TOGGLE_MODE':
      return { ...state, viewerMode: state.viewerMode === 'events' ? 'stream' : 'events' }
    case 'SET_CONTROL':
      return { ...state, controlEnabled: action.payload }
    case 'TOGGLE_CONTROL':
      return { ...state, controlEnabled: !state.controlEnabled }
    default:
      return state
  }
}

function clamp01(value: number) {
  if (!Number.isFinite(value)) return 0
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

function getNormalizedPoint(target: HTMLDivElement, clientX: number, clientY: number) {
  const rect = target.getBoundingClientRect()
  if (!rect.width || !rect.height) return { x: 0, y: 0 }
  const x = (clientX - rect.left) / rect.width
  const y = (clientY - rect.top) / rect.height
  return { x: clamp01(x), y: clamp01(y) }
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
  mode = 'stream',
  alwaysShow = false
}: BrowserViewerProps) {
  const initialState: BrowserViewerState = {
    isExpanded: defaultExpanded,
    selectedScreenshot: null,
    viewerMode: mode,
    controlEnabled: false,
  }

  const [state, dispatch] = useReducer(browserViewerReducer, initialState)
  const { isExpanded, selectedScreenshot, viewerMode, controlEnabled } = state
  const isLiveMode = viewerMode === 'stream'

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
    currentFrame,
    fps,
    error: streamError,
    lastAck,
    start: startStream,
    stop: stopStream,
    capture: captureFrame,
    sendInputAction,
    sendInputActionNoAck,
  } = useBrowserStream({
    threadId: isLiveMode ? threadId : null,
    autoStart: true,
    quality: 70,
    maxFps: 10
  })

  const isActive = isLiveMode ? isStreaming : isEventsActive

  const handleClose = useCallback(() => {
    if (isLiveMode) {
      stopStream()
    }
    clearScreenshots()
    onClose?.()
  }, [isLiveMode, stopStream, clearScreenshots, onClose])

  const toggleExpand = useCallback(() => {
    dispatch({ type: 'TOGGLE_EXPAND' })
  }, [])

  const toggleMode = useCallback(() => {
    dispatch({ type: 'TOGGLE_MODE' })
    dispatch({ type: 'SET_CONTROL', payload: false })
  }, [])

  useEffect(() => {
    if (controlEnabled && (!isLiveMode || !isConnected)) {
      dispatch({ type: 'SET_CONTROL', payload: false })
    }
  }, [controlEnabled, isConnected, isLiveMode])

  // Determine what to display
  const displayScreenshot = selectedScreenshot || latestScreenshot
  const liveImageUrl = currentFrame ? `data:image/jpeg;base64,${currentFrame.data}` : null
  const livePageUrl = typeof currentFrame?.metadata?.url === 'string' ? currentFrame.metadata.url : null
  const effectivePageUrl = isLiveMode ? livePageUrl : (displayScreenshot?.pageUrl || null)

  const [navigateUrl, setNavigateUrl] = useState('')
  const [typeText, setTypeText] = useState('')
  const [isSendingControl, setIsSendingControl] = useState(false)

  const controlSurfaceRef = useRef<HTMLDivElement | null>(null)
  const pointerStateRef = useRef<{
    pointerType: 'mouse' | 'touch' | 'pen'
    pointerId: number
    startNormX: number
    startNormY: number
    startClientX: number
    startClientY: number
    lastClientX: number
    lastClientY: number
    dragStarted: boolean
    lastMoveSentAt: number
    button: 'left' | 'middle' | 'right'
  } | null>(null)

  useEffect(() => {
    if (!controlEnabled) return
    // Give React a tick to render the focusable surface.
    const t = setTimeout(() => controlSurfaceRef.current?.focus(), 0)
    return () => clearTimeout(t)
  }, [controlEnabled])

  const canControl = Boolean(isLiveMode && isConnected)

  const handleControlPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!controlEnabled || !canControl) return
    if (!liveImageUrl) return

    const pointerType = e.pointerType === 'pen' ? 'pen' : e.pointerType === 'touch' ? 'touch' : 'mouse'
    if (pointerType === 'mouse' && e.button !== 0 && e.button !== 1 && e.button !== 2) return

    e.preventDefault()
    e.stopPropagation()

    const button = pointerType === 'mouse'
      ? (e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left')
      : 'left'
    const { x, y } = getNormalizedPoint(e.currentTarget, e.clientX, e.clientY)

    pointerStateRef.current = {
      pointerType,
      pointerId: e.pointerId,
      startNormX: x,
      startNormY: y,
      startClientX: e.clientX,
      startClientY: e.clientY,
      lastClientX: e.clientX,
      lastClientY: e.clientY,
      dragStarted: false,
      lastMoveSentAt: 0,
      button,
    }

    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // Ignore capture failures; events may still work.
    }

    e.currentTarget.focus()
  }, [canControl, controlEnabled, liveImageUrl])

  const handleControlPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const state = pointerStateRef.current
    if (!controlEnabled || !canControl) return
    if (!state || state.pointerId !== e.pointerId) return
    if (!liveImageUrl) return

    if (state.pointerType === 'touch' || state.pointerType === 'pen') {
      const now = Date.now()
      const deltaX = e.clientX - state.lastClientX
      const deltaY = e.clientY - state.lastClientY
      state.lastClientX = e.clientX
      state.lastClientY = e.clientY

      const movedFarEnough = Math.hypot(e.clientX - state.startClientX, e.clientY - state.startClientY) >= 6
      if (!state.dragStarted && movedFarEnough) {
        state.dragStarted = true
      }

      if (!state.dragStarted) return

      e.preventDefault()
      e.stopPropagation()

      if (now - state.lastMoveSentAt < 30) return
      state.lastMoveSentAt = now

      const dx = Math.round(-deltaX)
      const dy = Math.round(-deltaY)
      if (dx === 0 && dy === 0) return
      sendInputActionNoAck({ action: 'scroll', dx, dy })
      return
    }

    const distX = e.clientX - state.startClientX
    const distY = e.clientY - state.startClientY
    const movedFarEnough = Math.hypot(distX, distY) >= 4

    if (!state.dragStarted && movedFarEnough) {
      state.dragStarted = true

      sendInputActionNoAck({ action: 'mouse', type: 'move', x: state.startNormX, y: state.startNormY })
      void sendInputAction({ action: 'mouse', type: 'down', button: state.button }).catch(() => {})
    }

    if (!state.dragStarted) return

    const now = Date.now()
    if (now - state.lastMoveSentAt < 30) return
    state.lastMoveSentAt = now

    const { x, y } = getNormalizedPoint(e.currentTarget, e.clientX, e.clientY)
    sendInputActionNoAck({ action: 'mouse', type: 'move', x, y })
  }, [canControl, controlEnabled, liveImageUrl, sendInputAction, sendInputActionNoAck])

  const handleControlPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const state = pointerStateRef.current
    if (!controlEnabled || !canControl) return
    if (!state || state.pointerId !== e.pointerId) return
    if (!liveImageUrl) return

    e.preventDefault()
    e.stopPropagation()

    pointerStateRef.current = null

    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // ignore
    }

    const { x, y } = getNormalizedPoint(e.currentTarget, e.clientX, e.clientY)
    if (state.pointerType === 'touch' || state.pointerType === 'pen') {
      if (!state.dragStarted) {
        void sendInputAction({
          action: 'mouse',
          type: 'click',
          x,
          y,
          button: 'left',
          clicks: 1,
        }).catch(() => {})
      }
      return
    }

    if (state.dragStarted) {
      sendInputActionNoAck({ action: 'mouse', type: 'move', x, y })
      void sendInputAction({ action: 'mouse', type: 'up', button: state.button }).catch(() => {})
      return
    }

    void sendInputAction({
      action: 'mouse',
      type: 'click',
      x,
      y,
      button: state.button,
      clicks: 1,
    }).catch(() => {})
  }, [canControl, controlEnabled, liveImageUrl, sendInputAction, sendInputActionNoAck])

  const handleControlPointerCancel = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const state = pointerStateRef.current
    if (!controlEnabled || !canControl) return
    if (!state || state.pointerId !== e.pointerId) return

    pointerStateRef.current = null
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // ignore
    }

    if (state.dragStarted && state.pointerType === 'mouse') {
      void sendInputAction({ action: 'mouse', type: 'up', button: state.button }).catch(() => {})
    }
  }, [canControl, controlEnabled, sendInputAction])

  const handleControlWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    if (!controlEnabled || !canControl) return
    if (!liveImageUrl) return

    e.preventDefault()
    e.stopPropagation()

    const dx = Math.round(e.deltaX)
    const dy = Math.round(e.deltaY)
    sendInputActionNoAck({ action: 'scroll', dx, dy })
  }, [canControl, controlEnabled, liveImageUrl, sendInputActionNoAck])

  const handleControlKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!controlEnabled || !canControl) return

    // Let tab move focus within the viewer (avoid trapping).
    if (e.key === 'Tab') return

    const action = toPlaywrightKeyboardAction({
      key: e.key,
      ctrlKey: e.ctrlKey,
      metaKey: e.metaKey,
      altKey: e.altKey,
      shiftKey: e.shiftKey,
    })
    if (action.kind === 'ignore') return

    e.preventDefault()
    e.stopPropagation()
    if (action.kind === 'type') {
      void sendInputAction({ action: 'keyboard', type: 'type', text: action.text }).catch(() => {})
      return
    }

    void sendInputAction({ action: 'keyboard', type: 'press', key: action.key }).catch(() => {})
  }, [canControl, controlEnabled, sendInputAction])

  const handleControlPaste = useCallback((e: React.ClipboardEvent<HTMLDivElement>) => {
    if (!controlEnabled || !canControl) return
    const text = e.clipboardData.getData('text')
    if (!text) return
    e.preventDefault()
    e.stopPropagation()
    void sendInputAction({ action: 'keyboard', type: 'type', text }).catch(() => {})
  }, [canControl, controlEnabled, sendInputAction])

  const handleControlContextMenu = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!controlEnabled || !canControl) return
    e.preventDefault()
  }, [canControl, controlEnabled])

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
        'border rounded-lg overflow-hidden bg-background shadow-lg',
        isExpanded ? 'w-full md:w-[480px] max-w-[calc(100vw-2rem)]' : 'w-80',
        className
      )}
    >
      {/* Browser Chrome - Title Bar */}
      <div className="bg-muted/80 px-3 py-2 flex items-center gap-2 border-b">
        {/* Traffic Light Buttons */}
        <div className="flex gap-1.5">
          <button
            onClick={handleClose}
            className="w-3 h-3 rounded-full bg-red-500 hover:bg-red-600 transition-colors"
            title="Close"
          />
          <button
            onClick={() => dispatch({ type: 'SET_EXPANDED', payload: false })}
            className="w-3 h-3 rounded-full bg-yellow-500 hover:bg-yellow-600 transition-colors"
            title="Minimize"
          />
          <button
            onClick={toggleExpand}
            className="w-3 h-3 rounded-full bg-green-500 hover:bg-green-600 transition-colors"
            title={isExpanded ? 'Collapse' : 'Expand'}
          />
        </div>

        {/* Address Bar */}
        <div className="flex-1 flex items-center gap-2 bg-background/60 rounded px-2 py-1 text-xs">
          <Globe className="w-3 h-3 text-muted-foreground flex-shrink-0" />
          <span className="truncate text-muted-foreground">
            {effectivePageUrl || 'Browser'}
          </span>
          {effectivePageUrl && (
            <a
              href={effectivePageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 hover:text-primary"
              title="Open in new tab"
            >
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>

        {/* Mode Toggle */}
        <button
          onClick={toggleMode}
          className="p-1 hover:bg-background/60 rounded transition-colors"
          title={isLiveMode ? 'Switch to screenshots' : 'Switch to live view'}
        >
          {isLiveMode ? (
            <Camera className="w-3.5 h-3.5 text-muted-foreground" />
          ) : (
            <Play className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </button>

        {/* Control Toggle (Live Mode Only) */}
        {isLiveMode && (
          <button
            onClick={() => dispatch({ type: 'TOGGLE_CONTROL' })}
            disabled={!canControl}
            className={cn(
              'p-1 rounded transition-colors',
              !canControl && 'opacity-40 cursor-not-allowed',
              controlEnabled
                ? 'bg-primary/15 text-primary'
                : 'hover:bg-background/60 text-muted-foreground'
            )}
            title={controlEnabled ? 'Disable control' : 'Enable control'}
          >
            <CursorClick className="w-3.5 h-3.5" />
          </button>
        )}

        {/* Status Indicator */}
        {isActive && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin text-primary" />
            <span className="hidden sm:inline">
              {currentAction || 'Working...'}
              {typeof currentProgress === 'number' ? ` (${currentProgress}%)` : ''}
            </span>
          </div>
        )}

        {/* Live Stream Controls */}
        {isLiveMode && isConnected && (
          <div className="flex items-center gap-1">
            {isStreaming ? (
              <button
                onClick={stopStream}
                className="p-1 hover:bg-background/60 rounded transition-colors"
                title="Stop streaming"
              >
                <Pause className="w-3.5 h-3.5 text-red-500" />
              </button>
            ) : (
              <button
                onClick={startStream}
                className="p-1 hover:bg-background/60 rounded transition-colors"
                title="Start streaming"
              >
                <Play className="w-3.5 h-3.5 text-green-500" />
              </button>
            )}
            <button
              onClick={captureFrame}
              className="p-1 hover:bg-background/60 rounded transition-colors"
              title="Capture frame"
            >
              <Camera className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
            {isStreaming && (
              <span className="text-[10px] text-muted-foreground">
                {Math.max(0, Number.isFinite(fps) ? fps : 0)} FPS
              </span>
            )}
          </div>
        )}

        {/* Expand/Collapse Button */}
        <button
          onClick={toggleExpand}
          className="p-1 hover:bg-background/60 rounded transition-colors"
          title={isExpanded ? 'Collapse' : 'Expand'}
        >
          {isExpanded ? (
            <Minimize2 className="w-3.5 h-3.5 text-muted-foreground" />
          ) : (
            <Maximize2 className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </button>
      </div>

      {/* Control Panel (Live Mode Only) */}
      {isExpanded && controlEnabled && isLiveMode && (
        <div className="bg-muted/40 px-3 py-2 border-b flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <form
              className="flex-1 flex items-center gap-2"
              onSubmit={async (e) => {
                e.preventDefault()
                const url = navigateUrl.trim()
                if (!url) return
                setIsSendingControl(true)
                try {
                  await sendInputAction({ action: 'navigate', url })
                  setNavigateUrl('')
                  controlSurfaceRef.current?.focus()
                } finally {
                  setIsSendingControl(false)
                }
              }}
            >
              <input
                value={navigateUrl}
                onChange={(e) => setNavigateUrl(e.target.value)}
                placeholder="https://example.com"
                className="flex-1 h-8 px-2 rounded border bg-background text-xs outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                type="submit"
                disabled={!canControl || isSendingControl}
                className={cn(
                  'h-8 px-2 rounded border text-xs transition-colors',
                  'hover:bg-background/60',
                  (!canControl || isSendingControl) && 'opacity-50 cursor-not-allowed'
                )}
                title="Navigate"
              >
                Go
              </button>
            </form>

            {lastAck && typeof lastAck.ok === 'boolean' ? (
              <div
                className={cn(
                  'flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border bg-background/70 max-w-[45%]',
                  lastAck.ok ? 'text-emerald-700 border-emerald-200' : 'text-red-700 border-red-200'
                )}
                title={lastAck.ok ? `OK: ${lastAck.action}` : (lastAck.error || 'Action failed')}
              >
                {lastAck.ok ? (
                  <Check className="w-3 h-3 flex-shrink-0" />
                ) : (
                  <XCircle className="w-3 h-3 flex-shrink-0" />
                )}
                <span className="truncate">
                  {lastAck.ok ? lastAck.action : (lastAck.error || 'Failed')}
                </span>
              </div>
            ) : null}
          </div>

          <form
            className="flex items-center gap-2"
            onSubmit={async (e) => {
              e.preventDefault()
              const text = typeText
              if (!text.trim()) return
              setIsSendingControl(true)
              try {
                await sendInputAction({ action: 'keyboard', type: 'type', text })
                setTypeText('')
                controlSurfaceRef.current?.focus()
              } finally {
                setIsSendingControl(false)
              }
            }}
          >
            <input
              value={typeText}
              onChange={(e) => setTypeText(e.target.value)}
              placeholder="Type to page (press Enter to send)"
              className="flex-1 h-8 px-2 rounded border bg-background text-xs outline-none focus:ring-2 focus:ring-primary/40"
            />
            <button
              type="submit"
              disabled={!canControl || isSendingControl}
              className={cn(
                'h-8 px-2 rounded border text-xs transition-colors',
                'hover:bg-background/60',
                (!canControl || isSendingControl) && 'opacity-50 cursor-not-allowed'
              )}
              title="Send text"
            >
              Type
            </button>
            <button
              type="button"
              disabled={!canControl || isSendingControl}
              className={cn(
                'h-8 px-2 rounded border text-xs transition-colors',
                'hover:bg-background/60',
                (!canControl || isSendingControl) && 'opacity-50 cursor-not-allowed'
              )}
              title="Press Enter"
              onClick={async () => {
                setIsSendingControl(true)
                try {
                  await sendInputAction({ action: 'keyboard', type: 'press', key: 'Enter' })
                  controlSurfaceRef.current?.focus()
                } finally {
                  setIsSendingControl(false)
                }
              }}
            >
              Enter
            </button>
          </form>

          <div className="text-[11px] text-muted-foreground">
            Click/drag to interact · Scroll to scroll · Focus the preview to send keys · Paste to type quickly
          </div>
        </div>
      )}

      {/* Browser Content */}
      {isExpanded && (
        <>
          {/* Main Screenshot/Frame Display */}
          <div className="relative bg-muted/30">
            <div className="max-h-[50vh] md:max-h-[60vh] min-h-[240px] overflow-auto">
              {/* Live stream mode */}
              {isLiveMode && liveImageUrl ? (
                <div
                  ref={controlSurfaceRef}
                  tabIndex={controlEnabled ? 0 : -1}
                  className={cn(
                    'relative w-full outline-none',
                    controlEnabled && canControl && 'cursor-crosshair touch-none focus:ring-2 focus:ring-primary/40',
                  )}
                  onPointerDown={handleControlPointerDown}
                  onPointerMove={handleControlPointerMove}
                  onPointerUp={handleControlPointerUp}
                  onPointerCancel={handleControlPointerCancel}
                  onWheel={handleControlWheel}
                  onKeyDown={handleControlKeyDown}
                  onPaste={handleControlPaste}
                  onContextMenu={handleControlContextMenu}
                >
                  <Image
                    src={liveImageUrl}
                    alt="Live browser view"
                    width={1280}
                    height={720}
                    unoptimized
                    className={cn(
                      'block w-full h-auto bg-white',
                      controlEnabled && canControl && 'select-none'
                    )}
                    sizes="(max-width: 768px) 100vw, 1280px"
                    priority
                  />

                  {controlEnabled && canControl && (
                    <div className="pointer-events-none absolute bottom-2 left-2 px-2 py-0.5 bg-black/60 text-white text-[11px] rounded">
                      Control enabled
                    </div>
                  )}

                  {isLiveMode && liveImageUrl && (!effectivePageUrl || effectivePageUrl === 'about:blank') && (
                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-4">
                      <div className="max-w-[520px] rounded bg-black/60 text-white px-3 py-2 text-[11px] leading-relaxed">
                        <div className="font-medium">Browser is idle</div>
                        <div className="opacity-90">
                          Enable control (cursor icon) to navigate, or ask the agent to use browser tools.
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : isLiveMode && isConnected ? (
                <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                  <div className="text-center">
                    <Play className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Starting live view...</p>
                  </div>
                </div>
              ) : displayScreenshot ? (
                /* Screenshot mode */
                <Image
                  src={displayScreenshot.url}
                  alt={`Browser screenshot - ${displayScreenshot.action || 'view'}`}
                  width={1280}
                  height={720}
                  unoptimized
                  className="block w-full h-auto bg-white"
                  loading="lazy"
                  sizes="(max-width: 768px) 100vw, 1280px"
                />
              ) : (
                <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                  <div className="text-center">
                    <Globe className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Waiting for browser activity...</p>
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
            {(isLiveMode && isStreaming && Boolean(liveImageUrl)) || displayScreenshot?.isLive ? (
              <div className="absolute top-2 right-2 flex items-center gap-1 px-2 py-0.5 bg-red-600 text-white text-xs rounded">
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
                LIVE
              </div>
            ) : null}

            {/* Stream Error */}
            {isLiveMode && streamError && (
              <div className="absolute bottom-2 left-2 right-2 px-2 py-1 bg-red-600/90 text-white text-xs rounded">
                {streamError}
              </div>
            )}
          </div>

          {/* Screenshot Timeline - only show in events mode */}
          {!isLiveMode && screenshots.length > 1 && (
            <div className="bg-muted/40 p-2 border-t">
              <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-thin">
                {screenshots.map((ss, index) => (
                  <button
                    key={ss.id}
                    onClick={() => dispatch({ type: 'SET_SELECTED_SCREENSHOT', payload: ss })}
                    className={cn(
                      'relative flex-shrink-0 rounded border-2 overflow-hidden transition-colors duration-200',
                      'hover:border-primary/50',
                      (selectedScreenshot?.id === ss.id || (!selectedScreenshot && index === screenshots.length - 1))
                        ? 'border-primary ring-1 ring-primary/30'
                        : 'border-transparent'
                    )}
                    title={`${ss.action || 'Screenshot'} - ${new Date(ss.timestamp).toLocaleTimeString()}`}
                  >
                    <Image
                      src={ss.url}
                      alt={`Screenshot ${index + 1}`}
                      width={160}
                      height={96}
                      unoptimized
                      className="h-12 w-auto object-cover"
                      loading="lazy"
                      sizes="160px"
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
              <div className="text-[10px] text-muted-foreground mt-1 text-center">
                {screenshots.length} screenshot{screenshots.length !== 1 ? 's' : ''}
              </div>
            </div>
          )}
        </>
      )}

      {/* Collapsed View - Show mini preview */}
      {!isExpanded && ((isLiveMode && liveImageUrl) || displayScreenshot) && (
        <div
          className="h-24 cursor-pointer hover:opacity-80 transition-opacity"
          onClick={toggleExpand}
        >
          <Image
            src={isLiveMode && liveImageUrl ? liveImageUrl : (displayScreenshot as BrowserScreenshot).url}
            alt="Browser preview"
            width={480}
            height={96}
            unoptimized
            className="w-full h-full object-cover"
            sizes="(max-width: 768px) 100vw, 480px"
          />
        </div>
      )}
    </div>
  )
}

/**
 * Floating browser viewer that can be positioned anywhere
 */
export function FloatingBrowserViewer({
  threadId,
  onClose
}: {
  threadId: string | null
  onClose?: () => void
}) {
  const [position, setPosition] = useState({ x: 20, y: 20 })
  const [isDragging, setIsDragging] = useState(false)

  // Simple drag implementation
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button, a, img')) return
    setIsDragging(true)
  }, [])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return
    setPosition(prev => ({
      x: prev.x + e.movementX,
      y: prev.y + e.movementY
    }))
  }, [isDragging])

  return (
    <div
      className="fixed z-50 touch-none"
      style={{ left: position.x, top: position.y }}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseUp}
      onTouchStart={(e) => {
        if ((e.target as HTMLElement).closest('button, a, img')) return
        // Simple touch drag support could be added here similar to mouse
      }}
    >
      <BrowserViewer
        threadId={threadId}
        onClose={onClose}
        className={cn(
          'w-96 shadow-xl',
          isDragging && 'cursor-grabbing'
        )}
      />
    </div>
  )
}
