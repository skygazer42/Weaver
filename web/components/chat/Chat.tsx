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
import { Message, Artifact, ChatSession, ToolInvocation } from '@/types/chat'
import { STORAGE_KEYS, DEFAULT_MODEL, SEARCH_MODES } from '@/lib/constants'
import { useChatHistory } from '@/hooks/useChatHistory'

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  
  const { history, setHistory, isHistoryLoading, saveToHistory } = useChatHistory()
  
  // UI State
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL)
  const [searchMode, setSearchMode] = useState(SEARCH_MODES.AGENT) 
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [showMobileArtifacts, setShowMobileArtifacts] = useState(false)
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

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

  // Auto-scroll
  useEffect(() => {
    // Virtuoso handles followOutput, but sometimes we want to force it
  }, [messages])

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsLoading(false)
      setCurrentStatus('Stopped by user')
    }
  }

  const handleNewChat = () => {
      saveToHistory(messages)
      
      // Reset state
      setMessages([])
      setArtifacts([])
      setCurrentStatus('')
      setInput('')
      if (abortControllerRef.current) {
          abortControllerRef.current.abort()
      }
  }

  const processChat = async (messageHistory: Message[]) => {
    setIsLoading(true)
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            messages: messageHistory.map(m => ({ role: m.role, content: m.content })),
            stream: true,
            model: selectedModel,
            search_mode: searchMode
          }),
          signal: abortControllerRef.current.signal
        }
      )

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No reader available')
      }

      let assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: '',
        toolInvocations: [],
      }

      setMessages((prev) => [...prev, assistantMessage])

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter((line) => line.trim())

        for (const line of lines) {
          if (line.startsWith('0:')) {
            try {
              const data = JSON.parse(line.slice(2))

              if (data.type === 'status') {
                setCurrentStatus(data.data.text)
              } else if (data.type === 'text') {
                assistantMessage.content += data.data.content
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'message') {
                assistantMessage.content = data.data.content
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'tool') {
                const toolInvocation: ToolInvocation = {
                  toolCallId: `tool-${Date.now()}-${Math.random()}`,
                  toolName: data.data.name,
                  state: data.data.status === 'completed' ? 'completed' : 'running',
                  args: data.data.query ? { query: data.data.query } : {},
                }

                assistantMessage.toolInvocations = [
                  ...(assistantMessage.toolInvocations || []),
                  toolInvocation,
                ]

                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'completion') {
                assistantMessage.content = data.data.content
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessage.id ? { ...assistantMessage } : msg
                  )
                )
              } else if (data.type === 'artifact') {
                const newArtifact = data.data as Artifact
                setArtifacts((prev) => {
                  if (prev.some(a => a.id === newArtifact.id)) return prev
                  return [...prev, newArtifact]
                })
              }
            } catch (err) {
              console.error('Error parsing stream data:', err)
            }
          }
        }
      }

      setCurrentStatus('')
    } catch (error: any) {
      if (error.name === 'AbortError') {
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
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim(),
    }

    const newHistory = [...messages, userMessage]
    setMessages(newHistory)
    setInput('')
    setAttachments([])
    
    await processChat(newHistory)
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
          await processChat(newHistory)
      }
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground font-sans selection:bg-primary/20">
      {/* Sidebar */}
      <Sidebar 
        isOpen={sidebarOpen} 
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNewChat={handleNewChat}
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

        {/* Chat Area */}
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

        {/* Scroll To Bottom Button */}
        <div className={cn("absolute bottom-24 right-6 z-30 transition-all duration-500", showScrollButton ? "translate-y-0 opacity-100" : "translate-y-10 opacity-0 pointer-events-none")}>
             <Button variant="outline" size="icon" className="rounded-full shadow-lg bg-background/80 backdrop-blur border-primary/20 hover:bg-background" onClick={() => scrollToBottom()}>
                 <ArrowDown className="h-4 w-4" />
             </Button>
        </div>

        {/* Input Area */}
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
