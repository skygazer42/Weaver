'use client'

import { useState, useEffect } from 'react'
import { ChevronDown, Loader2, BrainCircuit, Globe, Code, FileText, CheckCircle2 } from 'lucide-react'
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
    <Card className="w-full max-w-md my-3 overflow-hidden border-border/60 transition-shadow duration-200 hover:shadow-md">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
         <div className="flex items-center gap-3">
            <div className={cn(
                "flex items-center justify-center size-8 rounded-full ring-1 ring-border shadow-sm transition-colors duration-200",
                isThinking ? "bg-primary/10 text-primary ring-primary/20" : "bg-muted text-muted-foreground"
            )}>
                {isThinking ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            </div>
            <div className="flex flex-col gap-0.5">
                <span className="text-sm font-semibold text-foreground/90">
                    {isThinking ? "Deep Researching" : "Research Completed"}
                </span>
                <span className="text-[10px] font-medium text-muted-foreground uppercase">
                    {isThinking ? "Processing..." : `${tools.length} Steps Executed`}
                </span>
            </div>
         </div>
         <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-foreground rounded-full"
            aria-label={isOpen ? "Collapse thinking steps" : "Expand thinking steps"}
            title={isOpen ? "Collapse" : "Expand"}
         >
            <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", isOpen && "rotate-180")} />
         </Button>
      </div>

      {/* Stepper (Always Visible) */}
      <div className="px-4 pb-4 pt-1">
          <div className="relative flex items-center justify-between mt-2">
              {/* Connecting Line */}
              <div className="absolute left-0 top-1/2 -translate-y-1/2 w-full h-[2px] bg-muted z-0 rounded-full" />
              <div
                  className="absolute left-0 top-1/2 -translate-y-1/2 h-[2px] w-full bg-primary origin-left z-0 rounded-full"
                  style={{ transform: `scaleX(${activeStep / (steps.length - 1)})` }}
              />

              {steps.map((step, index) => {
                  const isActive = index === activeStep
                  const isCompleted = index < activeStep
                  const Icon = step.icon

                  return (
                      <div key={step.label} className="relative z-10 flex flex-col items-center gap-2 group">
                          <div className={cn(
                              "size-8 rounded-full flex items-center justify-center border-2 bg-background shadow-sm",
                              isActive ? "border-primary text-primary ring-4 ring-primary/10" :
                              isCompleted ? "border-primary bg-primary text-primary-foreground border-transparent" :
                              "border-border/60 text-muted-foreground"
                          )}>
                              <Icon className="w-3.5 h-3.5" />
                          </div>
                          <span className={cn(
                              "text-[10px] font-semibold absolute -bottom-6 whitespace-nowrap",
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
        <div className="border-t border-border/60 bg-muted/10">
            <ScrollArea className="h-[240px]">
                <div className="p-3 space-y-2">
                    {tools.map((tool) => (
                        <LogItem key={tool.toolCallId} tool={tool} />
                    ))}
                </div>
            </ScrollArea>
        </div>
      )}
    </Card>
  )
}

function LogItem({ tool }: { tool: ToolInvocation }) {
  const isRunning = tool.state === 'running'
  const query = typeof tool.args?.query === 'string' ? tool.args.query : null
  const code = typeof tool.args?.code === 'string' ? tool.args.code : null
  const hasPreview = !!(query || code)

  return (
    <div className="group flex gap-3 p-2.5 rounded-lg hover:bg-muted/40 border border-transparent hover:border-border/40 transition-colors duration-200">
       <div className="flex flex-col items-center gap-1">
           <div className={cn(
               "w-1.5 h-1.5 rounded-full mt-1.5",
               isRunning ? "bg-primary" : "bg-border/60"
           )} />
           <div className="w-[1px] h-full bg-border/40 group-last:hidden" />
       </div>

       <div className="flex-1 min-w-0">
           <div className="flex items-center justify-between mb-0.5">
               <div className="flex items-center gap-2">
                   <Badge
                     variant="outline"
                     className="text-[10px] h-5 px-1.5 font-mono uppercase bg-muted/20 border-border/60 text-muted-foreground"
                   >
                       {tool.toolName.replace(/_/g, ' ')}
                   </Badge>
                   <span className="text-[10px] text-muted-foreground font-mono">
                       {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                   </span>
               </div>
               <span className={cn(
                   "text-[10px] font-medium px-1.5 py-0.5 rounded-full",
                   isRunning ? "bg-primary/10 text-primary" : "bg-muted/30 text-muted-foreground"
               )}>
                   {tool.state}
               </span>
           </div>

           {hasPreview && (
               <div className="mt-1.5 p-2 rounded bg-muted/40 border border-border/40 font-mono text-[10px] text-muted-foreground overflow-x-auto whitespace-pre-wrap break-all">
                   {tool.toolName === 'tavily_search' && query ? `Query: "${query}"` :
                    tool.toolName === 'execute_python_code' && code ? code.slice(0, 100) + (code.length > 100 ? '...' : '') :
                    JSON.stringify(tool.args)}
               </div>
           )}
       </div>
    </div>
  )
}
