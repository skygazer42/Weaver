'use client'

import React, { useRef, useState, memo } from 'react'
import Image from 'next/image'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import dynamic from 'next/dynamic'
import { cn } from '@/lib/utils'
import { Check, Copy, Pencil, Volume2, VolumeX, Loader2, FolderPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DataTableView } from './DataTableView'
import { ErrorBoundary } from 'react-error-boundary'
import { toast } from 'sonner'
import { Message } from '@/types/chat'
import { ThinkingProcess } from './message/ThinkingProcess'
import { CodeBlock } from './message/CodeBlock'
import { CitationBadge } from './message/CitationBadge'
import { useArtifacts } from '@/hooks/useArtifacts'
import { getApiBaseUrl, getArtifactDownloadUrl } from '@/lib/api'

// Lazy load MermaidBlock as it's a heavy dependency
const MermaidBlock = dynamic(() => import('./MermaidBlock').then(mod => mod.MermaidBlock), {
    loading: () => (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-border/70 bg-surface-subtle py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Loading visualization...</span>
        </div>
    ),
    ssr: false 
})

function ErrorFallback({ error }: { error: Error }) {
    return (
        <div className="rounded-lg border border-destructive-border bg-destructive-surface p-4 text-xs text-destructive">
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

// Keep code and table state when surrounding chat controls rerender.
const MarkdownContent = memo(function MarkdownContent({ content, workspaceId }: {
  content: string
  workspaceId?: string
}) {
  return (
    <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        disallowedElements={workspaceId ? ['img'] : undefined}
        urlTransform={(url) => workspaceId && url.startsWith('/api/workspaces/' + workspaceId + '/')
            ? getArtifactDownloadUrl(url) ?? ''
            : defaultUrlTransform(url)}
        components={{
            pre: ({children}) => <>{children}</>,
            p: ({node, children, ...props}) => (
                 <p className="mb-2 last:mb-0 leading-7" {...props}>
                    {React.Children.map(children, child => {
                        if (typeof child === 'string') {
                            const parts = child.split(/(\[\d+\])/g)
                            return parts.map((part, i) => {
                                const match = part.match(/^\[(\d+)\]$/)
                                if (match) {
                                    return <CitationBadge key={i} num={match[1]} />
                                }
                                return part
                            })
                        }
                        return child
                    })}
                 </p>
            ),
            code: ({node, className, children, ...props}: any) => {
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
                                <DataTableView data={content} type={match[1] as 'json'|'csv'} />
                            </ErrorBoundary>
                            <CodeBlock language={match[1]} value={content} />
                        </div>
                    )
                }

                if (isInline) {
                   return (
                        <code className="whitespace-pre-wrap break-words font-mono" {...props}>
                            {children}
                        </code>
                   )
                }

                return (
                    <CodeBlock language={match ? match[1] : 'text'} value={content} />
                )
            },
            a: ({node, ...props}) => (
                <a className="font-medium text-primary underline underline-offset-4 hover:text-primary/80" {...props} />
            )
        }}
    >
      {content}
    </ReactMarkdown>
  )
})

interface MessageItemProps {
    message: Message
    onEdit?: (id: string, newContent: string) => void
    workspaceId?: string
}

