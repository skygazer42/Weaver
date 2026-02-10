'use client'

import React, { useEffect, useState, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { Header } from './Header'
import { EmptyState } from './EmptyState'
import { ChatInput } from './ChatInput'
import { ScrollToBottomButton, InterruptBanner, MobileArtifactsOverlay } from './ChatOverlays'
import { Monitor } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Message } from '@/types/chat'
import { useChatState } from '@/hooks/useChatState'
import { useChatHistory } from '@/hooks/useChatHistory'
import { useChatStream } from '@/hooks/useChatStream'
import { filesToImageAttachments } from '@/lib/file-utils'
import { LoadingSkeleton } from '@/components/ui/loading'
import { ChatErrorBoundary } from '@/components/ui/error-boundary'
import { useSwipeGesture } from '@/hooks/useSwipeGesture'
import { useRef } from 'react'

// Dynamic imports for heavy components
const ArtifactsPanel = dynamic(
  () => import('./ArtifactsPanel').then(mod => ({ default: mod.ArtifactsPanel })),
  {
    loading: () => <div className="w-[400px] h-full flex items-center justify-center"><LoadingSkeleton className="w-full h-full" /></div>,
    ssr: false
  }
)

const BrowserViewer = dynamic(
  () => import('./BrowserViewer').then(mod => ({ default: mod.BrowserViewer })),
  { ssr: false }
)

const SettingsDialog = dynamic(
  () => import('@/components/settings/SettingsDialog').then(mod => ({ default: mod.SettingsDialog })),
  { ssr: false }
)

const Discover = dynamic(
  () => import('@/components/views/Discover').then(mod => ({ default: mod.Discover })),
  {
    loading: () => <div className="h-full w-full p-6"><LoadingSkeleton className="h-full w-full" /></div>,
    ssr: false
  }
)

const Library = dynamic(
  () => import('@/components/views/Library').then(mod => ({ default: mod.Library })),
  {
    loading: () => <div className="h-full w-full p-6"><LoadingSkeleton className="h-full w-full" /></div>,
    ssr: false
  }
)

const ChatMessages = dynamic(
  () => import('./ChatMessages').then(mod => ({ default: mod.ChatMessages })),
  {
    loading: () => (
      <div className="flex-1 p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          <LoadingSkeleton className="h-20 w-full" />
          <LoadingSkeleton className="h-24 w-full" />
          <LoadingSkeleton className="h-16 w-2/3" />
        </div>
      </div>
    ),
    ssr: false
  }
)

const Sidebar = dynamic(
  () => import('./Sidebar').then(mod => ({ default: mod.Sidebar })),
  {
    loading: () => (
      <div className="hidden md:flex w-[260px] border-r bg-card">
        <div className="w-full p-3 space-y-2">
          <LoadingSkeleton className="h-10 w-full" />
          <LoadingSkeleton className="h-8 w-full" />
          <LoadingSkeleton className="h-8 w-5/6" />
          <LoadingSkeleton className="h-8 w-4/5" />
        </div>
      </div>
    ),
    ssr: false
  }
)

