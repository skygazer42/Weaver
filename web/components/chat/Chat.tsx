'use client'

import React, { useRef, useEffect, useState } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { MessageItem } from './MessageItem'
import { ArtifactsPanel } from './ArtifactsPanel'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { EmptyState } from './EmptyState'
import { ChatInput } from './ChatInput'
import { Loader2, ArrowDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Message } from '@/types/chat'
import { STORAGE_KEYS, DEFAULT_MODEL, SEARCH_MODES } from '@/lib/constants'
import { useChatHistory } from '@/hooks/useChatHistory'
import { useChatStream } from '@/hooks/useChatStream'
import { filesToImageAttachments } from '@/lib/file-utils'
import { Discover } from '@/components/views/Discover'
import { Library } from '@/components/views/Library'

export function Chat() {
  // UI State
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL)
  const [searchMode, setSearchMode] = useState(SEARCH_MODES.AGENT) 
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [showMobileArtifacts, setShowMobileArtifacts] = useState(false)
  
  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard' | 'discover' | 'library'

  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtuosoRef = useRef<VirtuosoHandle>(null)

  const { history, isHistoryLoading, saveToHistory, loadSession } = useChatHistory()
  
  const {
    messages,
    setMessages,
    isLoading,
    setIsLoading, // Exposed but maybe not needed directly if handleStop covers it
    currentStatus,
    setCurrentStatus,
    artifacts,
    setArtifacts,
    pendingInterrupt,
    setPendingInterrupt,
    setThreadId,
    processChat,
    handleStop,
    handleApproveInterrupt
  } = useChatStream({ selectedModel, searchMode })

  // Load Model from LocalStorage
  useEffect(() => {
      const savedModel = localStorage.getItem(STORAGE_KEYS.MODEL)
      if (savedModel) {
          setSelectedModel(savedModel)
      }
  }, [])

  // Save Model to LocalStorage
  useEffect(() => {
      localStorage.setItem(STORAGE_KEYS.MODEL, selectedModel)
  }, [selectedModel])

  const scrollToBottom = (behavior: 'auto' | 'smooth' = 'smooth') => {
      virtuosoRef.current?.scrollToIndex({ index: messages.length - 1, behavior })
  }

  // Auto-scroll logic handled by Virtuoso's followOutput, 
  // but we can add specific triggers if needed.

  const handleNewChat = () => {
      if (messages.length > 0) {
        saveToHistory(messages)
      }
      
      setCurrentView('dashboard') // Switch back to chat view
      
      // Reset state
      setMessages([])
      setArtifacts([])
      setCurrentStatus('')
      setInput('')
      setThreadId(null)
      setPendingInterrupt(null)
      handleStop() // Abort any ongoing request
  }

  const handleChatSelect = (id: string) => {
    // Save current chat if not empty and not already saved (simple check for now)
    // For a real app, we'd check if the current session ID matches
    
    // Load new session
    const loadedMessages = loadSession(id)
    if (loadedMessages) {
      setMessages(loadedMessages)
      setCurrentView('dashboard') // Ensure we are on the chat view
      // Reset other state
      setArtifacts([]) // Artifacts might need to be saved/loaded too if we want them back
      setCurrentStatus('')
      setInput('')
      setThreadId(null)
      setPendingInterrupt(null)
      handleStop()
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
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
    
    await processChat(newHistory, imagePayloads)
  }

  const handleEditMessage = async (id: string, newContent: string) => {
      const index = messages.findIndex(m => m.id === id)
      if (index === -1) return

      const previousMessages = messages.slice(0, index)
      const updatedMessage: Message = {
          ...messages[index],
          content: newContent
      }
      
      const newHistory = [...previousMessages, updatedMessage]
      setMessages(newHistory)
      
      if (updatedMessage.role === 'user') {
          await processChat(newHistory, updatedMessage.attachments)
      }
  }
  
  // Render Content based on View
  const renderContent = () => {
      if (currentView === 'discover') return <Discover />
      if (currentView === 'library') return <Library />
      
      // Default: Dashboard/Chat
      return (
        <div className="flex-1 flex flex-col min-h-0">
          {messages.length === 0 ? (
            <div className="h-full w-full p-4 overflow-y-auto">
               <EmptyState 
                  selectedMode={searchMode}
                  onModeSelect={setSearchMode}
               />
            </div>
          ) : (
            <Virtuoso
                ref={virtuosoRef}
                data={messages}
                followOutput="auto"
                atBottomStateChange={(atBottom) => setShowScrollButton(!atBottom)}
                className="scrollbar-thin scrollbar-thumb-muted/20"
                itemContent={(index, message) => (
                    <div className="max-w-3xl mx-auto px-4 sm:px-0">
                        <MessageItem key={message.id} message={message} onEdit={handleEditMessage} />
                    </div>
                )}
                components={{
                    Footer: () => (
                        <div className="max-w-3xl mx-auto px-4 sm:px-0 pb-4">
                            {currentStatus && (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground py-2 animate-in fade-in slide-in-from-bottom-2">
                                    <Loader2 className="h-3 w-3 animate-spin text-primary" />
                                    <span className="font-medium animate-pulse">{currentStatus}</span>
                                </div>
                            )}
                            <div className="h-4" /> 
                        </div>
                    )
                }}
            />
          )}
        </div>
      )
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground font-sans selection:bg-primary/20">
      {/* Sidebar */}
      <Sidebar 
        isOpen={sidebarOpen} 
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNewChat={handleNewChat}
        onSelectChat={handleChatSelect}
        activeView={currentView}
        onViewChange={setCurrentView}
        history={history}
        isLoading={isHistoryLoading}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Header */}
        <Header 
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onToggleArtifacts={() => setShowMobileArtifacts(!showMobileArtifacts)}
          hasArtifacts={artifacts.length > 0}
        />

        {/* Dynamic Content Area */}
        {renderContent()}

        {/* Chat-specific overlays (Scroll button, Interrupts) - only show in dashboard view */}
        {currentView === 'dashboard' && (
           <>
                {/* Scroll To Bottom Button */}
                <div className={cn("absolute bottom-24 right-6 z-30 transition-all duration-500", showScrollButton ? "translate-y-0 opacity-100" : "translate-y-10 opacity-0 pointer-events-none")}>
                    <Button variant="outline" size="icon" className="rounded-full shadow-lg bg-background/80 backdrop-blur border-primary/20 hover:bg-background" onClick={() => scrollToBottom()}>
                        <ArrowDown className="h-4 w-4" />
                    </Button>
                </div>

                {pendingInterrupt && (
                <div className="mx-4 mb-3 p-3 border rounded-xl bg-amber-50 text-amber-900 shadow-sm flex flex-col gap-2">
                    <div className="text-sm font-semibold">Tool approval required</div>
                    <div className="text-xs text-amber-800">
                    {pendingInterrupt.message || pendingInterrupt?.prompts?.[0]?.message || 'Approve tool execution to continue.'}
                    </div>
                    <div className="flex gap-2">
                    <Button size="sm" onClick={handleApproveInterrupt} disabled={isLoading}>
                        Approve & Continue
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setPendingInterrupt(null)} disabled={isLoading}>
                        Dismiss
                    </Button>
                    </div>
                </div>
                )}
           </>
        )}

        {/* Input Area - Always visible or only in dashboard? Usually always visible in chat apps, but maybe hidden in Library? 
            For now, let's keep it visible only in Dashboard/Chat view to avoid confusion.
        */}
        {currentView === 'dashboard' && (
            <ChatInput 
            input={input}
            setInput={setInput}
            attachments={attachments}
            setAttachments={setAttachments}
            onSubmit={handleSubmit}
            isLoading={isLoading}
            onStop={handleStop}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
            />
        )}
      </div>

      {/* Desktop Artifacts Panel */}
      {artifacts.length > 0 && (
        <div className="w-[400px] border-l hidden xl:flex flex-col bg-card animate-in slide-in-from-right duration-500 shadow-2xl z-20">
          <ArtifactsPanel artifacts={artifacts} />
        </div>
      )}

      {/* Mobile Artifacts Overlay */}
      {showMobileArtifacts && (
         <div className="fixed inset-0 z-50 bg-background xl:hidden flex flex-col animate-in slide-in-from-right duration-300">
             <div className="flex items-center justify-between p-4 border-b">
                 <h2 className="font-semibold">Artifacts</h2>
                 <Button variant="ghost" size="icon" onClick={() => setShowMobileArtifacts(false)}>
                     <X className="h-5 w-5" />
                 </Button>
             </div>
             <div className="flex-1 overflow-hidden">
                 <ArtifactsPanel artifacts={artifacts} />
             </div>
         </div>
      )}
    </div>
  )
}