const MessageItemBase = ({ message, onEdit, workspaceId }: MessageItemProps) => {
  const isUser = (message.role || '').toLowerCase() === 'user'
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(message.content)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isTTSLoading, setIsTTSLoading] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const { saveArtifact } = useArtifacts(workspaceId)

  // Preprocess content for Math rendering
  const displayContent = preprocessContent(message.content || '')

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    toast.success('Message copied')
    setTimeout(() => setCopied(false), 2000)
  }

  const handleSaveToLibrary = () => {
    saveArtifact({
        type: 'text',
        title: message.content.slice(0, 30) + '...',
        content: message.content,
        tags: ['Saved Chat']
    })
    setSaved(true)
    toast.success('Saved to Library')
    setTimeout(() => setSaved(false), 2000)
  }

  const handleSpeak = async () => {
    // If playing, stop
    if (isPlaying && audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
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

    try {
      const response = await fetch(`${getApiBaseUrl()}/api/tts/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: plainText.slice(0, 2000), // limit length
          voice: 'longxiaochun'
        })
      })

      const result = await response.json()

      if (result.success && result.audio) {
        // Create audio and play
        const audio = new Audio(`data:audio/mp3;base64,${result.audio}`)
        audioRef.current = audio

        audio.onended = () => {
          setIsPlaying(false)
        }

        audio.onerror = () => {
          toast.error('Audio playback failed')
          setIsPlaying(false)
        }

        await audio.play()
        setIsPlaying(true)
      } else if (response.status === 503) {
        // TTS service unavailable, fallback to browser
        fallbackToWebTTS(plainText)
      } else {
        toast.error(result.error || 'TTS failed')
      }
    } catch (error) {
      console.error('TTS error:', error)
      // Fallback
      fallbackToWebTTS(plainText)
    } finally {
      setIsTTSLoading(false)
    }
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
  const processEvents = message.processEvents || []
  const isThinking = Boolean(message.isStreaming)
  const sources = (message.sources ?? []).filter(({ url }) => /^https?:\/\//i.test(url))
  const showThinking = !isUser && !isEditing && (isThinking || tools.length > 0 || processEvents.length > 0)
  const hideAssistantBubble =
    !isUser && !isEditing && !displayContent.trim() && sources.length === 0 && (isThinking || !!message.runStatus)


  return (
    <div
      className={cn(
        'group flex w-full gap-3 py-5 sm:py-6',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
            <div className={cn(
                'flex min-w-0 flex-col',
                isUser ? "max-w-[90%] md:max-w-[85%] items-end ml-auto" : "w-full max-w-full items-start mr-auto",
      )}>
        {!isUser && (
          <div className="mb-3 flex items-center gap-2.5 text-sm font-semibold tracking-tight text-foreground">
            <span className="flex h-6 w-6 items-center justify-center overflow-hidden rounded-md border border-border/80 bg-white">
              <Image src="/logo.png" alt="" width={20} height={20} />
            </span>
            Weaver
          </div>
        )}
        
        {/* Thinking Process */}
        {showThinking && (
          <ThinkingProcess
            tools={tools}
            artifacts={message.artifacts}
            events={processEvents}
            metrics={message.metrics}
            startedAt={message.createdAt}
            completedAt={message.completedAt}
            isThinking={isThinking}
          />
        )}

        {/* Message Bubble OR Edit Mode */}
        {isEditing ? (
            <div className="w-full rounded-lg border border-primary/40 bg-card p-4 shadow-surface">
                <textarea 
                    aria-label="Edit message"
                    value={editContent} 
                    onChange={e => setEditContent(e.target.value)} 
                    className="w-full bg-transparent resize-none focus:outline-none min-h-[100px] text-sm leading-relaxed"
                />
                <div className="flex justify-end gap-2 mt-3">
                    <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>Cancel</Button>
                    <Button size="sm" onClick={handleSaveEdit}>Save & Submit</Button>
                </div>
            </div>
        ) : hideAssistantBubble ? null : (
          <>
            <div className={cn(
                "relative min-w-0",
                isUser
                  ? "rounded-xl rounded-tr-sm bg-primary px-4 py-3 text-primary-foreground shadow-surface dark:border dark:border-primary/30 dark:bg-primary/20 dark:text-foreground"
                  : "w-full text-foreground"
              )}
            >
              <div className={cn(
                  "prose max-w-none break-words text-[15px] leading-7",
                  isUser && "prose-on-primary"
              )}>
                <MarkdownContent content={displayContent} workspaceId={workspaceId} />

                {sources.length > 0 && (
                  <details open={message.runStatus === 'insufficient_evidence'} className="not-prose mt-5 overflow-hidden rounded-lg border border-border/80 bg-card text-sm text-muted-foreground shadow-xs">
                    <summary className="cursor-pointer px-3.5 py-2.5 font-medium text-foreground transition-colors hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset">Sources ({sources.length})</summary>
                    <ol className="ml-8 list-decimal space-y-2 border-t border-border/70 py-3 pr-4 marker:text-muted-foreground">
                      {sources.map((source, index) => (
                        <li key={`${source.url}-${index}`}>
                          <a href={source.url} target="_blank" rel="noreferrer" className="break-words text-primary underline decoration-primary/30 underline-offset-4 hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">{source.title || source.url}</a>
                        </li>
                      ))}
                    </ol>
                  </details>
                )}

                {message.attachments && message.attachments.length > 0 && (
                  <div className="not-prose mt-3 grid grid-cols-2 gap-2">
                    {message.attachments.map((att, idx) => (
                      <div key={idx} className="rounded-md overflow-hidden border bg-background/60">
                        {att.preview ? (
                          <img
                            src={att.preview}
                            alt={att.name || `attachment-${idx}`}
                            className="w-full h-auto max-h-40 object-cover bg-white"
                          />
                        ) : (
                          <div className="p-3 text-xs text-muted-foreground">
                            {att.name || 'Image attachment'}
                          </div>
                        )}
                        <div className="truncate border-t border-border/70 px-2 py-1.5 text-xs text-muted-foreground">
                          {att.name || att.mime || 'Image'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Intentionally no typing indicator here; the Thinking row covers streaming state. */}
              </div>
            </div>

              {/* Actions: Copy, Speak & Edit */}
              <div className={cn("mt-2 flex items-center gap-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100", (copied || saved || isPlaying || isTTSLoading) && "opacity-100")}>
                 {/* Copy Button - Available for both roles */}
                 {message.content && (
                    <Button
                        variant="ghost"
                        size="icon"
                        type="button"
                        aria-label={copied ? 'Message copied' : 'Copy message'}
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
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
                          type="button"
                          aria-label={isPlaying ? 'Stop speaking' : 'Speak message'}
                          className={cn(
                            "h-7 w-7 text-muted-foreground hover:text-foreground",
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
                          type="button"
                          aria-label={saved ? 'Saved to Library' : 'Save to Library'}
                          className="h-7 w-7 text-muted-foreground hover:text-foreground"
                          onClick={handleSaveToLibrary}
                      >
                          {saved ? <Check className="h-3.5 w-3.5 text-success" /> : <FolderPlus className="h-3.5 w-3.5" />}
                      </Button>
                    </>
                 )}
                 {isUser && onEdit && (
                    <Button 
                        variant="ghost" 
                        size="icon" 
                        type="button"
                        aria-label="Edit message"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        onClick={() => setIsEditing(true)}
                    >
                        <Pencil className="h-3.5 w-3.5" />
                    </Button>
                 )}
              </div>
          </>
        )}
      </div>
    </div>
  )
}

export const MessageItem = memo(MessageItemBase)
