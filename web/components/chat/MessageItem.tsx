'use client'

import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import { Search, Code, Loader2, ChevronDown, Check, Copy, Terminal, Bot, User, BrainCircuit, PenTool, Globe } from 'lucide-react'
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
  const isThinking = tools.some(t => t.state === 'running')

  return (
    <div
      className={cn(
        'group flex w-full gap-2 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      {/* Bot Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 mt-1">
             <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/50 border shadow-sm">
                <Bot className="h-4 w-4 text-primary" />
             </div>
        </div>
      )}

      <div className={cn(
          'flex flex-col max-w-[85%] md:max-w-[75%]', 
          isUser ? 'items-end' : 'items-start'
      )}>
        
        {/* Thinking Process Graph / Accordion */}
        {!isUser && hasTools && (
          <div className="mb-2 ml-1 w-full max-w-md">
             {/* Graph Visualization (Mini) */}
             <div className="flex items-center gap-2 mb-2 px-2 py-1 overflow-hidden">
                <ThinkingNode icon={BrainCircuit} label="Plan" active={tools.length > 0} completed={tools.length > 1} />
                <ThinkingLine active={tools.length > 1} />
                <ThinkingNode icon={Globe} label="Search" active={tools.some(t => t.toolName.includes('search'))} completed={tools.some(t => t.toolName.includes('search') && t.state === 'completed')} />
                <ThinkingLine active={tools.some(t => t.toolName.includes('code'))} />
                <ThinkingNode icon={Code} label="Code" active={tools.some(t => t.toolName.includes('code'))} completed={tools.some(t => t.toolName.includes('code') && t.state === 'completed')} />
                <ThinkingLine active={!isThinking && tools.length > 0} />
                <ThinkingNode icon={PenTool} label="Write" active={!isThinking && tools.length > 0} completed={!isThinking && message.content.length > 0} />
             </div>

             <button 
                onClick={() => setIsThinkingOpen(!isThinkingOpen)}
                className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors bg-muted/30 hover:bg-muted/50 px-2.5 py-1.5 rounded-full border border-border/50"
             >
                {isThinkingOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronDown className="h-3 w-3 -rotate-90" />}
                <span>Process Logs</span>
                {isThinking && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
             </button>

             {isThinkingOpen && (
                <div className="mt-2 pl-2 space-y-2 py-1 border-l-2 border-muted ml-2">
                    {tools.map((tool) => (
                        <ToolInvocationItem key={tool.toolCallId} tool={tool} />
                    ))}
                </div>
             )}
          </div>
        )}

        {/* Message Bubble */}
        <div className={cn(
            "relative px-4 py-3 shadow-sm",
            isUser
              ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
              : "bg-muted/30 border text-foreground rounded-2xl rounded-tl-sm backdrop-blur-sm"
          )}
        >
          <div className={cn(
              "prose prose-sm max-w-none break-words leading-relaxed",
              isUser ? "prose-invert" : "dark:prose-invert"
          )}>
            <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                    pre: ({node, ...props}) => (
                        <div className="overflow-auto w-full my-2 bg-black/10 dark:bg-black/30 p-2 rounded-lg border border-black/5 dark:border-white/5" {...props} />
                    ),
                    code: ({node, ...props}) => (
                        <code className="bg-black/10 dark:bg-black/30 px-1 py-0.5 rounded text-sm font-mono" {...props} />
                    ),
                    a: ({node, ...props}) => (
                        <a className={cn("underline underline-offset-2 font-medium", isUser ? "text-white" : "text-primary hover:text-primary/80")} {...props} />
                    )
                }}
            >
              {message.content || (hasTools ? "" : "")}
            </ReactMarkdown>
            
            {/* Typing Indicator for AI if no content yet */}
            {!isUser && !message.content && !hasTools && (
               <span className="animate-pulse">...</span>
            )}
          </div>

          {!isUser && message.content && (
            <div className="absolute -bottom-6 left-0 opacity-0 group-hover:opacity-100 transition-opacity">
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

// Graph Components
function ThinkingNode({ icon: Icon, label, active, completed }: { icon: any, label: string, active: boolean, completed: boolean }) {
    return (
        <div className={cn(
            "flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium transition-all duration-300",
            completed ? "bg-primary/10 text-primary ring-1 ring-primary/20" :
            active ? "bg-blue-500/10 text-blue-500 ring-1 ring-blue-500/50 animate-pulse" :
            "bg-muted text-muted-foreground opacity-50"
        )}>
            <Icon className="h-3 w-3" />
            <span>{label}</span>
        </div>
    )
}

function ThinkingLine({ active }: { active: boolean }) {
    return (
        <div className={cn(
            "h-[1px] w-4 transition-colors duration-300",
            active ? "bg-primary/50" : "bg-muted"
        )} />
    )
}

function ToolInvocationItem({ tool }: { tool: ToolInvocation }) {
  const getIcon = () => {
    if (tool.toolName.includes('search')) return <Search className="h-3.5 w-3.5" />
    if (tool.toolName.includes('code')) return <Code className="h-3.5 w-3.5" />
    return <Terminal className="h-3.5 w-3.5" />
  }

  const isRunning = tool.state === 'running'

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground animate-in fade-in slide-in-from-left-1">
      <div className={cn(
          "flex h-4 w-4 items-center justify-center rounded-sm",
          isRunning ? "text-blue-500" : "text-muted-foreground"
      )}>
         {isRunning ? <Loader2 className="h-3 w-3 animate-spin" /> : getIcon()}
      </div>
      <span className="truncate max-w-[200px]">
        {tool.toolName === 'tavily_search' && `Searching: ${tool.args?.query || '...'}`}
        {tool.toolName === 'execute_python_code' && 'Executing Logic...'}
        {!tool.toolName.includes('search') && !tool.toolName.includes('code') && tool.toolName}
      </span>
    </div>
  )
}