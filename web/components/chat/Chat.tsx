'use client'

import React, { useRef, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageItem } from './MessageItem'
import { ArtifactsPanel, Artifact } from './ArtifactsPanel'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { EmptyState } from './EmptyState'
import { Send, Loader2, StopCircle } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  toolInvocations?: any[]
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  
  // UI State
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedModel, setSelectedModel] = useState('gpt-4o')
  const [searchMode, setSearchMode] = useState('agent') // 'web', 'agent', 'deep'
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollTop
    }
  }, [messages, currentStatus])

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsLoading(false)
      setCurrentStatus('Stopped by user')
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
    <div className="flex h-screen w-full overflow-hidden bg-background">
      {/* Sidebar */}
      <Sidebar 
        isOpen={sidebarOpen} 
        onToggle={() => setSidebarOpen(!sidebarOpen)} 
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 transition-all duration-300 ease-in-out">
        {/* Header */}
        <Header 
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
        />

        {/* Chat Area */}
        <ScrollArea className="flex-1 p-4" ref={scrollRef}>
          {messages.length === 0 ? (
            <EmptyState 
              selectedMode={searchMode}
              onModeSelect={setSearchMode}
            />
          ) : (
            <div className="max-w-3xl mx-auto space-y-4 pb-4">
              {messages.map((message) => (
                <MessageItem key={message.id} message={message} />
              ))}
              
              {/* Status indicator inline */}
              {currentStatus && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground p-2 animate-pulse">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>{currentStatus}</span>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* Input Area */}
        <div className="border-t p-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="max-w-3xl mx-auto">
            <form onSubmit={handleSubmit} className="relative flex items-center">
               <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={`Ask in ${searchMode} mode...`}
                disabled={isLoading}
                className="flex-1 pr-12 py-6 text-base rounded-xl shadow-sm"
              />
              <div className="absolute right-2 flex items-center">
                {isLoading ? (
                  <Button 
                    type="button" 
                    size="icon" 
                    variant="ghost" 
                    onClick={handleStop}
                    className="h-8 w-8 hover:bg-destructive/10 hover:text-destructive"
                  >
                    <StopCircle className="h-5 w-5" />
                  </Button>
                ) : (
                  <Button 
                    type="submit" 
                    size="icon" 
                    disabled={!input.trim()}
                    className="h-8 w-8 rounded-lg"
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </form>
            <div className="text-xs text-muted-foreground text-center mt-2">
              Using {selectedModel} • {searchMode === 'deep' ? 'Deep Research' : searchMode === 'web' ? 'Web Search' : 'Agent'} Mode
            </div>
          </div>
        </div>
      </div>

      {/* Artifacts Panel - Collapsible or Overlay on mobile */}
      {artifacts.length > 0 && (
        <div className="w-[400px] border-l hidden xl:block bg-card">
          <ArtifactsPanel artifacts={artifacts} />
        </div>
      )}
    </div>
  )
}