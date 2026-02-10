'use client'

import React, { useState, memo, useMemo, useCallback, useRef } from 'react'
import Image from 'next/image'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import dynamic from 'next/dynamic'
import { cn } from '@/lib/utils'
import { Bot, Check, Copy, Pencil, Volume2, VolumeX, Loader2, FolderPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DataTableView } from './DataTableView'
import { ErrorBoundary } from 'react-error-boundary'
import { toast } from 'sonner'
import { Message, Artifact } from '@/types/chat'
import { ThinkingProcess } from './message/ThinkingProcess'
import { CodeBlock } from './message/CodeBlock'
import { CitationBadge } from './message/CitationBadge'
import { SourceInspector } from './message/SourceInspector'
import { useArtifacts } from '@/hooks/useArtifacts'
import { getApiBaseUrl } from '@/lib/api'
import { useMarkdownWorker } from '@/hooks/useMarkdownWorker'

// Lazy load MermaidBlock as it's a heavy dependency
const MermaidBlock = dynamic(() => import('./MermaidBlock').then(mod => mod.MermaidBlock), {
  loading: () => (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center border rounded-lg bg-muted/10">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>Loading visualization...</span>
    </div>
  ),
  ssr: false
})

function ErrorFallback({ error }: { error: Error }) {
  return (
    <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-xs">
      <p className="font-semibold">Visualization Error</p>
      <pre className="mt-1 opacity-70">{error.message}</pre>
    </div>
  )
}

// Helper to normalize LaTeX delimiters
const preprocessContent = (content: string) => {
  if (!content) return ''
  return content
    .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$') // \( ... \) -> $ ... $
    .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$') // \[ ... \] -> $$ ... $$
}

interface MessageItemProps {
  message: Message
  onEdit?: (id: string, newContent: string) => void
}

