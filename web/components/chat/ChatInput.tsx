'use client'

import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Send, StopCircle, Globe, Bot, BrainCircuit, Paperclip, Sparkles, X, Mic, Server, ChevronDown, Check, Trash2, File as FileIcon, Image as ImageIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  input: string
  setInput: (value: string) => void
  attachments: File[]
  setAttachments: (files: File[]) => void
  onSubmit: (e: React.FormEvent) => void
  isLoading: boolean
  onStop: () => void
  searchMode: string
  setSearchMode: (mode: string) => void
}

export function ChatInput({ 
  input, 
  setInput,
  attachments,
  setAttachments, 
  onSubmit, 
  isLoading, 
  onStop, 
  searchMode, 
  setSearchMode 
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isFocused, setIsFocused] = useState(false)
  const [showCommandMenu, setShowCommandMenu] = useState(false)
  const [isMcpOpen, setIsMcpOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedMcp, setSelectedMcp] = useState('filesystem') // Default MCP

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setAttachments([...attachments, ...Array.from(e.target.files)])
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    if (e.dataTransfer.files) {
      setAttachments([...attachments, ...Array.from(e.dataTransfer.files)])
    }
  }, [attachments, setAttachments])

  const removeAttachment = (index: number) => {
    setAttachments(attachments.filter((_, i) => i !== index))
  }

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
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "relative group rounded-3xl border bg-background shadow-lg shadow-black/5 transition-all duration-300 overflow-hidden",
            isFocused ? "ring-2 ring-primary/20 border-primary" : "border-border/50",
            isDragging ? "ring-2 ring-primary border-primary bg-primary/5" : "",
            isLoading && "opacity-80"
          )}
        >
           {/* Drag Overlay */}
           {isDragging && (
             <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
                <div className="text-primary font-medium flex flex-col items-center gap-2">
                    <div className="p-4 rounded-full bg-primary/10">
                        <Paperclip className="h-8 w-8" />
                    </div>
                    <span>Drop files here</span>
                </div>
             </div>
           )}

           <div className="absolute top-3 left-3 flex gap-1 z-10">
               <input 
                  type="file" 
                  multiple 
                  className="hidden" 
                  ref={fileInputRef}
                  onChange={handleFileSelect}
               />
               <Button 
                  type="button" 
                  variant="ghost" 
                  size="icon" 
                  className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-full transition-colors"
                  onClick={() => fileInputRef.current?.click()}
               >
                <Paperclip className="h-4 w-4" />
              </Button>
           </div>

          <div className="flex flex-col w-full">
              {/* Attachments Preview */}
              {attachments.length > 0 && (
                  <div className="flex gap-2 px-14 pt-4 overflow-x-auto py-2 scrollbar-none">
                      {attachments.map((file, i) => (
                          <div key={i} className="relative group/attachment flex-shrink-0">
                              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 border text-xs font-medium max-w-[200px]">
                                  {file.type.startsWith('image/') ? (
                                      <ImageIcon className="h-3.5 w-3.5 text-blue-500" />
                                  ) : (
                                      <FileIcon className="h-3.5 w-3.5 text-orange-500" />
                                  )}
                                  <span className="truncate">{file.name}</span>
                              </div>
                              <button 
                                  onClick={() => removeAttachment(i)}
                                  className="absolute -top-1 -right-1 bg-background border rounded-full p-0.5 text-muted-foreground hover:text-destructive shadow-sm opacity-0 group-hover/attachment:opacity-100 transition-opacity"
                              >
                                  <X className="h-3 w-3" />
                              </button>
                          </div>
                      ))}
                  </div>
              )}

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
                className={cn(
                    "w-full resize-none bg-transparent px-14 min-h-[56px] max-h-[200px] text-base focus:outline-none placeholder:text-muted-foreground/50 scrollbar-thin scrollbar-thumb-muted",
                    attachments.length > 0 ? "pt-2 pb-4" : "py-4"
                )}
              />
          </div>

          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            {isLoading ? (
              <Button type="button" size="icon" variant="ghost" onClick={onStop} className="h-8 w-8 hover:bg-destructive/10 hover:text-destructive rounded-full">
                <div className="h-2.5 w-2.5 bg-current rounded-sm animate-pulse" />
              </Button>
            ) : (
              <Button type="button" size="icon" onClick={(e) => onSubmit(e as any)} disabled={!input.trim() && attachments.length === 0} className={cn("h-8 w-8 rounded-full transition-all duration-300 shadow-sm", (input.trim() || attachments.length > 0) ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-110" : "bg-muted text-muted-foreground")}>
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
