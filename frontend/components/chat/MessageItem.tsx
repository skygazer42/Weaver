'use client'

import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/card'
import { Search, Code, Loader2 } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  toolInvocations?: ToolInvocation[]
}

interface ToolInvocation {
  toolName: string
  toolCallId: string
  state: 'running' | 'completed' | 'failed'
  args?: any
  result?: any
}

export function MessageItem({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex w-full gap-4 py-4',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div className={cn('max-w-[80%]', isUser && 'order-2')}>
        {/* Avatar */}
        <div
          className={cn(
            'mb-2 flex items-center gap-2',
            isUser && 'justify-end'
          )}
        >
          <div
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold',
              isUser
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground'
            )}
          >
            {isUser ? 'U' : 'AI'}
          </div>
          <span className="text-sm text-muted-foreground">
            {isUser ? 'You' : 'Assistant'}
          </span>
        </div>

        {/* Message content */}
        <Card
          className={cn(
            'p-4',
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-card text-card-foreground'
          )}
        >
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        </Card>

        {/* Tool invocations */}
        {message.toolInvocations && message.toolInvocations.length > 0 && (
          <div className="mt-2 space-y-2">
            {message.toolInvocations.map((tool) => (
              <ToolInvocationCard key={tool.toolCallId} tool={tool} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ToolInvocationCard({ tool }: { tool: ToolInvocation }) {
  const getIcon = () => {
    if (tool.toolName.includes('search')) {
      return <Search className="h-4 w-4" />
    }
    if (tool.toolName.includes('code')) {
      return <Code className="h-4 w-4" />
    }
    return null
  }

  const getStatusColor = () => {
    switch (tool.state) {
      case 'running':
        return 'bg-blue-500/10 text-blue-500 border-blue-500/20'
      case 'completed':
        return 'bg-green-500/10 text-green-500 border-green-500/20'
      case 'failed':
        return 'bg-red-500/10 text-red-500 border-red-500/20'
      default:
        return 'bg-muted text-muted-foreground'
    }
  }

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3',
        getStatusColor()
      )}
    >
      <div className="mt-0.5">{getIcon()}</div>
      <div className="flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            {tool.toolName === 'tavily_search' && 'Searching'}
            {tool.toolName === 'execute_python_code' && 'Executing code'}
            {!tool.toolName.includes('search') &&
              !tool.toolName.includes('code') &&
              tool.toolName}
          </span>
          {tool.state === 'running' && (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
        </div>
        {tool.args?.query && (
          <p className="text-xs opacity-70">Query: {tool.args.query}</p>
        )}
        {tool.state === 'completed' && tool.result && (
          <div className="mt-2 text-xs opacity-70">
            {typeof tool.result === 'string'
              ? tool.result.slice(0, 100)
              : 'Completed'}
          </div>
        )}
      </div>
    </div>
  )
}
