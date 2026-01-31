'use client'

import React, { useState, useEffect } from 'react'
import { ChevronDown, Loader2, BrainCircuit, Globe, Code, FileText, CheckCircle2, Circle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ToolInvocation } from '@/types/chat'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'

interface ThinkingProcessProps {
  tools: ToolInvocation[]
  isThinking: boolean
}

export function ThinkingProcess({ tools, isThinking }: ThinkingProcessProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [activeStep, setActiveStep] = useState(0)

  // Determine active phase based on tools
  const hasSearch = tools.some(t => t.toolName.includes('search'))
  const hasCode = tools.some(t => t.toolName.includes('code'))
  const isComplete = !isThinking && tools.length > 0

  useEffect(() => {
      if (isComplete) setActiveStep(3)
      else if (hasCode) setActiveStep(2)
      else if (hasSearch) setActiveStep(1)
      else setActiveStep(0)
  }, [hasSearch, hasCode, isComplete])

  if (!tools || tools.length === 0) return null

  const steps = [
      { label: 'Plan', icon: BrainCircuit },
      { label: 'Search', icon: Globe },
      { label: 'Analyze', icon: Code },
      { label: 'Report', icon: FileText },
  ]

  return (
    <Card className="w-full max-w-md my-3 border-border/60 bg-card/40 backdrop-blur-sm shadow-sm overflow-hidden transition-all duration-300 hover:shadow-md hover:border-border/80">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
         <div className="flex items-center gap-3">
            <div className={cn(
                "flex items-center justify-center w-8 h-8 rounded-full ring-1 ring-border shadow-sm transition-all",
                isThinking ? "bg-primary/10 text-primary ring-primary/20" : "bg-muted text-muted-foreground"
            )}>
                {isThinking ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            </div>
            <div className="flex flex-col gap-0.5">
                <span className="text-sm font-semibold tracking-tight text-foreground/90">
                    {isThinking ? "Deep Researching" : "Research Completed"}
                </span>
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                    {isThinking ? "Processing..." : `${tools.length} Steps Executed`}
                </span>
            </div>
         </div>
         <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-foreground rounded-full"
         >
            <ChevronDown className={cn("h-4 w-4 transition-transform duration-300", isOpen && "rotate-180")} />
         </Button>
      </div>

      {/* Stepper (Always Visible) */}
      <div className="px-4 pb-4 pt-1">
          <div className="relative flex items-center justify-between mt-2">
              {/* Connecting Line */}
              <div className="absolute left-0 top-1/2 -translate-y-1/2 w-full h-[2px] bg-muted z-0 rounded-full" />
              <div
                  className="absolute left-0 top-1/2 -translate-y-1/2 h-[2px] bg-primary transition-all duration-700 ease-in-out z-0 rounded-full"
                  style={{ width: `${(activeStep / (steps.length - 1)) * 100}%` }}
              />

              {steps.map((step, index) => {
                  const isActive = index === activeStep
                  const isCompleted = index < activeStep
                  const Icon = step.icon

                  return (
                      <div key={step.label} className="relative z-10 flex flex-col items-center gap-2 group">
                          <div className={cn(
                              "w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all duration-300 bg-background shadow-sm",
                              isActive ? "border-primary text-primary scale-110 ring-4 ring-primary/10" :
                              isCompleted ? "border-primary bg-primary text-primary-foreground border-transparent" :
                              "border-muted-foreground/30 text-muted-foreground"
                          )}>
                              <Icon className="w-3.5 h-3.5" />
                          </div>
                          <span className={cn(
                              "text-[10px] font-semibold transition-colors duration-300 absolute -bottom-6 whitespace-nowrap",
                              isActive ? "text-primary" :
                              isCompleted ? "text-foreground/80" :
                              "text-muted-foreground/60"
                          )}>
                              {step.label}
                          </span>
                      </div>
                  )
              })}
          </div>
          <div className="h-4" /> {/* Spacer for labels */}
      </div>

      {/* Logs (Collapsible) */}
      {isOpen && (
        <div className="border-t border-border/50 bg-muted/10 animate-in slide-in-from-top-2 duration-300">
            <ScrollArea className="h-[240px]">
                <div className="p-3 space-y-2">
                    {tools.map((tool, i) => (
                        <LogItem key={tool.toolCallId} tool={tool} index={i} />
                    ))}
                </div>
            </ScrollArea>
        </div>
      )}
    </Card>
  )
}

function LogItem({ tool, index }: { tool: ToolInvocation, index: number }) {
  const isRunning = tool.state === 'running'

  return (
    <div className="group flex gap-3 p-2.5 rounded-lg hover:bg-muted/40 border border-transparent hover:border-border/40 transition-all duration-200">
       <div className="flex flex-col items-center gap-1">
           <div className={cn(
               "w-1.5 h-1.5 rounded-full mt-1.5",
               isRunning ? "bg-blue-500 animate-pulse" : "bg-muted-foreground/40"
           )} />
           <div className="w-[1px] h-full bg-border/40 group-last:hidden" />
       </div>

       <div className="flex-1 min-w-0">
           <div className="flex items-center justify-between mb-0.5">
               <div className="flex items-center gap-2">
                   <Badge variant="outline" className={cn(
                       "text-[10px] h-5 px-1.5 font-mono uppercase tracking-wider",
                       tool.toolName.includes('search') ? "bg-blue-500/10 text-blue-600 border-blue-200 dark:border-blue-800" :
                       tool.toolName.includes('code') ? "bg-purple-500/10 text-purple-600 border-purple-200 dark:border-purple-800" :
                       "bg-zinc-500/10 text-zinc-600 border-zinc-200 dark:border-zinc-800"
                   )}>
                       {tool.toolName.replace(/_/g, ' ')}
                   </Badge>
                   <span className="text-[10px] text-muted-foreground font-mono">
                       {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                   </span>
               </div>
               <span className={cn(
                   "text-[10px] font-medium px-1.5 py-0.5 rounded-full",
                   isRunning ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-400"
               )}>
                   {tool.state}
               </span>
           </div>

           {(tool.args?.query || tool.args?.code) && (
               <div className="mt-1.5 p-2 rounded bg-muted/40 border border-border/40 font-mono text-[10px] text-muted-foreground overflow-x-auto whitespace-pre-wrap break-all">
                   {tool.toolName === 'tavily_search' ? `Query: "${tool.args.query}"` :
                    tool.toolName === 'execute_python_code' ? tool.args.code?.slice(0, 100) + (tool.args.code?.length > 100 ? '...' : '') :
                    JSON.stringify(tool.args)}
               </div>
           )}
       </div>
    </div>
  )
}