export function Chat() {
  // Unified UI state via reducer
  const {
    state: ui,
    toggleSidebar,
    toggleArtifacts,
    setMobileArtifacts,
    setScrollButton,
    setSettings,
    setBrowserViewer,
    setView,
    setModel,
    setSearchMode,
    resetForNewChat,
  } = useChatState()

  // Session state
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])

  // Chat history
  const {
    history,
    isHistoryLoading,
    saveToHistory,
    loadSession,
    deleteSession,
    clearHistory,
    togglePin,
    renameSession
  } = useChatHistory()

  // Chat stream
  const {
    messages,
    setMessages,
    isLoading,
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
  } = useChatStream({ selectedModel: ui.selectedModel, searchMode: ui.searchMode })

  // Auto-save messages
  useEffect(() => {
    if (messages.length > 0 && currentSessionId && !isLoading) {
      saveToHistory(messages, currentSessionId)
    }
  }, [messages, currentSessionId, isLoading, saveToHistory])

  // Handlers
  const handleNewChat = useCallback(() => {
    if (messages.length > 0) {
      saveToHistory(messages, currentSessionId || undefined)
    }

    setCurrentSessionId(null)
    setMessages([])
    setArtifacts([])
    setCurrentStatus('')
    setInput('')
    setThreadId(null)
    setPendingInterrupt(null)
    resetForNewChat()
    handleStop()
  }, [messages, currentSessionId, saveToHistory, setMessages, setArtifacts, setCurrentStatus, setThreadId, setPendingInterrupt, resetForNewChat, handleStop])

  const handleDeleteChat = useCallback((id: string) => {
    deleteSession(id)
    if (currentSessionId === id) {
      handleNewChat()
    }
  }, [deleteSession, currentSessionId, handleNewChat])

  const handleClearHistory = useCallback(() => {
    clearHistory()
    handleNewChat()
  }, [clearHistory, handleNewChat])

  const handleChatSelect = useCallback((id: string) => {
    if (messages.length > 0) {
      saveToHistory(messages, currentSessionId || undefined)
    }

    const loadedMessages = loadSession(id)
    if (loadedMessages) {
      setMessages(loadedMessages)
      setCurrentSessionId(id)
      setView('dashboard')
      setArtifacts([])
      setCurrentStatus('')
      setInput('')
      setThreadId(null)
      setPendingInterrupt(null)
      handleStop()
    }
  }, [messages, currentSessionId, saveToHistory, loadSession, setMessages, setView, setArtifacts, setCurrentStatus, setThreadId, setPendingInterrupt, handleStop])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if ((!input.trim() && attachments.length === 0) || isLoading) return

    const imagePayloads = await filesToImageAttachments(attachments)

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim(),
      attachments: imagePayloads
    }

    const newHistory = [...messages, userMessage]
    setMessages(newHistory)
    setInput('')
    setAttachments([])

    if (!currentSessionId && newHistory.length === 1) {
      const id = saveToHistory(newHistory)
      if (id) setCurrentSessionId(id)
    } else if (currentSessionId) {
      saveToHistory(newHistory, currentSessionId)
    }

    await processChat(newHistory, imagePayloads)
  }, [input, attachments, isLoading, messages, currentSessionId, setMessages, saveToHistory, processChat])

  const handleEditMessage = useCallback(async (id: string, newContent: string) => {
    const index = messages.findIndex(m => m.id === id)
    if (index === -1) return

    const previousMessages = messages.slice(0, index)
    const updatedMessage: Message = { ...messages[index], content: newContent }
    const newHistory = [...previousMessages, updatedMessage]
    setMessages(newHistory)

    if (updatedMessage.role === 'user') {
      await processChat(newHistory, updatedMessage.attachments)
    }
  }, [messages, setMessages, processChat])

  const handleStarterClick = useCallback((text: string, mode: string) => {
    setInput(text)
    setSearchMode(mode)
  }, [setSearchMode])

  const handleAtBottomChange = useCallback((atBottom: boolean) => {
    setScrollButton(!atBottom)
  }, [setScrollButton])

  const scrollToBottom = useCallback(() => {
    // ChatMessages handles this internally
  }, [])

  // Render content based on current view
  const renderContent = () => {
    if (ui.currentView === 'discover') return <Discover />
    if (ui.currentView === 'library') return <Library />

    return (
      <div className="flex-1 flex flex-col min-h-0">
        {messages.length === 0 ? (
          <div className="h-full w-full p-4 overflow-y-auto">
            <EmptyState
              selectedMode={ui.searchMode}
              onModeSelect={setSearchMode}
              onStarterClick={handleStarterClick}
            />
          </div>
        ) : (
          <ChatErrorBoundary
            onError={(error, errorInfo) => {
              console.error('[ChatMessages] Render crash:', {
                component: 'ChatMessages',
                error: error.message,
                stack: errorInfo.componentStack,
                timestamp: new Date().toISOString(),
              })
            }}
          >
            <ChatMessages
              messages={messages}
              isLoading={isLoading}
              currentStatus={currentStatus}
              onEditMessage={handleEditMessage}
              onAtBottomChange={handleAtBottomChange}
            />
          </ChatErrorBoundary>
        )}
      </div>
    )
  }

  // Swipe gestures for mobile sidebar
  const containerRef = useRef<HTMLDivElement>(null)
  useSwipeGesture(containerRef, {
    onSwipeRight: () => {
      if (!ui.sidebarOpen) toggleSidebar()
    },
    onSwipeLeft: () => {
      if (ui.sidebarOpen) toggleSidebar()
    },
    threshold: 60
  })

  return (
    <div ref={containerRef} className="flex h-dvh w-full overflow-hidden bg-background text-foreground font-sans selection:bg-primary/20">
      {/* Sidebar */}
      <Sidebar
        isOpen={ui.sidebarOpen}
        onToggle={toggleSidebar}
        onNewChat={handleNewChat}
        onSelectChat={handleChatSelect}
        onDeleteChat={handleDeleteChat}
        onTogglePin={togglePin}
        onRenameChat={renameSession}
        onClearHistory={handleClearHistory}
        onOpenSettings={() => setSettings(true)}
        activeView={ui.currentView}
        onViewChange={(v: string) => setView(v as 'dashboard' | 'discover' | 'library')}
        history={history}
        isLoading={isHistoryLoading}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <Header
          sidebarOpen={ui.sidebarOpen}
          onToggleSidebar={toggleSidebar}
          selectedModel={ui.selectedModel}
          onModelChange={setModel}
          onOpenSettings={() => setSettings(true)}
          onToggleArtifacts={() => setMobileArtifacts(!ui.showMobileArtifacts)}
          hasArtifacts={artifacts.length > 0}
        />

        {renderContent()}

        {ui.showSettings ? (
          <SettingsDialog
            open={ui.showSettings}
            onOpenChange={setSettings}
            selectedModel={ui.selectedModel}
            onModelChange={setModel}
          />
        ) : null}

        {/* Chat overlays - only in dashboard view */}
        {ui.currentView === 'dashboard' && (
          <>
            <ScrollToBottomButton
              visible={ui.showScrollButton}
              onClick={scrollToBottom}
            />

            <InterruptBanner
              pendingInterrupt={pendingInterrupt}
              isLoading={isLoading}
              onApprove={handleApproveInterrupt}
              onDismiss={() => setPendingInterrupt(null)}
            />
          </>
        )}

        {/* Input area */}
        {ui.currentView === 'dashboard' && (
          <ChatInput
            input={input}
            setInput={setInput}
            attachments={attachments}
            setAttachments={setAttachments}
            onSubmit={handleSubmit}
            isLoading={isLoading}
            onStop={handleStop}
            searchMode={ui.searchMode}
            setSearchMode={setSearchMode}
          />
        )}

        {/* Accessibility: live region for status updates */}
        <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
          {currentStatus}
        </div>
      </div>

      {/* Desktop Artifacts Panel */}
      {artifacts.length > 0 && (
        <div className={cn(
          "border-l hidden xl:flex flex-col bg-card animate-in slide-in-from-right duration-500 shadow-2xl z-20 transition-all",
          ui.isArtifactsOpen ? "w-[400px]" : "w-[50px]"
        )}>
          <ChatErrorBoundary
            onError={(error, errorInfo) => {
              console.error('[ArtifactsPanel] Render crash:', {
                component: 'ArtifactsPanel',
                error: error.message,
                stack: errorInfo.componentStack,
                timestamp: new Date().toISOString(),
              })
            }}
          >
            <ArtifactsPanel
              artifacts={artifacts}
              isOpen={ui.isArtifactsOpen}
              onToggle={toggleArtifacts}
            />
          </ChatErrorBoundary>
        </div>
      )}

      {/* Browser Viewer */}
      {ui.currentView === 'dashboard' && threadId && (
        <>
          <Button
            variant="outline"
            size="icon"
            className={cn(
              "fixed z-50 rounded-full shadow-lg bg-background",
              "bottom-32 right-6", // Desktop
              "max-xl:bottom-24 max-xl:right-4" // Adjust for smaller screens
            )}
            onClick={() => setBrowserViewer(!ui.showBrowserViewer)}
            aria-label={ui.showBrowserViewer ? 'Hide browser' : 'Show browser'}
          >
            <Monitor className={cn("h-4 w-4", ui.showBrowserViewer && "text-primary")} />
          </Button>

          {ui.showBrowserViewer && (
            <div className={cn(
              "z-40",
              // Desktop: fixed position
              "xl:fixed xl:bottom-48 xl:right-6",
              // Mobile/Tablet: sticky at bottom, full width
              "max-xl:fixed max-xl:bottom-0 max-xl:left-0 max-xl:right-0 max-xl:max-h-[50vh]"
            )}>
              <ChatErrorBoundary
                onError={(error, errorInfo) => {
                  console.error('[BrowserViewer] Render crash:', {
                    component: 'BrowserViewer',
                    error: error.message,
                    stack: errorInfo.componentStack,
                    timestamp: new Date().toISOString(),
                  })
                }}
              >
                <BrowserViewer
                  threadId={threadId}
                  className={cn(
                    "shadow-2xl",
                    "max-xl:rounded-b-none max-xl:w-full"
                  )}
                  defaultExpanded={true}
                  alwaysShow={true}
                  onClose={() => setBrowserViewer(false)}
                />
              </ChatErrorBoundary>
            </div>
          )}
        </>
      )}

      {/* Mobile Artifacts Overlay */}
      <MobileArtifactsOverlay
        show={ui.showMobileArtifacts}
        artifacts={artifacts}
        onClose={() => setMobileArtifacts(false)}
      />
    </div>
  )
}