const MessageItemBase = ({ message, onEdit }: MessageItemProps) => {
  const isUser = (message.role || '').toLowerCase() === 'user'
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(message.content)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isTTSLoading, setIsTTSLoading] = useState(false)
  const [audioRef, setAudioRef] = useState<HTMLAudioElement | null>(null)
  const [activeCitation, setActiveCitation] = useState<string | null>(null)
  const sourceInspectorRef = useRef<HTMLDivElement | null>(null)

  const { saveArtifact } = useArtifacts()

  // Offload heavy processing to worker for long messages
  const shouldUseWorker = (message.content?.length || 0) > 2000
  const { processedContent, isProcessing } = useMarkdownWorker(message.content || '', shouldUseWorker)

  // Memoize preprocessed content for Math rendering
  // If worker ran, it's already preprocessed. If not, we do it here.
  // The regex is idempotent so it's safe to run again.
  const displayContent = useMemo(() => {
    if (isProcessing) return '' // or show fallback/partial?
    return preprocessContent(shouldUseWorker ? processedContent : (message.content || ''))
  }, [message.content, processedContent, isProcessing, shouldUseWorker])

  // Memoized handlers
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    toast.success('Message copied')
    setTimeout(() => setCopied(false), 2000)
  }, [message.content])

  const handleSaveToLibrary = useCallback(() => {
    saveArtifact({
      type: 'text',
      title: message.content.slice(0, 30) + '...',
      content: message.content,
      tags: ['Saved Chat']
    })
    setSaved(true)
    toast.success('Saved to Library')
    setTimeout(() => setSaved(false), 2000)
  }, [message.content, saveArtifact])

  const handleSpeak = async () => {
    // If playing, stop
    if (isPlaying && audioRef) {
      audioRef.pause()
      audioRef.currentTime = 0
      setIsPlaying(false)
      return
    }

    // Extract plain text (remove markdown)
    const plainText = message.content
      .replace(/```[\s\S]*?```/g, '') // remove code blocks
      .replace(/`[^`]+`/g, '') // remove inline code
      .replace(/[\[^\]\]+\]\([^)]+\)/g, '$1') // links -> text
      .replace(/[#*_~]/g, '') // remove markdown symbols
      .replace(/\n+/g, ' ') // newlines -> spaces
      .trim()

    if (!plainText) {
      toast.error('No readable content found')
      return
    }

    setIsTTSLoading(true)

    // Retry with exponential backoff
    const MAX_RETRIES = 3
    let lastError: Error | null = null

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(`${getApiBaseUrl()}/api/tts/synthesize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: plainText.slice(0, 2000),
            voice: 'longxiaochun'
          })
        })

        const result = await response.json()

        if (result.success && result.audio) {
          const audio = new Audio(`data:audio/mp3;base64,${result.audio}`)
          setAudioRef(audio)
          audio.onended = () => setIsPlaying(false)
          audio.onerror = () => {
            toast.error('Audio playback failed')
            setIsPlaying(false)
          }
          await audio.play()
          setIsPlaying(true)
          setIsTTSLoading(false)
          return
        }

        if (response.status === 503 && attempt < MAX_RETRIES - 1) {
          // Service temporarily unavailable, retry with backoff
          await new Promise(r => setTimeout(r, Math.pow(2, attempt) * 1000))
          continue
        }

        if (response.status !== 503) {
          toast.error(result.error || 'TTS failed')
          break
        }
      } catch (error) {
        lastError = error as Error
        if (attempt < MAX_RETRIES - 1) {
          await new Promise(r => setTimeout(r, Math.pow(2, attempt) * 1000))
          continue
        }
      }
    }

    // All retries exhausted, fallback to browser TTS
    console.error('TTS failed after retries:', lastError)
    fallbackToWebTTS(plainText)
    setIsTTSLoading(false)
  }

  const fallbackToWebTTS = (text: string) => {
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(text.slice(0, 500))
      utterance.lang = 'en-US' // Default to EN or check locale
      utterance.onend = () => setIsPlaying(false)
      utterance.onerror = () => {
        toast.error('Browser TTS failed')
        setIsPlaying(false)
      }
      speechSynthesis.speak(utterance)
      setIsPlaying(true)
    } else {
      toast.error('Browser TTS not supported')
    }
  }

  const handleSaveEdit = () => {
    if (onEdit && editContent.trim() !== message.content) {
      onEdit(message.id, editContent)
    }
    setIsEditing(false)
  }

  const tools = message.toolInvocations || []
  const hasTools = tools.length > 0
  const isThinking = tools.some(t => t.state === 'running')
  const hasSources = !isUser && (message.sources?.length || 0) > 0

  const handleCitationClick = useCallback((citation: string) => {
    setActiveCitation(prev => (prev === citation ? null : citation))
    sourceInspectorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [])

  return (
    <div
      className={cn(
        'group flex w-full gap-2 py-4',
        'animate-fade-in-up',
        isUser ? 'justify-end' : 'justify-start'
      )}
      style={{ animationDelay: '0.05s' }}
    >
      {/* Bot Avatar - Removed */}
      <div className={cn(
        'flex flex-col',
        isUser ? "max-w-[90%] md:max-w-[85%] items-end ml-auto" : "w-full max-w-full items-start mr-auto",
      )}>

        {/* Thinking Process */}
        {!isUser && hasTools && !isEditing && (
          <ThinkingProcess tools={tools} isThinking={isThinking} />
        )}

        {/* Message Bubble OR Edit Mode */}
        {isEditing ? (
          <div className="w-full bg-muted/30 p-4 rounded-xl border border-primary/20 shadow-sm animate-in fade-in zoom-in-95">
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              className="w-full bg-transparent resize-none focus:outline-none min-h-[100px] text-sm leading-relaxed"
            />
            <div className="flex justify-end gap-2 mt-3">
              <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>Cancel</Button>
              <Button size="sm" onClick={handleSaveEdit}>Save & Submit</Button>
            </div>
          </div>
        ) : (
          <div className={cn(
            "relative px-5 py-3.5 shadow-sm transition-all duration-300",
            isUser
              ? "message-user"
              : "message-assistant hover:shadow-glow-sm"
          )}
          >
            <div className={cn(
              "prose prose-neutral dark:prose-invert max-w-none break-words leading-7",
              "text-[15px] md:text-base" // Slightly larger font
            )}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  pre: ({ children }) => <>{children}</>,
                  p: ({ node, children, ...props }) => (
                    <p className="mb-2 last:mb-0 leading-7" {...props}>
                      {React.Children.map(children, child => {
                        if (typeof child === 'string') {
                          const parts = child.split(/(\[\d+\])/g)
                          return parts.map((part, i) => {
                            const match = part.match(/^\[(\d+)\]$/)
                            if (match) {
                              return (
                                <CitationBadge
                                  key={i}
                                  num={match[1]}
                                  active={activeCitation === match[1]}
                                  onClick={handleCitationClick}
                                />
                              )
                            }
                            return part
                          })
                        }
                        return child
                      })}
                    </p>
                  ),
                  code: ({ node, className, children, ...props }: any) => {
                    const match = /language-(\w+)/.exec(className || '')
                    const isInline = !match && !String(children).includes('\n')
                    const content = String(children).replace(/\n$/, '')

                    // Check for Mermaid
                    if (match && match[1] === 'mermaid') {
                      return (
                        <ErrorBoundary FallbackComponent={ErrorFallback}>
                          <MermaidBlock code={content} />
                        </ErrorBoundary>
                      )
                    }

                    // Check for JSON/CSV
                    if (match && (match[1] === 'json' || match[1] === 'csv')) {
                      return (
                        <div className="flex flex-col gap-2">
                          <ErrorBoundary FallbackComponent={() => null}>
                            <DataTableView data={content} type={match[1] as 'json' | 'csv'} />
                          </ErrorBoundary>
                          <CodeBlock language={match[1]} value={content} />
                        </div>
                      )
                    }

                    if (isInline) {
                      return (
                        <code className="bg-black/10 dark:bg-black/30 px-1.5 py-0.5 rounded text-sm font-mono break-words whitespace-pre-wrap" {...props}>
                          {children}
                        </code>
                      )
                    }

                    return (
                      <CodeBlock language={match ? match[1] : 'text'} value={content} />
                    )
                  },
                  a: ({ node, ...props }) => (
                    <a className={cn("underline underline-offset-2 font-medium", isUser ? "text-white" : "text-primary hover:text-primary/80")} {...props} />
                  )
                }}
              >
                {displayContent || (hasTools ? "" : "")}
              </ReactMarkdown>

              {message.attachments && message.attachments.length > 0 && (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {message.attachments.map((att, idx) => (
                    <div key={idx} className="rounded-md overflow-hidden border bg-background/60">
                      {att.preview ? (
                        <Image
                          src={att.preview}
                          alt={att.name || `attachment-${idx}`}
                          width={640}
                          height={360}
                          unoptimized
                          loading="lazy"
                          decoding="async"
                          className="w-full h-auto max-h-40 object-cover bg-white blur-sm transition-all duration-300"
                          onLoad={(e) => e.currentTarget.classList.remove('blur-sm')}
                        />
                      ) : (
                        <div className="p-3 text-xs text-muted-foreground">
                          {att.name || 'Image attachment'}
                        </div>
                      )}
                      <div className="px-2 py-1 text-[10px] text-muted-foreground truncate border-t border-border/50">
                        {att.name || att.mime || 'Image'}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {hasSources && (
                <div ref={sourceInspectorRef}>
                  <SourceInspector
                    sources={message.sources || []}
                    activeCitation={activeCitation}
                    onSelectCitation={setActiveCitation}
                  />
                </div>
              )}

              {/* Typing Indicator for AI if no content yet */}
              {!isUser && !message.content && !hasTools && (
                <span className="animate-pulse">...</span>
              )}

              {/* Worker Processing Indicator */}
              {isProcessing && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2 animate-pulse">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Processing content...</span>
                </div>
              )}
            </div>

            {/* Actions: Copy, Speak & Edit */}
            <div className="absolute -bottom-6 right-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
              {/* Copy Button - Available for both roles */}
              {message.content && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  onClick={handleCopy}
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
              )}

              {!isUser && message.content && (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className={cn(
                      "h-6 w-6 text-muted-foreground hover:text-foreground",
                      isPlaying && "text-primary"
                    )}
                    onClick={handleSpeak}
                    disabled={isTTSLoading}
                  >
                    {isTTSLoading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : isPlaying ? (
                      <VolumeX className="h-3.5 w-3.5" />
                    ) : (
                      <Volume2 className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                    onClick={handleSaveToLibrary}
                  >
                    {saved ? <Check className="h-3.5 w-3.5 text-green-500" /> : <FolderPlus className="h-3.5 w-3.5" />}
                  </Button>
                </>
              )}
              {isUser && onEdit && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground ml-auto"
                  onClick={() => setIsEditing(true)}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export const MessageItem = memo(MessageItemBase)
