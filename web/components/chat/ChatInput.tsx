'use client'

import React, { useRef, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Send, StopCircle, Globe, Bot, BrainCircuit, Paperclip, Sparkles, X, Mic, Server, ChevronDown, Check, Trash2 } from 'lucide-react'
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
  const [showCommandMenu, setShowCommandMenu] = useState(false)
  const [isMcpOpen, setIsMcpOpen] = useState(false)
  const [selectedMcp, setSelectedMcp] = useState('filesystem') // Default MCP

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

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const val = e.target.value
      setInput(val)
      if (val === '/') setShowCommandMenu(true)
      else if (showCommandMenu && !val.startsWith('/')) setShowCommandMenu(false)
  }

  const handleCommandSelect = (cmd: string) => {
      if (['deep','agent','web'].includes(cmd)) setSearchMode(cmd)
      if (cmd === 'clear') window.location.reload()
      setInput('')
      setShowCommandMenu(false)
      textareaRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(e)
    }
    if (e.key === 'Escape') {
        setShowCommandMenu(false)
        setIsMcpOpen(false)
    }
  }

  const mcpOptions = [
      { id: 'filesystem', label: 'Filesystem' },
      { id: 'github', label: 'GitHub' },
      { id: 'brave', label: 'Brave Search' },
      { id: 'memory', label: 'Memory' }
  ]

  const modes = [
    { id: 'web', label: 'Web', icon: Globe, color: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/20" },
    { id: 'agent', label: 'Agent', icon: Bot, color: "text-purple-500", bg: "bg-purple-500/10", border: "border-purple-500/20" },
    { id: 'deep', label: 'Deep Search', icon: BrainCircuit, color: "text-amber-500", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  ]

  const commands = [
      { id: 'deep', label: 'Deep Mode', icon: BrainCircuit, desc: 'Switch to Deep Search' },
      { id: 'agent', label: 'Agent Mode', icon: Bot, desc: 'Switch to Agent' },
      { id: 'web', label: 'Web Mode', icon: Globe, desc: 'Switch to Web Search' },
      { id: 'clear', label: 'Clear Chat', icon: Trash2, desc: 'Reset conversation' },
  ]
  
  return (
    <div className="relative z-20 mx-auto w-full max-w-3xl px-4 pb-6">
      <div className="flex flex-col gap-2">
        
        {/* Command Menu */}
        {showCommandMenu && (
            <div className="absolute bottom-full left-4 mb-2 w-64 bg-popover border rounded-xl shadow-xl overflow-hidden animate-in slide-in-from-bottom-2 fade-in z-50">
                <div className="px-3 py-2 text-xs font-semibold text-muted-foreground bg-muted/50 border-b">Commands</div>
                <div className="p-1">
                    {commands.map(cmd => (
                        <button key={cmd.id} onClick={() => handleCommandSelect(cmd.id)} className="flex items-center gap-3 w-full px-2 py-2 text-sm rounded-lg hover:bg-accent hover:text-accent-foreground text-left transition-colors">
                            <div className="flex items-center justify-center h-6 w-6 rounded bg-background border shadow-sm">
                                <cmd.icon className="h-3.5 w-3.5" />
                            </div>
                            <div>
                                <div className="font-medium">{cmd.label}</div>
                                <div className="text-[10px] text-muted-foreground">{cmd.desc}</div>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        )}

        {/* Mode Tabs */}
        <div className="flex items-center gap-1 self-start ml-1 mb-1">
           {modes.map((mode) => {
             const isActive = searchMode === mode.id
             return (
               <button
                 key={mode.id}
                 type="button"
                 onClick={() => {
                     setSearchMode(mode.id)
                     setIsMcpOpen(false)
                 }}
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

           {/* MCP Dropdown */}
           <div className="relative">
               <button
                 onClick={() => {
                     setSearchMode('mcp')
                     setIsMcpOpen(!isMcpOpen)
                 }}
                 className={cn(
                   "relative flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 border",
                   searchMode === 'mcp'
                     ? "bg-green-500/10 text-foreground border-green-500/20 shadow-sm"
                     : "text-muted-foreground border-transparent hover:bg-muted/50"
                 )}
               >
                 <Server className={cn("h-3.5 w-3.5 transition-colors", searchMode === 'mcp' ? "text-green-500" : "text-muted-foreground")} />
                 {searchMode === 'mcp' ? (mcpOptions.find(o => o.id === selectedMcp)?.label || 'MCP') : 'MCP'}
                 <ChevronDown className="h-3 w-3 opacity-50" />
               </button>

               {isMcpOpen && (
                   <div className="absolute bottom-full left-0 mb-2 w-40 bg-popover border rounded-xl shadow-lg animate-in fade-in zoom-in-95 z-50 overflow-hidden">
                       <div className="p-1">
                           {mcpOptions.map(opt => (
                               <button
                                   key={opt.id}
                                   onClick={() => {
                                       setSelectedMcp(opt.id)
                                       setSearchMode('mcp')
                                       setIsMcpOpen(false)
                                   }}
                                   className={cn(
                                       "flex w-full items-center justify-between rounded-lg px-2 py-2 text-xs transition-colors hover:bg-muted",
                                       selectedMcp === opt.id && searchMode === 'mcp' && "bg-muted font-medium text-green-500"
                                   )}
                               >
                                   {opt.label}
                                   {selectedMcp === opt.id && searchMode === 'mcp' && <Check className="h-3 w-3" />}
                               </button>
                           ))}
                       </div>
                   </div>
               )}
           </div>
        </div>

        {/* Input Container */}
        <div 
          className={cn(
            "relative group rounded-3xl border bg-background shadow-lg shadow-black/5 transition-all duration-300",
            isFocused ? "ring-2 ring-primary/20 border-primary" : "border-border/50",
            isLoading && "opacity-80"
          )}
        >
           <div className="absolute top-3 left-3 flex gap-1 z-10">
               <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-full transition-colors">
                <Paperclip className="h-4 w-4" />
              </Button>
           </div>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={`Ask ${searchMode === 'mcp' ? selectedMcp : 'anything'}...`}
            disabled={isLoading}
            rows={1}
            className="w-full resize-none bg-transparent px-14 py-4 min-h-[56px] max-h-[200px] text-base focus:outline-none placeholder:text-muted-foreground/50 scrollbar-thin scrollbar-thumb-muted"
          />

          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            {isLoading ? (
              <Button type="button" size="icon" variant="ghost" onClick={onStop} className="h-8 w-8 hover:bg-destructive/10 hover:text-destructive rounded-full">
                <div className="h-2.5 w-2.5 bg-current rounded-sm animate-pulse" />
              </Button>
            ) : (
              <Button type="button" size="icon" onClick={(e) => onSubmit(e as any)} disabled={!input.trim()} className={cn("h-8 w-8 rounded-full transition-all duration-300 shadow-sm", input.trim() ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-110" : "bg-muted text-muted-foreground")}>
                <Send className="h-4 w-4 ml-0.5" />
              </Button>
            )}
          </div>
        </div>
        
        <div className="flex justify-between px-4 text-[10px] text-muted-foreground opacity-60">
            <span><strong>/</strong> for commands</span>
            <span>AI can make mistakes.</span>
        </div>
      </div>
    </div>
  )
}
