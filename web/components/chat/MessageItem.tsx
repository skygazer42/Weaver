'use client'

import React, { useState, memo, useMemo, useCallback, useRef } from 'react'
import Image from 'next/image'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import dynamic from 'next/dynamic'
import { cn } from '@/lib/utils'
import { BookmarkPlus, Brain, Check, ChevronDown, ClipboardCopy, ListChecks, Loader2, PenLine, Volume2, Square } from '@/components/ui/icons'
import { Button } from '@/components/ui/button'
import { DataTableView } from './DataTableView'
import { ErrorBoundary, type FallbackProps } from 'react-error-boundary'
import { toast } from 'sonner'
import { Message, type MessageSource } from '@/types/chat'
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

function ErrorFallback({ error }: FallbackProps) {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : 'Unknown error'

  return (
    <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-xs">
      <p className="font-semibold">Visualization Error</p>
      <pre className="mt-1 opacity-70">{message}</pre>
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

type AssistantContentBlock =
  | { kind: 'markdown'; content: string }
  | { kind: 'research_plan'; title: string; reasoning: string; queries: string[] }
  | { kind: 'disclosure'; variant: 'plan' | 'reasoning'; title: string; content: string }

function hasCjk(input: string): boolean {
  return /[\u3400-\u9fff]/.test(input)
}

function normalizeHeadingToken(line: string): string {
  const trimmed = String(line || '').trim()
  const withoutHashes = trimmed.replace(/^#{1,6}\s+/, '')
  const withoutBold = withoutHashes.replace(/^\*\*(.+)\*\*$/, '$1')
  const withoutTrailingColon = withoutBold.replace(/[：:]\s*$/, '')
  return withoutTrailingColon.trim().toLowerCase()
}

function parseResearchPlanMessage(content: string): { title: string; reasoning: string; queries: string[] } | null {
  const normalized = String(content || '').replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  const first = (lines[0] || '').trim()

  if (!/^(research plan|研究计划)\s*[:：]\s*$/i.test(first)) return null

  const title = hasCjk(first) ? '研究计划' : 'Research plan'

  const queriesHeadingIndex = lines.findIndex((line, idx) => {
    if (idx === 0) return false
    return /^(queries|查询|搜索查询)\s*[:：]\s*$/i.test(line.trim())
  })

  const reasoningLines =
    queriesHeadingIndex >= 0
      ? lines.slice(1, queriesHeadingIndex)
      : lines.slice(1)

  const queryLines =
    queriesHeadingIndex >= 0
      ? lines.slice(queriesHeadingIndex + 1)
      : []

  const reasoning = reasoningLines.join('\n').trim()
  const queries: string[] = []
  for (const line of queryLines) {
    const trimmed = String(line || '').trim()
    if (!trimmed) continue
    const m = trimmed.match(/^(?:\d+\.|\-|\*|•)\s*(.+)$/)
    const candidate = (m && typeof m[1] === 'string' ? m[1] : trimmed).trim()
    if (candidate) queries.push(candidate)
  }

  return { title, reasoning, queries }
}

const PLAN_TOKENS = new Set([
  'plan',
  'research plan',
  'strategy',
  'approach',
  'queries',
  'steps',
  '计划',
  '规划',
  '研究计划',
  '策略',
  '查询',
  '搜索查询',
  '步骤',
])

const REASONING_TOKENS = new Set([
  'reasoning',
  'thinking',
  'analysis',
  'rationale',
  'notes',
  'method',
  '思考',
  '推理',
  '分析',
  '理由',
  '方法',
])

const BOUNDARY_TOKENS = new Set([
  'answer',
  'final',
  'final answer',
  'response',
  'conclusion',
  '回答',
  '最终',
  '最终回答',
  '结论',
  '结果',
])

const TOKEN_TITLE: Record<string, string> = {
  'research plan': 'Research plan',
  plan: 'Plan',
  strategy: 'Strategy',
  approach: 'Approach',
  queries: 'Queries',
  steps: 'Steps',
  reasoning: 'Reasoning',
  thinking: 'Thinking',
  analysis: 'Analysis',
  rationale: 'Rationale',
  notes: 'Notes',
  method: 'Method',
  // Chinese headings are already user-facing titles.
  研究计划: '研究计划',
  计划: '计划',
  规划: '规划',
  策略: '策略',
  查询: '查询',
  搜索查询: '搜索查询',
  步骤: '步骤',
  思考: '思考',
  推理: '推理',
  分析: '分析',
  理由: '理由',
  方法: '方法',
}

function matchStructuredHeading(line: string): { kind: 'plan' | 'reasoning' | 'boundary'; title: string; inlineContent?: string } | null {
  const trimmed = String(line || '').trim()
  if (!trimmed) return null

  const withoutHashes = trimmed.replace(/^#{1,6}\s+/, '')

  // Inline headings: "Reasoning: ...", "Plan: ...", "Answer: ..."
  const inline = withoutHashes.match(/^(?:\*\*)?(.+?)(?:\*\*)?\s*[:：]\s*(.+)$/)
  if (inline) {
    const label = inline[1] || ''
    const remainder = (inline[2] || '').trim()
    const token = normalizeHeadingToken(label)
    if (!token) return null

    if (PLAN_TOKENS.has(token)) {
      return { kind: 'plan', title: TOKEN_TITLE[token] || (hasCjk(label) ? '计划' : 'Plan'), inlineContent: remainder || undefined }
    }
    if (REASONING_TOKENS.has(token)) {
      return { kind: 'reasoning', title: TOKEN_TITLE[token] || (hasCjk(label) ? '思考' : 'Reasoning'), inlineContent: remainder || undefined }
    }
    if (BOUNDARY_TOKENS.has(token) || token.startsWith('answer') || token.startsWith('final')) {
      return { kind: 'boundary', title: 'Boundary' }
    }
    return null
  }

  // Non-inline headings: require either markdown heading syntax ("## Plan") or a trailing colon ("Plan:")
  const looksLikeHeading = trimmed.startsWith('#') || /[:：]\s*$/.test(withoutHashes)
  if (!looksLikeHeading) return null

  const token = normalizeHeadingToken(withoutHashes)
  if (!token) return null

  const titleFallback = (kind: 'plan' | 'reasoning', raw: string) => {
    if (hasCjk(raw)) return kind === 'plan' ? '计划' : '思考'
    return kind === 'plan' ? 'Plan' : 'Reasoning'
  }

  if (PLAN_TOKENS.has(token)) return { kind: 'plan', title: TOKEN_TITLE[token] || titleFallback('plan', trimmed) }
  if (REASONING_TOKENS.has(token)) return { kind: 'reasoning', title: TOKEN_TITLE[token] || titleFallback('reasoning', trimmed) }
  if (BOUNDARY_TOKENS.has(token)) return { kind: 'boundary', title: 'Boundary' }

  // Prefix matches for common headings like "Final Answer", "Answer (short)".
  if (token.startsWith('answer')) return { kind: 'boundary', title: 'Boundary' }
  if (token.startsWith('final')) return { kind: 'boundary', title: 'Boundary' }

  return null
}

function parseAssistantContentBlocks(content: string): AssistantContentBlock[] {
  const normalized = String(content || '').replace(/\r\n/g, '\n')
  if (!normalized.trim()) return []

  const plan = parseResearchPlanMessage(normalized)
  if (plan) {
    return [
      { kind: 'research_plan', title: plan.title, reasoning: plan.reasoning, queries: plan.queries }
    ]
  }

  const lines = normalized.split('\n')

  type HeadingMatch = {
    lineIndex: number
    rawLine: string
    kind: 'plan' | 'reasoning' | 'boundary'
    title: string
    inlineContent?: string
  }

  const matches: HeadingMatch[] = []
  let inFence = false

  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i] ?? ''
    const trimmed = rawLine.trim()

    if (trimmed.startsWith('```')) {
      inFence = !inFence
      continue
    }
    if (inFence) continue

    const m = matchStructuredHeading(trimmed)
    if (!m) continue

    matches.push({
      lineIndex: i,
      rawLine,
      kind: m.kind,
      title: m.title,
      inlineContent: m.inlineContent,
    })
  }

  // Conservative: only restructure if we have explicit boundaries.
  // This avoids accidentally swallowing the final answer into a "Reasoning" section.
  if (matches.length < 2) {
    return [{ kind: 'markdown', content: normalized }]
  }

  const blocks: AssistantContentBlock[] = []

  const pushMarkdown = (text: string) => {
    const trimmed = String(text || '').trim()
    if (!trimmed) return
    blocks.push({ kind: 'markdown', content: text })
  }

  // Content before the first heading.
  pushMarkdown(lines.slice(0, matches[0]!.lineIndex).join('\n'))

  for (let i = 0; i < matches.length; i += 1) {
    const cur = matches[i]!
    const next = matches[i + 1] || null
    const endLine = next ? next.lineIndex : lines.length
    const sectionBody = lines.slice(cur.lineIndex + 1, endLine).join('\n')
    const sectionText = cur.inlineContent
      ? [cur.inlineContent, sectionBody].filter(Boolean).join('\n')
      : sectionBody

    if (cur.kind === 'plan' || cur.kind === 'reasoning') {
      const contentTrimmed = sectionText.trim()
      if (!contentTrimmed) {
        // If a section is empty, keep the original heading line as markdown.
        pushMarkdown(cur.rawLine)
        continue
      }
      blocks.push({
        kind: 'disclosure',
        variant: cur.kind,
        title: cur.title,
        content: sectionText,
      })
      continue
    }

    // Boundary headings (Answer/Final/Conclusion) remain inline markdown.
    pushMarkdown([cur.rawLine, sectionText].join('\n'))
  }

  return blocks
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

  const hasActionBar = Boolean(message.content)

  const citationSourceByNum = useMemo(() => {
    const map = new Map<string, MessageSource>()
    ;(message.sources || []).forEach((source, idx) => {
      map.set(String(idx + 1), source)
    })
    return map
  }, [message.sources])

  const handleCitationClick = useCallback((citation: string) => {
    setActiveCitation(prev => (prev === citation ? null : citation))
    sourceInspectorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [])

  const renderStringWithCitations = useCallback((text: string, keyPrefix: string) => {
    const parts = text.split(/(\[\d+\])/g)
    return parts.map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/)
      if (!match) return part
      const citationNum = match[1]!
      return (
        <CitationBadge
          key={`${keyPrefix}-${i}`}
          num={citationNum}
          source={citationSourceByNum.get(citationNum)}
          active={activeCitation === citationNum}
          onClick={handleCitationClick}
        />
      )
    })
  }, [activeCitation, citationSourceByNum, handleCitationClick])

  const renderChildrenWithCitations = useCallback((children: React.ReactNode, keyPrefix: string) => {
    return React.Children.map(children, (child, childIdx) => {
      if (typeof child === 'string') {
        return renderStringWithCitations(child, `${keyPrefix}-${childIdx}`)
      }
      return child
    })
  }, [renderStringWithCitations])

  const contentBlocks = useMemo<AssistantContentBlock[]>(() => {
    if (isUser) {
      return [{ kind: 'markdown', content: displayContent }]
    }
    return parseAssistantContentBlocks(displayContent)
  }, [displayContent, isUser])

  const renderMarkdownBlock = useCallback((content: string, keyPrefix: string) => {
    const safe = String(content || '')
    if (!safe.trim()) return null

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          pre: ({ children }) => <>{children}</>,
          h1: ({ children, ...props }) => (
            <h1 className="mt-4 mb-2 text-2xl font-semibold leading-tight text-balance" {...props}>
              {children}
            </h1>
          ),
          h2: ({ children, ...props }) => (
            <h2 className="mt-4 mb-2 text-xl font-semibold leading-tight text-balance" {...props}>
              {children}
            </h2>
          ),
          h3: ({ children, ...props }) => (
            <h3 className="mt-3 mb-1 text-lg font-semibold leading-tight text-balance" {...props}>
              {children}
            </h3>
          ),
          h4: ({ children, ...props }) => (
            <h4 className="mt-3 mb-1 text-base font-semibold leading-tight text-balance" {...props}>
              {children}
            </h4>
          ),
          p: ({ node, children, ...props }) => (
            <p className="mb-2 last:mb-0 leading-7" {...props}>
              {renderChildrenWithCitations(children, `${keyPrefix}-p`)}
            </p>
          ),
          ul: ({ children, ...props }) => (
            <ul className="my-2 ml-5 list-disc space-y-1" {...props}>
              {children}
            </ul>
          ),
          ol: ({ children, ...props }) => (
            <ol className="my-2 ml-5 list-decimal space-y-1" {...props}>
              {children}
            </ol>
          ),
          li: ({ children, ...props }) => (
            <li className="leading-7" {...props}>
              {renderChildrenWithCitations(children, `${keyPrefix}-li`)}
            </li>
          ),
          blockquote: ({ children, ...props }) => (
            <blockquote className="my-3 border-l-2 border-border/60 pl-4 text-muted-foreground" {...props}>
              {children}
            </blockquote>
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
                <code className="bg-muted/60 border border-border/40 px-1.5 py-0.5 rounded text-[13px] md:text-sm font-mono break-words whitespace-pre-wrap" {...props}>
                  {children}
                </code>
              )
            }

            return (
              <CodeBlock language={match?.[1] ?? 'text'} value={content} />
            )
          },
          a: ({ node, ...props }) => (
            <a
              className="font-medium underline underline-offset-2 decoration-primary/40 text-primary hover:text-primary/80 hover:decoration-primary"
              {...props}
            />
          )
        }}
      >
        {safe}
      </ReactMarkdown>
    )
  }, [renderChildrenWithCitations])

  return (
    <div
      className={cn(
        'group flex w-full gap-2 py-3',
        isUser ? 'justify-end' : 'justify-start'
      )}
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
            "relative px-5 pt-3.5 pb-3.5",
            hasActionBar && "max-md:pb-12",
            isUser
              ? "message-user"
              : "message-assistant"
          )}
          >
            <div className={cn(
              "max-w-none break-words leading-7 text-pretty",
              "text-[15px] md:text-base" // Slightly larger font
            )}>
              {contentBlocks.length > 0
                ? contentBlocks.map((block, idx) => {
                  const keyBase = `${message.id}-${block.kind}-${idx}`

                  if (block.kind === 'markdown') {
                    return (
                      <React.Fragment key={keyBase}>
                        {renderMarkdownBlock(block.content, `${message.id}-md-${idx}`)}
                      </React.Fragment>
                    )
                  }

                  if (block.kind === 'research_plan') {
                    const copyAllQueries = async () => {
                      const payload = block.queries.map((q, i) => `${i + 1}. ${q}`).join('\n').trim()
                      if (!payload) return
                      try {
                        await navigator.clipboard.writeText(payload)
                        toast.success('Queries copied')
                      } catch {
                        toast.error('Copy failed')
                      }
                    }

                    return (
                      <StructuredDisclosure
                        key={keyBase}
                        variant="plan"
                        title={block.title}
                        icon={ListChecks}
                        meta={block.queries.length ? `${block.queries.length} queries` : undefined}
                        contentClassName="text-sm"
                      >
                        {block.reasoning ? (
                          <div className="text-muted-foreground">
                            {renderMarkdownBlock(block.reasoning, `${message.id}-plan-${idx}-reasoning`)}
                          </div>
                        ) : null}

                        {block.queries.length > 0 ? (
                          <div className="mt-3">
                            <div className="flex items-center justify-between gap-2">
                              <p className="text-[11px] font-semibold uppercase text-muted-foreground">
                                Queries
                              </p>
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                onClick={copyAllQueries}
                              >
                                Copy queries
                              </Button>
                            </div>
                            <ol className="mt-2 ml-5 list-decimal space-y-1 text-sm">
                              {block.queries.map((q, i) => (
                                <li key={`${keyBase}-q-${i}`} className="leading-6 text-foreground">
                                  {q}
                                </li>
                              ))}
                            </ol>
                          </div>
                        ) : null}
                      </StructuredDisclosure>
                    )
                  }

                  if (block.kind === 'disclosure') {
                    const variantIcon = block.variant === 'plan' ? ListChecks : Brain
                    const meta = (() => {
                      const lines = block.content.split('\n').filter(Boolean).length
                      return lines >= 3 ? `${lines} lines` : undefined
                    })()

                    return (
                      <StructuredDisclosure
                        key={keyBase}
                        variant={block.variant}
                        title={block.title}
                        icon={variantIcon}
                        meta={meta}
                        contentClassName={block.variant === 'reasoning' ? 'text-sm text-muted-foreground' : 'text-sm'}
                      >
                        {renderMarkdownBlock(block.content, `${message.id}-${block.variant}-${idx}`)}
                      </StructuredDisclosure>
                    )
                  }

                  return null
                })
                : null}

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
                          className="w-full h-auto max-h-40 object-cover bg-white blur-sm transition duration-300"
                          onLoad={(e) => e.currentTarget.classList.remove('blur-sm')}
                        />
                      ) : (
                        <div className="p-3 text-xs font-medium text-muted-foreground">
                          {att.name || 'Image attachment'}
                        </div>
                      )}
                      <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground truncate border-t border-border/50">
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
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground mt-2 animate-pulse">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Processing content...</span>
                </div>
              )}
            </div>

            {/* Actions: Copy, Speak & Edit */}
            {hasActionBar ? (
              <div
                role="toolbar"
                aria-label="Message actions"
                className={cn(
                  "absolute flex items-center gap-0.5 rounded-lg border border-border/40 bg-card/95 backdrop-blur-sm shadow-sm p-0.5",
                  "right-2 bottom-2 md:right-0 md:-bottom-5",
                  "opacity-100 md:opacity-0",
                  "md:group-hover:opacity-100 md:group-focus-within:opacity-100",
                  "transition-all duration-150",
                )}
              >
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50"
                  onClick={handleCopy}
                  aria-label="Copy message"
                  title="Copy"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <ClipboardCopy className="h-3.5 w-3.5 text-sky-500 dark:text-sky-400" />}
                </Button>

                {!isUser ? (
                  <>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className={cn(
                        "h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50",
                        isPlaying && "text-primary bg-primary/10"
                      )}
                      onClick={handleSpeak}
                      disabled={isTTSLoading}
                      aria-label={isPlaying ? "Stop audio" : "Read aloud"}
                      title={isPlaying ? "Stop" : "Listen"}
                    >
                      {isTTSLoading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : isPlaying ? (
                        <Square className="h-3 w-3" />
                      ) : (
                        <Volume2 className="h-3.5 w-3.5 text-violet-500 dark:text-violet-400" />
                      )}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50"
                      onClick={handleSaveToLibrary}
                      aria-label={saved ? "Saved to library" : "Save to library"}
                      title={saved ? "Saved" : "Save"}
                    >
                      {saved ? <Check className="h-3.5 w-3.5 text-green-500" /> : <BookmarkPlus className="h-3.5 w-3.5 text-amber-500 dark:text-amber-400" />}
                    </Button>
                  </>
                ) : null}

                {isUser && onEdit ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50"
                    onClick={() => setIsEditing(true)}
                    aria-label="Edit message"
                    title="Edit"
                  >
                    <PenLine className="h-3.5 w-3.5 text-emerald-500 dark:text-emerald-400" />
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}

function StructuredDisclosure({
  variant,
  title,
  meta,
  icon: Icon,
  contentClassName,
  children,
}: {
  variant: 'plan' | 'reasoning'
  title: string
  meta?: string
  icon: React.ComponentType<{ className?: string }>
  contentClassName?: string
  children: React.ReactNode
}) {
  const isPlan = variant === 'plan'

  const iconColor = isPlan
    ? 'text-sky-500 dark:text-sky-400'
    : 'text-violet-500 dark:text-violet-400'

  return (
    <details
      className={cn(
        'weaver-disclosure my-3 rounded-xl border overflow-hidden',
        isPlan
          ? 'border-sky-500/10 bg-sky-500/[0.02]'
          : 'border-violet-500/10 bg-violet-500/[0.02]'
      )}
    >
      <summary
        className={cn(
          "flex items-center justify-between gap-3 px-4 py-2.5 cursor-pointer select-none",
          "hover:bg-accent/30 transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        )}
        aria-label={title}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={cn(
            "flex items-center justify-center size-6 rounded-md",
            isPlan
              ? "bg-sky-500/10"
              : "bg-violet-500/10"
          )}>
            <Icon className={cn("h-3.5 w-3.5", iconColor)} />
          </span>
          <span className="text-xs font-semibold text-foreground truncate">
            {title}
          </span>
          {meta ? (
            <span className="hidden sm:inline-flex text-[11px] font-medium text-muted-foreground tabular-nums truncate">
              {meta}
            </span>
          ) : null}
        </div>

        <ChevronDown className="weaver-disclosure-chevron h-3.5 w-3.5 text-muted-foreground transition-transform duration-200" />
      </summary>

      <div className={cn("px-4 pb-3 pt-1 border-t border-border/20", contentClassName)}>
        {children}
      </div>
    </details>
  )
}

export const MessageItem = memo(MessageItemBase)
