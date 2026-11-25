'use client'

import React, { useRef, useEffect, useState, useCallback, useId } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ArrowUp, Globe, Bot, Paperclip, X, Mic, MicOff, ChevronDown, Settings2, Trash2, File as FileIcon, Bug, BookOpen, PenTool, TestTube, Plug, Rocket, ListChecks, Plus } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { createFilePreview } from '@/lib/file-utils'
import { getApiBaseUrl } from '@/lib/api'
import { useMcpConfig } from '@/hooks/useMcpConfig'

interface ChatInputProps {
  input: string
  setInput: React.Dispatch<React.SetStateAction<string>>
  attachments: File[]
  setAttachments: (files: File[]) => void
  onSubmit: (e: React.FormEvent) => void
  researchPlan: string[]
  setResearchPlan: (topics: string[]) => void
  planReset: number
  isLoading: boolean
  canStop: boolean
  isStopping: boolean
  awaitingApproval: boolean
  onStop: () => void
  searchMode: string
  setSearchMode: (mode: string) => void
  wide?: boolean
  focusSignal?: number
  onOpenSettings?: () => void
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
  researchPlan,
  setResearchPlan,
  planReset,
  isLoading,
  canStop,
  isStopping,
  awaitingApproval,
  onStop,
  searchMode,
  setSearchMode,
  wide = false,
  focusSignal = 0,
  onOpenSettings,
}: ChatInputProps) {
  const { t } = useI18n()
  const { config: mcpConfig, isLoading: mcpLoading, error: mcpError, refresh: refreshMcp } = useMcpConfig()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wasLoading = useRef(isLoading)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mcpContainerRef = useRef<HTMLDivElement>(null)
  const commandMenuRef = useRef<HTMLDivElement>(null)
  const [showCommandMenu, setShowCommandMenu] = useState(false)
  const [isMcpOpen, setIsMcpOpen] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [planState, setPlanState] = useState({ reset: planReset, open: false })
  const planId = useId()
  const showPlan = searchMode === 'deep' || searchMode === 'ultra'
  const planOpen = showPlan && planState.reset === planReset && planState.open

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

  useEffect(() => {
    if (focusSignal <= 0) return
    const el = textareaRef.current
    if (!el) return
    el.focus()
    const end = el.value.length
    el.setSelectionRange(end, end)
  }, [focusSignal])

  useEffect(() => {
    if (!isMcpOpen && !showCommandMenu) return
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (isMcpOpen && mcpContainerRef.current && !mcpContainerRef.current.contains(target)) {
        setIsMcpOpen(false)
      }
      if (showCommandMenu && commandMenuRef.current && !commandMenuRef.current.contains(target)) {
        setShowCommandMenu(false)
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [isMcpOpen, showCommandMenu])

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

  const modes = [
    { id: 'web', label: t('web'), icon: Globe },
    { id: 'agent', label: t('agent'), icon: Bot },
    { id: searchMode === 'deep' ? 'deep' : 'ultra', label: t('ultra'), icon: Rocket },
  ]

  const commands = [
      { id: 'agent', label: t('agentMode'), icon: Bot, desc: t('commandAgentDesc') },
      { id: 'ultra', label: t('ultra'), icon: Rocket, desc: t('commandUltraDesc') },
      { id: 'web', label: t('webMode'), icon: Globe, desc: t('commandWebDesc') },
      { id: 'fix', label: t('commandFix'), icon: Bug, desc: t('commandFixDesc') },
      { id: 'explain', label: t('commandExplain'), icon: BookOpen, desc: t('commandExplainDesc') },
      { id: 'refactor', label: t('commandRefactor'), icon: PenTool, desc: t('commandRefactorDesc') },
      { id: 'test', label: t('commandTest'), icon: TestTube, desc: t('commandTestDesc') },
      { id: 'clear', label: t('clearChat'), icon: Trash2, desc: t('resetConversation') },
  ]
  
  return (
    <div
      className={cn(
        'relative z-20 mx-auto w-full shrink-0 px-4 pb-4 pt-1 transition-[max-width] duration-200 ease-out motion-reduce:transition-none sm:px-6',
        wide ? 'max-w-4xl' : 'max-w-3xl'
      )}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setShowCommandMenu(false)
          setIsMcpOpen(false)
        }
      }}
    >
      {showCommandMenu && (
        <div ref={commandMenuRef} className="absolute bottom-full left-4 z-50 mb-2 w-80 max-w-[calc(100%-2rem)] overflow-hidden rounded-lg border border-border/80 bg-popover text-popover-foreground shadow-elevated sm:left-6">
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

      {planOpen && <ResearchPlanEditor id={planId} topics={researchPlan} onChange={setResearchPlan} />}

      <div className={cn('mb-2 flex w-full items-center gap-0.5 whitespace-nowrap', showPlan ? 'flex-wrap' : 'flex-nowrap')}>
        {modes.map(mode => {
          const isActive = searchMode === mode.id
          return (
            <button
              key={mode.id}
              type="button"
              aria-label={mode.id === 'agent' ? 'Agent' : mode.id === 'ultra' || mode.id === 'deep' ? t('ultra') : undefined}
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
        <div ref={mcpContainerRef} className="relative shrink-0">
          <div
            className={cn(
              'flex h-8 items-center rounded-lg border text-xs font-medium whitespace-nowrap transition-colors',
              searchMode === 'mcp'
                ? 'border-primary/25 bg-primary/10 text-primary shadow-xs'
                : 'border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground'
            )}
          >
            <button type="button" aria-pressed={searchMode === 'mcp'} onClick={() => { setSearchMode(searchMode === 'mcp' ? '' : 'mcp'); setIsMcpOpen(searchMode !== 'mcp') }} className="flex h-full items-center gap-1.5 rounded-l-lg pl-2 pr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"><Plug aria-hidden="true" className="h-3.5 w-3.5" />{t('mcp')}</button>
            <button type="button" aria-label={t('mcpShowServers')} aria-expanded={isMcpOpen} aria-controls="composer-mcp-options" onClick={() => setIsMcpOpen(!isMcpOpen)} className="flex h-full items-center rounded-r-lg pl-1 pr-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"><ChevronDown aria-hidden="true" className={cn('h-3 w-3 transition-transform', isMcpOpen && 'rotate-180')} /></button>
          </div>
          {isMcpOpen && (
            <div id="composer-mcp-options" aria-label={t('mcpConfiguration')} className="absolute bottom-full left-0 z-50 mb-2 flex max-h-[min(22rem,calc(100dvh-8rem))] w-72 max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-lg border border-border/80 bg-popover text-popover-foreground shadow-elevated max-sm:left-auto max-sm:right-0">
              <div className="shrink-0 border-b border-border/70 bg-surface-subtle px-3 py-2 text-xs font-semibold">{t('mcpConfiguration')}</div>
              <div className="min-h-0 overflow-y-auto p-2">
                {mcpLoading && <p role="status" className="px-2 py-3 text-xs text-muted-foreground">{t('loading')}</p>}
                {mcpError && <div role="alert" className="space-y-2 px-2 py-3 text-xs text-destructive"><p className="whitespace-normal leading-5">{t('mcpLoadFailed')}</p><Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => void refreshMcp()}>{t('mcpRetry')}</Button></div>}
                {!mcpLoading && mcpConfig?.enabled && Object.entries(mcpConfig.servers).map(([serverId, server]) => {
                  const status = mcpConfig.server_statuses.find(item => item.id === serverId)
                  const state = !server.enabled ? 'disabled' : status?.status ?? 'disabled'
                  return <div key={serverId} className="flex items-start gap-2 rounded-md px-2 py-2.5">
                    <span aria-hidden="true" className={cn('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', state === 'connected' ? 'bg-success' : state === 'error' ? 'bg-destructive' : 'bg-muted-foreground')} />
                    <div className="min-w-0 flex-1"><p className="truncate font-mono text-xs font-medium" title={serverId}>{serverId}</p><p className={cn('mt-1 text-xs', state === 'error' ? 'text-destructive' : 'text-muted-foreground')}>{state === 'connected' ? t('mcpConnected') : state === 'error' ? t('error') : t('mcpServerDisabled')}</p></div>
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{t('mcpToolCount').replace('{count}', String(status?.tool_count ?? 0))}</span>
                  </div>
                })}
                {!mcpLoading && mcpConfig && (!mcpConfig.enabled || Object.keys(mcpConfig.servers).length === 0) && <div className="space-y-1 px-2 py-3 text-xs leading-5 whitespace-normal"><p className="font-medium">{mcpConfig.enabled ? t('mcpNoServers') : t('mcpServerDisabled')}</p><p className="text-muted-foreground">{mcpConfig.enabled ? t('mcpNoServersHint') : t('mcpDisabledHint')}</p></div>}
              </div>
              {onOpenSettings && <div className="shrink-0 border-t border-border/70 p-1.5"><Button type="button" variant="ghost" className="h-9 w-full justify-start gap-2 px-2 text-xs" onClick={() => { setIsMcpOpen(false); onOpenSettings() }}><Settings2 className="h-3.5 w-3.5" aria-hidden="true" />{t('mcpManage')}</Button></div>}
            </div>
          )}
        </div>
        {showPlan && (
          <Button type="button" variant="ghost" size="sm" aria-expanded={planOpen} aria-controls={planOpen ? planId : undefined}
            onClick={() => setPlanState({ reset: planReset, open: !planOpen })}
            className={cn('ml-1 h-8 gap-1.5 rounded-lg border px-2 text-xs text-muted-foreground', planOpen ? 'border-primary/25 bg-primary/10 text-primary hover:text-primary' : 'border-border')}>
            <ListChecks aria-hidden="true" className="size-3.5" />{t('studioPlan')}
            {researchPlan.length > 0 && <span className="font-mono text-[11px] tabular-nums">{researchPlan.length}</span>}
          </Button>
        )}
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
          placeholder={searchMode === 'mcp' ? t('mcpAskPlaceholder') : t('askAnything')}
          aria-label={t('askAnything')}
          disabled={isLoading || awaitingApproval}
          rows={1}
          className="block max-h-[200px] min-h-[72px] w-full resize-none bg-transparent px-4 pb-2 pt-4 text-base leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />

        <div className="flex items-center justify-between px-3 pb-3 pt-1">
          <div className="flex shrink-0 items-center">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={t('attachFiles')}
              title={t('attachFiles')}
              onClick={() => fileInputRef.current?.click()}
              className="rounded-full text-muted-foreground hover:text-foreground"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
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
                  'rounded-full text-muted-foreground hover:text-foreground',
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
              <Button
                type="button"
                size="icon"
                variant="outline"
                aria-label={t('stopGenerating')}
                disabled={isStopping}
                onClick={onStop}
                className="h-9 w-9 rounded-full border-destructive-border text-destructive hover:bg-destructive-surface hover:text-destructive"
              >
                <div className="h-2.5 w-2.5 rounded-sm bg-current" />
              </Button>
            ) : (
              <Button
                type="button"
                size="icon"
                aria-label={t('sendMessage')}
                onClick={onSubmit}
                disabled={isLoading || awaitingApproval || (!input.trim() && attachments.length === 0)}
                className="h-9 w-9 rounded-full disabled:bg-muted disabled:text-muted-foreground disabled:opacity-100 disabled:shadow-none"
              >
                <ArrowUp className="h-4 w-4 stroke-[2.25]" />
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

const planPresets = ['studioPlanEvidence', 'studioPlanAlternatives', 'studioPlanRisks', 'studioPlanTrends'] as const

function ResearchPlanEditor({ id, topics, onChange }: { id: string; topics: string[]; onChange: (topics: string[]) => void }) {
  const { t } = useI18n()
  const [draft, setDraft] = useState('')
  const topic = draft.trim()
  const canAdd = topic.length > 0 && !topics.includes(topic)

  return (
    <section id={id} aria-label={t('studioPlanTitle')} className="mb-2 space-y-2 rounded-lg border border-border bg-card p-3">
      <h3 className="text-xs font-semibold text-foreground">{t('studioPlanTitle')}</h3>
      {topics.length > 0 && (
        <ul className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
          {topics.map(item => (
            <li key={item} className="flex max-w-full items-center gap-1 rounded-md bg-primary/10 pl-2 pr-0.5 text-xs text-primary">
              <span className="min-w-0 break-words py-1">{item}</span>
              <Button type="button" variant="ghost" size="icon" className="size-7 shrink-0 hover:text-primary"
                aria-label={t('studioPlanRemove').replace('{topic}', item)} onClick={() => onChange(topics.filter(existing => existing !== item))}>
                <X aria-hidden="true" className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form className="flex items-center gap-2" onSubmit={event => {
        event.preventDefault()
        if (!canAdd) return
        onChange([...topics, topic])
        setDraft('')
      }}>
        <Input aria-label={t('studioPlanDirection')} placeholder={t('studioPlanPlaceholder')} value={draft} maxLength={180}
          onChange={event => setDraft(event.target.value)} className="h-9 min-w-0 text-base sm:text-sm" />
        <Button type="submit" variant="outline" size="sm" disabled={!canAdd} className="h-9 shrink-0 gap-1.5 px-2.5 text-xs">
          <Plus aria-hidden="true" className="size-3.5" />{t('studioPlanAdd')}
        </Button>
      </form>
      <div role="group" aria-label={t('studioPlanPresets')} className="flex flex-wrap gap-1">
        {planPresets.map(key => {
          const preset = t(key)
          return <Button key={key} type="button" variant="ghost" size="sm" disabled={topics.includes(preset)}
            onClick={() => onChange([...topics, preset])} className="h-7 gap-1 bg-surface-subtle px-2 text-xs text-muted-foreground">
            <Plus aria-hidden="true" className="size-3" />{preset}
          </Button>
        })}
      </div>
    </section>
  )
}
