'use client'

import React, { useState } from 'react'
import { ChevronDown, Loader2, BrainCircuit, Globe, Code, PenTool, Terminal, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ToolInvocation } from '@/types/chat'

interface ThinkingProcessProps {
  tools: ToolInvocation[]
  isThinking: boolean
}

export function ThinkingProcess({ tools, isThinking }: ThinkingProcessProps) {
  const [isOpen, setIsOpen] = useState(false)

  if (!tools || tools.length === 0) return null

  return (
    <div className="mb-2 ml-1 w-full max-w-md">
      {/* Graph Visualization (Mini) */}
      <div className="flex items-center gap-2 mb-2 px-2 py-1 overflow-hidden">
        <ThinkingNode 
            icon={BrainCircuit} 
            label="Plan" 
            active={tools.length > 0} 
            completed={tools.length > 1} 
        />
        <ThinkingLine active={tools.length > 1} />
        <ThinkingNode 
            icon={Globe} 
            label="Search" 
            active={tools.some(t => t.toolName.includes('search'))} 
            completed={tools.some(t => t.toolName.includes('search') && t.state === 'completed')} 
        />
        <ThinkingLine active={tools.some(t => t.toolName.includes('code'))} />
        <ThinkingNode 
            icon={Code} 
            label="Code" 
            active={tools.some(t => t.toolName.includes('code'))} 
            completed={tools.some(t => t.toolName.includes('code') && t.state === 'completed')} 
        />
        <ThinkingLine active={!isThinking && tools.length > 0} />
        <ThinkingNode 
            icon={PenTool} 
            label="Write" 
            active={!isThinking && tools.length > 0} 
            completed={!isThinking} // Assuming write is done when not thinking
        />
      </div>

      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors bg-muted/30 hover:bg-muted/50 px-2.5 py-1.5 rounded-full border border-border/50"
      >
        {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronDown className="h-3 w-3 -rotate-90" />}
        <span>Process Logs</span>
        {isThinking && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
      </button>

      {isOpen && (
        <div className="mt-2 pl-2 space-y-2 py-1 border-l-2 border-muted ml-2">
            {tools.map((tool) => (
                <ToolInvocationItem key={tool.toolCallId} tool={tool} />
            ))}
        </div>
      )}
    </div>
  )
}

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
