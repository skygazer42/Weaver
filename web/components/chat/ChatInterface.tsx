'use client'

import React, { useRef, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageItem } from './MessageItem'
import { SearchModeSelector, SearchMode } from './SearchModeSelector'
import { Send, Loader2, Sparkles } from 'lucide-react'
import { getApiBaseUrl } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  toolInvocations?: any[]
}

interface ChatInterfaceProps {
  selectedModel: string
}

export function ChatInterface({ selectedModel }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [searchMode, setSearchMode] = useState<SearchMode>({
    useWebSearch: false,
    useAgent: false,
    useDeepSearch: false,
  })
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

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

    try {
      const response = await fetch(
        `${getApiBaseUrl()}/api/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            messages: [{ role: 'user', content: userMessage.content }],
            stream: true,
            model: selectedModel,
            search_mode: searchMode,
          }),
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
              }
            } catch (err) {
              console.error('Error parsing stream data:', err)
            }
          }
        }
      }

      setCurrentStatus('')
    } catch (error) {
      console.error('Error:', error)
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, an error occurred. Please try again.',
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Messages Area */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-2xl text-center space-y-4">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
                  <Sparkles className="h-8 w-8 text-primary" />
                </div>
              </div>
              <h2 className="text-2xl font-semibold">
                欢迎使用 Weaver AI
              </h2>
              <p className="text-muted-foreground">
                我是你的 AI 研究助手，可以进行深度搜索、代码执行和生成式 UI。
                试试问我一些问题吧！
              </p>
              <div className="grid gap-2 sm:grid-cols-2 text-left mt-6">
                <div className="rounded-lg border p-4 hover:border-primary cursor-pointer transition-colors">
	                  <div className="font-medium mb-1">💡 研究问题</div>
	                  <div className="text-sm text-muted-foreground">
	                    &quot;分析 2024 年最流行的 AI 框架&quot;
	                  </div>
	                </div>
	                <div className="rounded-lg border p-4 hover:border-primary cursor-pointer transition-colors">
	                  <div className="font-medium mb-1">📊 数据分析</div>
	                  <div className="text-sm text-muted-foreground">
	                    &quot;创建一个市场份额对比图表&quot;
	                  </div>
	                </div>
	                <div className="rounded-lg border p-4 hover:border-primary cursor-pointer transition-colors">
	                  <div className="font-medium mb-1">🔍 深度调研</div>
	                  <div className="text-sm text-muted-foreground">
	                    &quot;对比 Python 和 JavaScript 的优缺点&quot;
	                  </div>
	                </div>
	                <div className="rounded-lg border p-4 hover:border-primary cursor-pointer transition-colors">
	                  <div className="font-medium mb-1">💻 代码执行</div>
	                  <div className="text-sm text-muted-foreground">
	                    &quot;用 Python 生成斐波那契数列&quot;
	                  </div>
	                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.map((message) => (
              <MessageItem key={message.id} message={message} />
            ))}
          </div>
        )}

        {/* Status indicator */}
        {currentStatus && (
          <div className="mx-auto max-w-3xl mt-4 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{currentStatus}</span>
          </div>
        )}
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t bg-background p-4">
        <div className="mx-auto max-w-3xl space-y-3">
          {/* Search Mode Selector */}
          <div className="flex items-center gap-2">
            <SearchModeSelector mode={searchMode} onChange={setSearchMode} />

            {/* Active Modes Display */}
            {(searchMode.useWebSearch || searchMode.useAgent || searchMode.useDeepSearch) && (
              <div className="flex gap-2 text-xs">
                {searchMode.useWebSearch && (
                  <span className="rounded-full bg-primary/10 px-2 py-1 text-primary">
                    网络搜索
                  </span>
                )}
                {searchMode.useAgent && (
                  <span className="rounded-full bg-primary/10 px-2 py-1 text-primary">
                    Agent
                  </span>
                )}
                {searchMode.useDeepSearch && (
                  <span className="rounded-full bg-amber-500/10 px-2 py-1 text-amber-600">
                    深度搜索
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Input Form */}
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="发送消息..."
              disabled={isLoading}
              className="flex-1"
            />
            <Button type="submit" disabled={isLoading || !input.trim()}>
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>

          {/* Footer Info */}
          <div className="text-center text-xs text-muted-foreground">
            使用模型: <span className="font-medium">{selectedModel}</span>
            {' · '}
            <span>Weaver AI 可能会出错，请验证重要信息</span>
          </div>
        </div>
      </div>
    </div>
  )
}
