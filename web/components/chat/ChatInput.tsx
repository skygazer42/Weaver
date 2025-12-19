'use client'

import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Globe, Bot, Paperclip, X, Mic, MicOff, ChevronDown, Check, Trash2, File as FileIcon, Image as ImageIcon, Bug, BookOpen, PenTool, TestTube, Plug, Lightbulb, Rocket } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { createFilePreview } from '@/lib/file-utils'

interface ChatInputProps {
  input: string
  setInput: React.Dispatch<React.SetStateAction<string>>
  attachments: File[]
  setAttachments: (files: File[]) => void
  onSubmit: (e: React.FormEvent) => void
  isLoading: boolean
  onStop: () => void
  searchMode: string
  setSearchMode: (mode: string) => void
}

interface AttachmentPreview {
    file: File
    previewUrl: string
    revoke: () => void
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
  const { t } = useI18n()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isFocused, setIsFocused] = useState(false)
  const [showCommandMenu, setShowCommandMenu] = useState(false)
  const [isMcpOpen, setIsMcpOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedMcp, setSelectedMcp] = useState('filesystem') // Default MCP
  const [previews, setPreviews] = useState<AttachmentPreview[]>([])

  // Manage Previews
  useEffect(() => {
      // Sync previews with attachments
      // This is a bit tricky if we want to avoid recreating URLs for existing files.
      // A simple approach: Clear all old previews and create new ones is robust but inefficient.
      // Better: Create previews only for new files.
      
      // Cleanup function for removed files is handled by the revoke() call
      
      const newPreviews: AttachmentPreview[] = []
      
      attachments.forEach(file => {
          const existing = previews.find(p => p.file === file)
          if (existing) {
              newPreviews.push(existing)
          } else {
              const { url, revoke } = createFilePreview(file)
              newPreviews.push({ file, previewUrl: url, revoke })
          }
      })

      // Clean up removed previews
      previews.forEach(p => {
          if (!attachments.includes(p.file)) {
              p.revoke()
          }
      })

      setPreviews(newPreviews)
      
      // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attachments])

  // Cleanup on unmount
  useEffect(() => {
      return () => {
          previews.forEach(p => p.revoke())
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const [isListening, setIsListening] = useState(false)
  const [isProcessingAudio, setIsProcessingAudio] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
      })

      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop())

        if (audioChunksRef.current.length === 0) {
          setIsListening(false)
          setIsProcessingAudio(false)
          return
        }

        setIsProcessingAudio(true)

        try {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
          const reader = new FileReader()
          reader.onloadend = async () => {
            const base64Audio = (reader.result as string).split(',')[1]

            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/asr/recognize`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                audio_data: base64Audio,
                format: 'webm',
                sample_rate: 16000,
                language_hints: ['zh', 'en']
              })
            })

            const result = await response.json()

            if (result.success && result.text) {
              setInput(prev => prev + (prev ? ' ' : '') + result.text)
              toast.success('Speech recognized')
            } else if (result.error) {
              if (response.status === 503) {
                toast.info('Using browser fallback')
                fallbackToWebSpeech()
              } else {
                toast.error(`ASR Error: ${result.error}`)
              }
            }
          }
          reader.readAsDataURL(audioBlob)
        } catch (error) {
          console.error('ASR error:', error)
          toast.error('Recognition failed')
        } finally {
          setIsProcessingAudio(false)
          setIsListening(false)
        }
      }

      mediaRecorder.start(100)
      setIsListening(true)
      toast.info('Listening... Click to stop')

    } catch (error) {
      console.error('Microphone error:', error)
      toast.error('Microphone access denied')
      setIsListening(false)
    }
  }

  const fallbackToWebSpeech = () => {
    if (typeof window !== 'undefined' && !('webkitSpeechRecognition' in window)) {
      toast.error('Web Speech API not supported')
      return
    }

    // @ts-ignore
    const SpeechRecognition = window.webkitSpeechRecognition as any
    const recognition = new SpeechRecognition()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = 'en-US' // Consider dynamic lang

    recognition.onstart = () => setIsListening(true)
    recognition.onend = () => setIsListening(false)
    recognition.onerror = (event: any) => {
      setIsListening(false)
      console.error('Speech error:', event.error)
    }
    recognition.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript
        }
      }
      if (finalTranscript) {
        setInput(prev => prev + (prev ? ' ' : '') + finalTranscript)
      }
    }

    recognition.start()
  }

  const stopListening = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    setIsListening(false)
  }

  const handleCommandSelect = (cmd: string) => {
      if (['think','agent','ultra','web','deep','deep_agent'].includes(cmd)) setSearchMode(cmd)
      if (cmd === 'clear') window.location.reload()

      if (cmd === 'fix') setInput('Please fix the following code:\n\n')
      if (cmd === 'explain') setInput('Please explain this concept:\n\n')
      if (cmd === 'refactor') setInput('Please refactor this code to be more efficient:\n\n')
      if (cmd === 'test') setInput('Please generate unit tests for:\n\n')

      if (!['fix','explain','refactor','test'].includes(cmd)) setInput('')
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
      { id: 'filesystem', label: t('filesystem') },
      { id: 'github', label: t('github') },
      { id: 'brave', label: t('braveSearch') },
      { id: 'memory', label: t('memory') }
  ]

  const modes = [
    { id: 'think', label: t('think'), icon: Lightbulb, color: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
    { id: 'web', label: t('web'), icon: Globe, color: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/20" },
    { id: 'agent', label: t('agent'), icon: Bot, color: "text-purple-500", bg: "bg-purple-500/10", border: "border-purple-500/20" },
    { id: 'ultra', label: t('ultra'), icon: Rocket, color: "text-indigo-500", bg: "bg-indigo-500/10", border: "border-indigo-500/20" },
  ]

  const commands = [
      { id: 'think', label: 'Think Mode', icon: Lightbulb, desc: 'LLM only, no external tools' },
      { id: 'agent', label: 'Agent Mode', icon: Bot, desc: 'Plan & web search' },
      { id: 'ultra', label: 'Ultra Mode', icon: Rocket, desc: 'Deep research (agent + deep search)' },
      { id: 'web', label: 'Web Mode', icon: Globe, desc: 'Web search only' },
      { id: 'fix', label: 'Fix Code', icon: Bug, desc: 'Debug & Fix' },
      { id: 'explain', label: 'Explain', icon: BookOpen, desc: 'Explain concept' },
      { id: 'refactor', label: 'Refactor', icon: PenTool, desc: 'Optimize code' },
      { id: 'test', label: 'Write Tests', icon: TestTube, desc: 'Generate tests' },
      { id: 'clear', label: 'Clear Chat', icon: Trash2, desc: 'Reset conversation' },
  ]
  
  return (
    <div className="relative z-20 mx-auto w-full max-w-3xl px-4 pb-6">
      <div className="flex flex-col gap-2">
        
        {/* Command Menu */}
        {showCommandMenu && (
            <div className="absolute bottom-full left-4 mb-2 w-64 bg-popover border rounded-xl shadow-xl overflow-hidden animate-in slide-in-from-bottom-2 fade-in z-50">
                <div className="px-3 py-2 text-xs font-semibold text-muted-foreground bg-muted/50 border-b">{t('commands')}</div>
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
                     ? "bg-pink-500/10 text-foreground border-pink-500/20 shadow-sm"
                     : "text-muted-foreground border-transparent hover:bg-muted/50"
                 )}
               >
                 <Plug className={cn("h-3.5 w-3.5 transition-colors", searchMode === 'mcp' ? "text-pink-500" : "text-muted-foreground")} />
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
                                       selectedMcp === opt.id && searchMode === 'mcp' && "bg-muted font-medium text-pink-500"
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
                    <span>{t('dropFilesHere')}</span>
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
              {previews.length > 0 && (
                  <div className="flex gap-2 px-14 pt-4 overflow-x-auto py-2 scrollbar-none">
                      {previews.map((item, i) => (
                          <div key={i} className="relative group/attachment flex-shrink-0">
                              <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-muted/50 border text-xs font-medium max-w-[200px] overflow-hidden">
                                  {item.file.type.startsWith('image/') ? (
                                      <div className="h-8 w-8 rounded overflow-hidden flex-shrink-0 bg-background">
                                         <img src={item.previewUrl} alt="preview" className="h-full w-full object-cover" />
                                      </div>
                                  ) : (
                                      <div className="h-8 w-8 rounded bg-background flex items-center justify-center flex-shrink-0">
                                          <FileIcon className="h-4 w-4 text-orange-500" />
                                      </div>
                                  )}
                                  <span className="truncate flex-1">{item.file.name}</span>
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
                placeholder={searchMode === 'mcp' ? `${mcpOptions.find(o => o.id === selectedMcp)?.label || 'MCP'}...` : t('askAnything')}
                disabled={isLoading}
                rows={1}
                className={cn(
                    "w-full resize-none bg-transparent px-14 min-h-[56px] max-h-[200px] text-base focus:outline-none placeholder:text-muted-foreground/50 scrollbar-thin scrollbar-thumb-muted",
                    attachments.length > 0 ? "pt-2 pb-4" : "py-4"
                )}
              />
          </div>

          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            {!isLoading && (
                 <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={isListening ? stopListening : startListening}
                    disabled={isProcessingAudio}
                    className={cn(
                        "h-8 w-8 rounded-full hover:bg-muted transition-all duration-300",
                        isListening && "bg-red-500/10 text-red-500 animate-pulse hover:bg-red-500/20",
                        isProcessingAudio && "bg-blue-500/10 text-blue-500 animate-spin"
                    )}
                 >
                    {isProcessingAudio ? (
                      <div className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : isListening ? (
                      <MicOff className="h-4 w-4" />
                    ) : (
                      <Mic className="h-4 w-4" />
                    )}
                 </Button>
            )}

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
            <span><strong>/</strong> {t('forCommands')}</span>
            <span>{t('aiCanMakeMistakes')}</span>
        </div>
      </div>
    </div>
  )
}
