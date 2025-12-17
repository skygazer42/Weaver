'use client'

import React, { useRef, useEffect, useState } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageItem } from './MessageItem'
import { ArtifactsPanel, Artifact } from './ArtifactsPanel'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { EmptyState } from './EmptyState'
import { ChatInput } from './ChatInput'
import { Loader2, ArrowDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  toolInvocations?: any[]
}

interface ChatSession {
    id: string
    title: string
    date: string
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [history, setHistory] = useState<ChatSession[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)
  
  // UI State
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedModel, setSelectedModel] = useState('gpt-4o')
  const [searchMode, setSearchMode] = useState('agent') 
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [showMobileArtifacts, setShowMobileArtifacts] = useState(false)
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Load History and Model from LocalStorage
  useEffect(() => {
      const savedHistory = localStorage.getItem('weaver-history')
      if (savedHistory) {
          try {
              setHistory(JSON.parse(savedHistory))
          } catch (e) {
              console.error('Failed to parse history', e)
          }
      } else {
          // Default data for demo
          setHistory([
             { id: '1', title: 'Market Analysis 2024', date: 'Today' },
             { id: '2', title: 'Python Viz Script', date: 'Yesterday' }
          ])
      }

      const savedModel = localStorage.getItem('weaver-model')
      if (savedModel) {
          setSelectedModel(savedModel)
      }

      setIsHistoryLoading(false)
  }, [])

  // Save History to LocalStorage
  useEffect(() => {
      if (!isHistoryLoading) {
        localStorage.setItem('weaver-history', JSON.stringify(history))
      }
  }, [history, isHistoryLoading])

  // Save Model to LocalStorage
  useEffect(() => {
      localStorage.setItem('weaver-model', selectedModel)
  }, [selectedModel])

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
      if (scrollRef.current) {
          const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]') as HTMLElement
          if (viewport) {
               viewport.scrollTo({ top: viewport.scrollHeight, behavior })
          }
      }
  }

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
      const target = e.currentTarget
      const diff = target.scrollHeight - target.scrollTop - target.clientHeight
      setShowScrollButton(diff > 200) // Show if more than 200px from bottom
  }

  // Auto-scroll
  useEffect(() => {
    setTimeout(() => {
        scrollToBottom('instant')
    }, 100)
  }, [messages, currentStatus])

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsLoading(false)
      setCurrentStatus('Stopped by user')
    }
  }

  const handleNewChat = () => {
      // If current chat has messages, save it to history
      if (messages.length > 0) {
          const firstUserMsg = messages.find(m => m.role === 'user')
          const title = firstUserMsg ? firstUserMsg.content.slice(0, 30) : 'New Conversation'
          
          const newSession: ChatSession = {
              id: Date.now().toString(),
              title: title,
              date: 'Just now'
          }
          setHistory(prev => [newSession, ...prev])
      }
      
      // Reset state
      setMessages([])
      setArtifacts([])
      setCurrentStatus('')
      setInput('')
      if (abortControllerRef.current) {
          abortControllerRef.current.abort()
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

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setAttachments([])
    setIsLoading(true)

    // Create new abort controller
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
            messages: [{ role: 'user', content: userMessage.content }],
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
                const toolInvocation = {
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
        <ScrollArea 
            className="flex-1 p-0 sm:p-4" 
            ref={scrollRef}
            onViewportScroll={handleScroll}
        >
          {messages.length === 0 ? (
            <div className="h-full w-full p-4">
               <EmptyState 
                  selectedMode={searchMode}
                  onModeSelect={setSearchMode}
               />
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-8 pb-8 px-4 sm:px-0 pt-6">
              {messages.map((message) => (
                <MessageItem key={message.id} message={message} />
              ))}
              
              {/* Status indicator inline */}
              {currentStatus && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground p-2 animate-in fade-in slide-in-from-bottom-2">
                  <Loader2 className="h-3 w-3 animate-spin text-primary" />
                  <span className="font-medium animate-pulse">{currentStatus}</span>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

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
