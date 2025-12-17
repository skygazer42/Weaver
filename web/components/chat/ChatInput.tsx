'use client'

import React, { useRef, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Send, StopCircle, Globe, Bot, BrainCircuit, Paperclip, Sparkles, X, Mic } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  input: string
  setInput: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  isLoading: boolean
  onStop: () => void
  searchMode: string
  setSearchMode: (mode: string) => void
}

export function ChatInput({ 
  input, 
  setInput, 
  onSubmit, 
  isLoading, 
  onStop, 
  searchMode, 
  setSearchMode 
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [isFocused, setIsFocused] = useState(false)

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'inherit'
      const scrollHeight = textareaRef.current.scrollHeight
      textareaRef.current.style.height = `${Math.min(Math.max(scrollHeight, 56), 200)}px`
    }
  }, [input])

  useEffect(() => {
    if (!isLoading) {
      textareaRef.current?.focus()
    }
  }, [isLoading])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(e)
    }
  }

  const modes = [
    { id: 'web', label: 'Web', icon: Globe, color: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/20" },
    { id: 'agent', label: 'Agent', icon: Bot, color: "text-purple-500", bg: "bg-purple-500/10", border: "border-purple-500/20" },
    { id: 'deep', label: 'Deep Search', icon: BrainCircuit, color: "text-amber-500", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  ]

  const activeMode = modes.find(m => m.id === searchMode)

  return (
    <div className="relative z-20 mx-auto w-full max-w-3xl px-4 pb-6">
      <div className="flex flex-col gap-2">
        
        {/* Mode Tabs */}
        <div className="flex items-center gap-1 self-start ml-1 mb-1">
           {modes.map((mode) => {
             const isActive = searchMode === mode.id
             return (
               <button
                 key={mode.id}
                 type="button"
                 onClick={() => setSearchMode(mode.id)}
                 className={cn(
                   "relative flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 border",
                   isActive 
                     ? cn("text-foreground shadow-sm", mode.bg, mode.border)
                     : "text-muted-foreground border-transparent hover:bg-muted/50"
                 )}
               >
                 <mode.icon className={cn("h-3.5 w-3.5 transition-colors", isActive ? mode.color : "text-muted-foreground")} />
                 {mode.label}
               </button>
             )
           })}
        </div>

        {/* Input Container */}
        <div 
          className={cn(
            "relative group rounded-3xl border bg-background shadow-lg shadow-black/5 transition-all duration-300",
            isFocused ? "ring-2 ring-primary/20 border-primary" : "border-border/50",
            isLoading && "opacity-80"
          )}
        >
          {/* Top Actions (Attachments) */}
           <div className="absolute top-3 left-3 flex gap-1 z-10">
               <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-full transition-colors"
                title="Attach file"
              >
                <Paperclip className="h-4 w-4" />
              </Button>
           </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={`Ask anything...`}
            disabled={isLoading}
            rows={1}
            className="w-full resize-none bg-transparent px-14 py-4 min-h-[56px] max-h-[200px] text-base focus:outline-none placeholder:text-muted-foreground/50 scrollbar-thin scrollbar-thumb-muted"
          />

          {/* Right Actions (Send/Mic) */}
          <div className="absolute bottom-3 right-3 flex items-center gap-2">
             {/* Mic placeholder */}
             {!input && !isLoading && (
                 <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground rounded-full"
                 >
                    <Mic className="h-4 w-4" />
                 </Button>
             )}

            {isLoading ? (
              <Button 
                type="button" 
                size="icon" 
                variant="ghost" 
                onClick={onStop}
                className="h-8 w-8 hover:bg-destructive/10 hover:text-destructive rounded-full"
              >
                <div className="h-2.5 w-2.5 bg-current rounded-sm animate-pulse" />
              </Button>
            ) : (
              <Button 
                type="button" 
                size="icon" 
                onClick={(e) => onSubmit(e as any)}
                disabled={!input.trim()}
                className={cn(
                    "h-8 w-8 rounded-full transition-all duration-300 shadow-sm",
                    input.trim() 
                      ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-110" 
                      : "bg-muted text-muted-foreground"
                )}
              >
                <Send className="h-4 w-4 ml-0.5" />
              </Button>
            )}
          </div>
        </div>
        
        <div className="flex justify-between px-4 text-[10px] text-muted-foreground opacity-60">
            <span><strong>Shift + Enter</strong> for new line</span>
            <span>AI can make mistakes.</span>
        </div>
      </div>
    </div>
  )
}
