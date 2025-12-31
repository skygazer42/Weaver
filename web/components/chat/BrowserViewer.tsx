'use client'

import React, { useState, useCallback } from 'react'
import { Loader2, Globe, X, Maximize2, Minimize2, ExternalLink, Play, Pause, Camera } from 'lucide-react'
import { cn } from '@/lib/utils'
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
  alwaysShow = false
}: BrowserViewerProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [selectedScreenshot, setSelectedScreenshot] = useState<BrowserScreenshot | null>(null)
  const [viewerMode, setViewerMode] = useState<'events' | 'stream'>(mode)
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
    start: startStream,
    stop: stopStream,
    capture: captureFrame
  } = useBrowserStream({
    threadId: isLiveMode ? threadId : null,
    autoStart: false,
    quality: 70,
    maxFps: 5
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
    setIsExpanded(prev => !prev)
  }, [])

  const toggleMode = useCallback(() => {
    setViewerMode(prev => (prev === 'events' ? 'stream' : 'events'))
  }, [])

  // Determine what to display
  const displayScreenshot = selectedScreenshot || latestScreenshot
  const liveImageUrl = currentFrame ? `data:image/jpeg;base64,${currentFrame.data}` : null

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
        'border rounded-lg overflow-hidden bg-background shadow-lg transition-all duration-200',
        isExpanded ? 'w-[480px] max-w-[calc(100vw-3rem)]' : 'w-80',
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
            onClick={() => setIsExpanded(false)}
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
            {displayScreenshot?.pageUrl || 'Browser'}
          </span>
          {displayScreenshot?.pageUrl && (
            <a
              href={displayScreenshot.pageUrl}
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
            {isStreaming && fps > 0 && (
              <span className="text-[10px] text-muted-foreground">{fps} FPS</span>
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

      {/* Browser Content */}
      {isExpanded && (
        <>
          {/* Main Screenshot/Frame Display */}
          <div className="relative bg-muted/30">
            <div className="max-h-[60vh] min-h-[240px] overflow-auto">
              {/* Live stream mode */}
              {isLiveMode && liveImageUrl ? (
                <img
                  src={liveImageUrl}
                  alt="Live browser view"
                  className="block w-full h-auto bg-white"
                />
              ) : isLiveMode && isConnected ? (
                <div className="flex items-center justify-center min-h-[240px] text-muted-foreground">
                  <div className="text-center">
                    <Play className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Click play to start live view</p>
                  </div>
                </div>
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
                    onClick={() => setSelectedScreenshot(ss)}
                    className={cn(
                      'relative flex-shrink-0 rounded border-2 overflow-hidden transition-all',
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
          <img
            src={isLiveMode && liveImageUrl ? liveImageUrl : displayScreenshot?.url || ''}
            alt="Browser preview"
            className="w-full h-full object-cover"
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
      className="fixed z-50"
      style={{ left: position.x, top: position.y }}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseUp}
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
