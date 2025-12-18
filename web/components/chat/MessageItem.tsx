'use client'

import React, { useState, memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import dynamic from 'next/dynamic'
import { cn } from '@/lib/utils'
import { Search, Code, Loader2, ChevronDown, Check, Copy, Terminal, Bot, User, BrainCircuit, PenTool, Globe, Pencil, Volume2, VolumeX, Loader } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DataTableView } from './DataTableView'
import { ErrorBoundary } from 'react-error-boundary'
import { toast } from 'sonner'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Message, ToolInvocation } from '@/types/chat'

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
  const [isThinkingOpen, setIsThinkingOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(message.content)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isTTSLoading, setIsTTSLoading] = useState(false)
  const [audioRef, setAudioRef] = useState<HTMLAudioElement | null>(null)

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    toast.success('Message copied')
    setTimeout(() => setCopied(false), 2000)
  }

  const handleSpeak = async () => {
    // 如果正在播放，停止
    if (isPlaying && audioRef) {
      audioRef.pause()
      audioRef.currentTime = 0
      setIsPlaying(false)
      return
    }

    // 提取纯文本（去除 markdown 格式）
    const plainText = message.content
      .replace(/```[\s\S]*?```/g, '') // 移除代码块
      .replace(/`[^`]+`/g, '') // 移除行内代码
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // 链接只保留文字
      .replace(/[#*_~]/g, '') // 移除 markdown 标记
      .replace(/\n+/g, ' ') // 换行改空格
      .trim()

    if (!plainText) {
      toast.error('没有可朗读的内容')
      return
    }

    setIsTTSLoading(true)

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/tts/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: plainText.slice(0, 2000), // 限制长度
          voice: 'longxiaochun'
        })
      })

      const result = await response.json()

      if (result.success && result.audio) {
        // 创建音频并播放
        const audio = new Audio(`data:audio/mp3;base64,${result.audio}`)
        setAudioRef(audio)

        audio.onended = () => {
          setIsPlaying(false)
        }

        audio.onerror = () => {
          toast.error('音频播放失败')
          setIsPlaying(false)
        }

        await audio.play()
        setIsPlaying(true)
      } else if (response.status === 503) {
        // TTS 服务不可用，使用浏览器 TTS
        fallbackToWebTTS(plainText)
      } else {
        toast.error(result.error || '语音合成失败')
      }
    } catch (error) {
      console.error('TTS error:', error)
      // 回退到浏览器 TTS
      fallbackToWebTTS(plainText)
    } finally {
      setIsTTSLoading(false)
    }
  }

  const fallbackToWebTTS = (text: string) => {
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(text.slice(0, 500))
      utterance.lang = 'zh-CN'
      utterance.onend = () => setIsPlaying(false)
      utterance.onerror = () => {
        toast.error('浏览器语音合成失败')
        setIsPlaying(false)
      }
      speechSynthesis.speak(utterance)
      setIsPlaying(true)
    } else {
      toast.error('浏览器不支持语音合成')
    }
  }
  
  const handleSaveEdit = () => {
    if (onEdit && editContent.trim() !== message.content) {
        onEdit(message.id, editContent)
    }
    setIsEditing(false)
  }

  // Filter tools to group them as "Thinking Process"
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
      {/* Bot Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 mt-1">
             <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/50 border shadow-sm">
                <Bot className="h-4 w-4 text-primary" />
             </div>
        </div>
      )}

      <div className={cn(
          'flex flex-col max-w-[85%] md:max-w-[75%]', 
          isUser ? 'items-end' : 'items-start',
          // If editing, take full width available
          isEditing && "w-full max-w-full md:max-w-full"
      )}>
        
        {/* Thinking Process Graph / Accordion */}
        {!isUser && hasTools && !isEditing && (
          <div className="mb-2 ml-1 w-full max-w-md">
             {/* Graph Visualization (Mini) */}
             <div className="flex items-center gap-2 mb-2 px-2 py-1 overflow-hidden">
                <ThinkingNode icon={BrainCircuit} label="Plan" active={tools.length > 0} completed={tools.length > 1} />
                <ThinkingLine active={tools.length > 1} />
                <ThinkingNode icon={Globe} label="Search" active={tools.some(t => t.toolName.includes('search'))} completed={tools.some(t => t.toolName.includes('search') && t.state === 'completed')} />
                <ThinkingLine active={tools.some(t => t.toolName.includes('code'))} />
                <ThinkingNode icon={Code} label="Code" active={tools.some(t => t.toolName.includes('code'))} completed={tools.some(t => t.toolName.includes('code') && t.state === 'completed')} />
                <ThinkingLine active={!isThinking && tools.length > 0} />
                <ThinkingNode icon={PenTool} label="Write" active={!isThinking && tools.length > 0} completed={!isThinking && message.content.length > 0} />
             </div>

             <button 
                onClick={() => setIsThinkingOpen(!isThinkingOpen)}
                className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors bg-muted/30 hover:bg-muted/50 px-2.5 py-1.5 rounded-full border border-border/50"
             >
                {isThinkingOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronDown className="h-3 w-3 -rotate-90" />}
                <span>Process Logs</span>
                {isThinking && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
             </button>

             {isThinkingOpen && (
                <div className="mt-2 pl-2 space-y-2 py-1 border-l-2 border-muted ml-2">
                    {tools.map((tool) => (
                        <ToolInvocationItem key={tool.toolCallId} tool={tool} />
                    ))}
                </div>
             )}
          </div>
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
                "relative px-4 py-3 shadow-sm",
                isUser
                  ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
                  : "bg-muted/30 border text-foreground rounded-2xl rounded-tl-sm backdrop-blur-sm"
              )}
            >
              <div className={cn(
                  "prose prose-sm max-w-none break-words leading-relaxed",
                  isUser ? "prose-invert" : "dark:prose-invert"
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
                                        const parts = child.split(/(\[d+]) /g) // Corrected regex for citation
                                        return parts.map((part, i) => {
                                            const match = part.match(/^\\\[(\\d+)\\\]$/) // Corrected regex for citation
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
              <div className="absolute -bottom-6 left-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                 {!isUser && message.content && (
                    <>
                      <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 text-muted-foreground hover:text-foreground"
                          onClick={handleCopy}
                      >
                          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      </Button>
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

function CitationBadge({ num }: { num: string }) {
    return (
        <TooltipProvider>
            <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                    <sup className="ml-0.5 cursor-pointer text-xs font-bold text-primary hover:underline decoration-dotted select-none">
                        [{num}]
                    </sup>
                </TooltipTrigger>
                <TooltipContent className="max-w-[300px] break-words">
                    <div className="space-y-1">
                        <p className="font-semibold text-xs">Source [{num}]</p>
                        <p className="text-xs text-muted-foreground">Reference details would appear here.</p>
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    )
}

function CodeBlock({ language, value }: { language: string, value: string }) {
    const [copied, setCopied] = useState(false)
  
    const handleCopy = () => {
      navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success('Code copied')
      setTimeout(() => setCopied(false), 2000)
    }
  
    return (
      <div className="relative w-full">
        <div className="flex items-center justify-between px-4 py-1.5 bg-zinc-900 border-b border-white/5">
          <span className="text-xs font-medium text-zinc-400">{language}</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-zinc-400 hover:text-white hover:bg-white/10"
            onClick={handleCopy}
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </Button>
        </div>
        <div className="overflow-x-auto p-4 bg-zinc-950">
          <code className="text-sm font-mono text-zinc-300 whitespace-pre">
            {value}
          </code>
        </div>
      </div>
    )
}

// Graph Components
function ThinkingNode({ icon: Icon, label, active, completed }: { icon: any, label: string, active: boolean, completed: boolean }) {
    return (
        <div className={cn(
            "flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium transition-all duration-300",
            completed ? "bg-primary/10 text-primary ring-1 ring-primary/20" :
            active ? "bg-blue-500/10 text-blue-500 ring-1 ring-blue-500/50 animate-pulse" :
            "bg-muted text-muted-foreground opacity-50"
        )}>
            <Icon className="h-3 w-3" />
            <span>{label}</span>
        </div>
    )
}

function ThinkingLine({ active }: { active: boolean }) {
    return (
        <div className={cn(
            "h-[1px] w-4 transition-colors duration-300",
            active ? "bg-primary/50" : "bg-muted"
        )} />
    )
}

function ToolInvocationItem({ tool }: { tool: ToolInvocation }) {
  const getIcon = () => {
    if (tool.toolName.includes('search')) return <Search className="h-3.5 w-3.5" />
    if (tool.toolName.includes('code')) return <Code className="h-3.5 w-3.5" />
    return <Terminal className="h-3.5 w-3.5" />
  }

  const isRunning = tool.state === 'running'

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground animate-in fade-in slide-in-from-left-1">
      <div className={cn(
          "flex h-4 w-4 items-center justify-center rounded-sm",
          isRunning ? "text-blue-500" : "text-muted-foreground"
      )}>
         {isRunning ? <Loader2 className="h-3 w-3 animate-spin" /> : getIcon()}
      </div>
      <span className="truncate max-w-[200px]">
        {tool.toolName === 'tavily_search' && `Searching: ${tool.args?.query || '...'}`}
        {tool.toolName === 'execute_python_code' && 'Executing Logic...'}
        {!tool.toolName.includes('search') && !tool.toolName.includes('code') && tool.toolName}
      </span>
    </div>
  )
}
