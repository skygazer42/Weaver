'use client'

import React, { useState, memo } from 'react'
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
import { useArtifacts } from '@/hooks/useArtifacts'

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

interface MessageItemProps {
    message: Message
    onEdit?: (id: string, newContent: string) => void
}

const MessageItemBase = ({ message, onEdit }: MessageItemProps) => {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(message.content)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isTTSLoading, setIsTTSLoading] = useState(false)
  const [audioRef, setAudioRef] = useState<HTMLAudioElement | null>(null)

  const { saveArtifact } = useArtifacts()

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

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/tts/synthesize`, {
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
        setAudioRef(audio)

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
  const hasTools = tools.length > 0
  const isThinking = tools.some(t => t.state === 'running')

  return (
    <div
      className={cn(
        'group flex w-full gap-2 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
            {/* Bot Avatar - Removed */}
            <div className={cn(
                'flex flex-col max-w-[90%] md:max-w-[85%]', 
                isUser ? 'items-end' : 'items-start',          // If editing, take full width available
          isEditing && "w-full max-w-full md:max-w-full"
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
                "relative px-5 py-3.5 shadow-sm",
                isUser
                  ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
                  : "bg-muted/30 border text-foreground rounded-2xl rounded-tl-sm backdrop-blur-sm"
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
                        pre: ({node, ...props}) => (
                            <pre className="not-prose my-2 w-full overflow-hidden rounded-lg border bg-zinc-950 dark:bg-zinc-900" {...props} />
                        ),
                        p: ({node, children, ...props}) => (
                             <p className="mb-2 last:mb-0 leading-7" {...props}>
                                {React.Children.map(children, child => {
                                    if (typeof child === 'string') {
                                        const parts = child.split(/(\[d+]) /g) 
                                        return parts.map((part, i) => {
                                            const match = part.match(/^\\\\[(\\d+)\\]$/)
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
                                    <code className="bg-black/10 dark:bg-black/30 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                                        {children}
                                    </code>
                               )
                            }

                            return (
                                <CodeBlock language={match ? match[1] : 'text'} value={content} />
                            )
                        },
                        a: ({node, ...props}) => (
                            <a className={cn("underline underline-offset-2 font-medium", isUser ? "text-white" : "text-primary hover:text-primary/80")} {...props} />
                        )
                    }}
                >
                  {message.content || (hasTools ? "" : "")}
                </ReactMarkdown>

                {message.attachments && message.attachments.length > 0 && (
                  <div className="mt-3 grid grid-cols-2 gap-2">
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
                        <div className="px-2 py-1 text-[10px] text-muted-foreground truncate border-t border-border/50">
                          {att.name || att.mime || 'Image'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Typing Indicator for AI if no content yet */}
                {!isUser && !message.content && !hasTools && (
                   <span className="animate-pulse">...</span>
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