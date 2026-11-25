'use client'

import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Globe, Bot, Paperclip, X, Mic, MicOff, ChevronDown, Check, Trash2, File as FileIcon, Bug, BookOpen, PenTool, TestTube, Plug, Rocket } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { createFilePreview } from '@/lib/file-utils'
import { getApiBaseUrl } from '@/lib/api'

interface ChatInputProps {
  input: string
  setInput: React.Dispatch<React.SetStateAction<string>>
  attachments: File[]
  setAttachments: (files: File[]) => void
  onSubmit: (e: React.FormEvent) => void
  isLoading: boolean
  canStop: boolean
  isStopping: boolean
  awaitingApproval: boolean
  onStop: () => void
  searchMode: string
  setSearchMode: (mode: string) => void
}

function AttachmentImage({ file }: { file: File }) {
  const imageRef = useRef<HTMLImageElement>(null)
  useEffect(() => {
    const { url, revoke } = createFilePreview(file)
    if (imageRef.current) imageRef.current.src = url
    return revoke
  }, [file])
  return <img ref={imageRef} alt={file.name} className="h-full w-full object-cover" />
}

export function ChatInput({
  input,
  setInput,
  attachments,
  setAttachments,
  onSubmit,
  isLoading,
  canStop,
  isStopping,
  awaitingApproval,
  onStop,
  searchMode,
  setSearchMode
}: ChatInputProps) {
  const { t } = useI18n()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasLoading = useRef(isLoading)
  const fileInputRef = useRef<HTMLInputElement>(null)
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
      textareaRef.current.style.height = `${Math.min(Math.max(scrollHeight, 72), 200)}px`
    }
  }, [input])

  useEffect(() => {
    if (wasLoading.current && !isLoading) {
      textareaRef.current?.focus()
    }
    wasLoading.current = isLoading
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

            const response = await fetch(`${getApiBaseUrl()}/api/asr/recognize`, {
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
      if (cmd === 'direct') setSearchMode('')
      else if (['agent','ultra','web','deep','deep_agent'].includes(cmd)) setSearchMode(cmd)
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
    { id: 'web', label: t('web'), icon: Globe },
    { id: 'agent', label: t('agent'), icon: Bot },
    { id: 'ultra', label: t('ultra'), icon: Rocket },
  ]

  const commands = [
      { id: 'agent', label: 'Agent Mode', icon: Bot, desc: 'Plan & web search' },
      { id: 'ultra', label: 'Deep Research', icon: Rocket, desc: 'Deep research (agent + deep search)' },
      { id: 'web', label: 'Web Mode', icon: Globe, desc: 'Web search only' },
      { id: 'fix', label: 'Fix Code', icon: Bug, desc: 'Debug & Fix' },
      { id: 'explain', label: 'Explain', icon: BookOpen, desc: 'Explain concept' },
      { id: 'refactor', label: 'Refactor', icon: PenTool, desc: 'Optimize code' },
      { id: 'test', label: 'Write Tests', icon: TestTube, desc: 'Generate tests' },
      { id: 'clear', label: 'Clear Chat', icon: Trash2, desc: 'Reset conversation' },
  ]
  
  return (
    <div
      className="relative z-20 mx-auto w-full max-w-5xl shrink-0 px-3 pb-4 pt-1 sm:px-5"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setShowCommandMenu(false)
          setIsMcpOpen(false)
        }
      }}
    >
      {showCommandMenu && (
        <div className="absolute bottom-full left-3 z-50 mb-2 w-80 max-w-[calc(100%-2rem)] overflow-hidden rounded-lg border border-border/80 bg-popover text-popover-foreground shadow-elevated sm:left-5">
          <div className="border-b border-border/70 bg-surface-subtle px-3 py-2 text-[11px] font-semibold tracking-wide text-muted-foreground">{t('commands')}</div>
          <div className="max-h-80 overflow-y-auto p-1.5">
            {commands.map(cmd => (
              <button
                key={cmd.id}
                type="button"
                onClick={() => handleCommandSelect(cmd.id)}
                className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border/70 bg-card text-muted-foreground">
                  <cmd.icon className="h-3.5 w-3.5" />
                </div>
                <div>
                  <div className="font-medium">{cmd.label}</div>
                  <div className="text-xs text-muted-foreground">{cmd.desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mb-2 flex w-full flex-nowrap items-center gap-0.5 whitespace-nowrap">
        {modes.map(mode => {
          const isActive = searchMode === mode.id
          return (
            <button
              key={mode.id}
              type="button"
              aria-label={mode.id === 'agent' ? 'Agent' : mode.id === 'ultra' ? 'Deep Research' : undefined}
              aria-pressed={isActive}
              onClick={() => {
                setSearchMode(isActive ? '' : mode.id)
                setIsMcpOpen(false)
              }}
              className={cn(
                'flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                isActive
                  ? 'border-primary/25 bg-primary/10 text-primary shadow-xs'
                  : 'border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground'
              )}
            >
              <mode.icon aria-hidden="true" className="h-3.5 w-3.5" />
              {mode.label}
            </button>
          )
        })}
        <div className="relative shrink-0">
          <button
            type="button"
            aria-pressed={searchMode === 'mcp'}
            aria-expanded={isMcpOpen}
            aria-controls="composer-mcp-options"
            title={searchMode === 'mcp' ? mcpOptions.find(option => option.id === selectedMcp)?.label : undefined}
            onClick={() => {
              if (searchMode === 'mcp') {
                setSearchMode('')
                setIsMcpOpen(false)
              } else {
                setSearchMode('mcp')
                setIsMcpOpen(true)
              }
            }}
            className={cn(
              'flex h-8 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
              searchMode === 'mcp'
                ? 'border-primary/25 bg-primary/10 text-primary shadow-xs'
                : 'border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground'
            )}
          >
            <Plug aria-hidden="true" className="h-3.5 w-3.5" />
            MCP
            <ChevronDown aria-hidden="true" className="h-3 w-3" />
          </button>
          {isMcpOpen && (
            <div id="composer-mcp-options" className="absolute right-0 top-full z-50 mt-2 max-h-[min(18rem,calc(100dvh-8rem))] w-44 overflow-y-auto rounded-lg border border-border/80 bg-popover p-1.5 text-popover-foreground shadow-elevated">
              {mcpOptions.map(option => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={selectedMcp === option.id && searchMode === 'mcp'}
                  onClick={() => {
                    setSelectedMcp(option.id)
                    setSearchMode('mcp')
                    setIsMcpOpen(false)
                  }}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset',
                    selectedMcp === option.id && searchMode === 'mcp' && 'bg-primary/10 font-medium text-primary'
                  )}
                >
                  {option.label}
                  {selectedMcp === option.id && <Check aria-hidden="true" className="h-3.5 w-3.5" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          'relative rounded-2xl border border-border/75 bg-card shadow-surface transition-[border-color,box-shadow] focus-within:border-primary/35 focus-within:ring-2 focus-within:ring-primary/10',
          isDragging && 'border-primary bg-primary/5 ring-2 ring-primary/25'
        )}
      >
        {isDragging && (
          <div className="absolute inset-0 z-50 flex items-center justify-center rounded-2xl bg-card/95 backdrop-blur-[2px]">
            <div className="flex items-center gap-3 text-sm font-medium text-primary">
              <Paperclip className="h-5 w-5" />
              <span>{t('dropFilesHere')}</span>
            </div>
          </div>
        )}

        <input type="file" multiple className="hidden" ref={fileInputRef} onChange={handleFileSelect} />
        {attachments.length > 0 && (
          <div className="flex gap-2 overflow-x-auto px-4 pb-1 pt-3">
            {attachments.map((file, index) => (
              <div key={index} className="group/attachment relative shrink-0 pr-1 pt-1">
                <div className="flex max-w-[220px] items-center gap-2 rounded-md border border-border/80 bg-surface-subtle px-2 py-1.5 text-xs font-medium">
                  {file.type.startsWith('image/') ? (
                    <div className="h-8 w-8 shrink-0 overflow-hidden rounded bg-card">
                      <AttachmentImage file={file} />
                    </div>
                  ) : (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-card text-muted-foreground">
                      <FileIcon className="h-4 w-4" />
                    </div>
                  )}
                  <span className="truncate pr-2" title={file.name}>{file.name}</span>
                </div>
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => removeAttachment(index)}
                  className="absolute right-0 top-0 flex h-5 w-5 items-center justify-center rounded border border-border bg-card text-muted-foreground opacity-100 shadow-xs transition-opacity hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 md:opacity-0 md:group-hover/attachment:opacity-100 md:group-focus-within/attachment:opacity-100"
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
          placeholder={searchMode === 'mcp' ? `${mcpOptions.find(option => option.id === selectedMcp)?.label || 'MCP'}...` : t('askAnything')}
          aria-label={t('askAnything')}
          disabled={isLoading || awaitingApproval}
          rows={1}
          className="block max-h-[200px] min-h-[72px] w-full resize-none bg-transparent px-4 pb-2 pt-4 text-base leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />

        <div className="flex items-center justify-end px-3 pb-3 pt-1">
          <div className="flex shrink-0 items-center gap-1">
            <Button type="button" variant="ghost" size="icon" aria-label="Attach files" onClick={() => fileInputRef.current?.click()} className="text-muted-foreground hover:text-foreground">
              <Paperclip className="h-4 w-4" />
            </Button>
            {!isLoading && (
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={isListening ? 'Stop recording' : 'Record voice message'}
                aria-pressed={isListening}
                onClick={isListening ? stopListening : startListening}
                disabled={isProcessingAudio}
                className={cn(
                  'text-muted-foreground hover:text-foreground',
                  isListening && 'bg-destructive-surface text-destructive hover:bg-destructive/15',
                  isProcessingAudio && 'text-info'
                )}
              >
                {isProcessingAudio ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </Button>
            )}
            {canStop ? (
              <Button type="button" size="icon" variant="outline" aria-label={t('stopGenerating')} disabled={isStopping} onClick={onStop} className="border-destructive-border text-destructive hover:bg-destructive-surface hover:text-destructive">
                <div className="h-2.5 w-2.5 rounded-sm bg-current" />
              </Button>
            ) : (
              <Button type="button" size="icon" aria-label={t('sendMessage')} onClick={onSubmit} disabled={isLoading || awaitingApproval || (!input.trim() && attachments.length === 0)}>
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>

      <p className="mt-2 px-2 text-center text-xs leading-5 text-muted-foreground">
        {t('aiCanMakeMistakes')}
      </p>
    </div>
  )
}
