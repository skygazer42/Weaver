'use client'

import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/card'
import { Search, Code, Loader2, ChevronDown, Check, Copy, Terminal, Bot } from 'lucide-react'
import { Button } from '@/components/ui/button'

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
  const [isThinkingOpen, setIsThinkingOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Filter tools to group them as "Thinking Process"
  const tools = message.toolInvocations || []
  const hasTools = tools.length > 0

  return (
    <div
      className={cn(
        'group flex w-full gap-4 py-6 animate-in fade-in slide-in-from-bottom-2 duration-500',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div className={cn('flex flex-col max-w-[85%] md:max-w-[75%]', isUser ? 'items-end' : 'items-start')}>
        
        {/* Avatar / Role Label */}
        <div className={cn("flex items-center gap-2 mb-2 select-none", isUser ? "flex-row-reverse" : "flex-row")}>
            <div className={cn(
                "flex h-8 w-8 items-center justify-center rounded-xl text-xs font-bold shadow-sm ring-1 ring-inset",
                isUser 
                  ? "bg-primary text-primary-foreground ring-primary/20" 
                  : "bg-muted text-foreground ring-border"
            )}>
                {isUser ? 'You' : <Bot className="h-5 w-5" />}
            </div>
            <span className="text-xs text-muted-foreground font-medium">
                {isUser ? 'User' : 'Manus'}
            </span>
        </div>

        {/* Thinking Process (Collapsible) - Only for Assistant */}
        {!isUser && hasTools && (
          <div className="w-full mb-3">
             <button 
                onClick={() => setIsThinkingOpen(!isThinkingOpen)}
                className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors bg-muted/30 hover:bg-muted/50 px-3 py-2 rounded-lg w-full md:w-auto"
             >
                {isThinkingOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5 -rotate-90" />}
                <span>Thinking Process</span>
                <span className="bg-muted px-1.5 py-0.5 rounded-full text-[10px]">{tools.length} steps</span>
             </button>

             {isThinkingOpen && (
                <div className="mt-2 pl-4 border-l-2 border-muted space-y-3 py-2">
                    {tools.map((tool) => (
                        <ToolInvocationItem key={tool.toolCallId} tool={tool} />
                    ))}
                </div>
             )}
          </div>
        )}

        {/* Message Content */}
        <div className={cn(
            "relative px-5 py-4 rounded-2xl shadow-sm ring-1 ring-inset",
            isUser
              ? "bg-primary text-primary-foreground ring-primary/20 rounded-tr-sm"
              : "bg-card text-card-foreground ring-border rounded-tl-sm"
          )}
        >
          {/* Markdown Content */}
          <div className="prose prose-sm dark:prose-invert max-w-none break-words leading-relaxed">
            <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                    pre: ({node, ...props}) => <div className="overflow-auto w-full my-2 bg-muted/50 p-2 rounded-lg" {...props} />,
                    code: ({node, ...props}) => <code className="bg-muted/50 px-1 py-0.5 rounded text-sm font-mono" {...props} />
                }}
            >
              {message.content || (hasTools ? "..." : "")}
            </ReactMarkdown>
          </div>

          {/* Copy Action (Hover) */}
          {!isUser && message.content && (
            <div className="absolute -bottom-6 right-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                    onClick={handleCopy}
                >
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ToolInvocationItem({ tool }: { tool: ToolInvocation }) {
  const getIcon = () => {
    if (tool.toolName.includes('search')) return <Search className="h-3.5 w-3.5" />
    if (tool.toolName.includes('code')) return <Code className="h-3.5 w-3.5" />
    return <Terminal className="h-3.5 w-3.5" />
  }

  const isComplete = tool.state === 'completed'
  const isRunning = tool.state === 'running'

  return (
    <div className="flex items-start gap-3 text-sm group">
      <div className={cn(
          "mt-0.5 flex h-5 w-5 items-center justify-center rounded bg-background border shadow-sm",
          isRunning ? "text-blue-500" : "text-muted-foreground"
      )}>
         {isRunning ? <Loader2 className="h-3 w-3 animate-spin" /> : getIcon()}
      </div>
      
      <div className="flex-1 space-y-1">
        <div className="flex items-center justify-between">
            <span className={cn("font-medium text-xs", isRunning ? "text-foreground" : "text-muted-foreground")}>
                {tool.toolName === 'tavily_search' && 'Searching Web'}
                {tool.toolName === 'execute_python_code' && 'Executing Python'}
                {!tool.toolName.includes('search') && !tool.toolName.includes('code') && tool.toolName}
            </span>
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                {tool.state}
            </span>
        </div>
        
        {/* Tool Arguments (Collapsed preview) */}
        {tool.args?.query && (
          <div className="text-xs text-muted-foreground font-mono bg-muted/30 px-2 py-1 rounded w-fit max-w-[200px] truncate">
            "{tool.args.query}"
          </div>
        )}
        
        {/* Code Preview (if applicable) */}
        {tool.toolName.includes('code') && tool.args?.code && (
           <div className="mt-1">
              <div className="text-[10px] bg-muted/50 p-2 rounded font-mono overflow-hidden max-h-20 opacity-70 group-hover:opacity-100 transition-opacity">
                 {tool.args.code.slice(0, 100)}...
              </div>
           </div>
        )}
      </div>
    </div>
  )
}