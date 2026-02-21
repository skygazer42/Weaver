'use client'

import React, { useEffect, useRef, useState, useMemo, useCallback, memo } from 'react'
import { Check, Copy, ChevronDown, ChevronRight, WrapText, Download, MoreHorizontal, ArrowUp, ArrowDown, Maximize2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { showSuccess } from '@/lib/toast-utils'
import dynamic from 'next/dynamic'
import { Virtuoso, type ScrollerProps, type VirtuosoHandle } from 'react-virtuoso'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

// Lazy-load SyntaxHighlighter to reduce initial bundle (~200KB savings)
const SyntaxHighlighter = dynamic(
  () => import('react-syntax-highlighter/dist/esm/prism').then(mod => mod.default || mod),
  { ssr: false }
)

// Static import for the theme (small JSON file, ok to keep static)
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface CodeBlockProps {
  language: string
  value: string
  defaultCollapsed?: boolean
}

// Threshold for enabling virtual scrolling
const VIRTUAL_SCROLL_THRESHOLD = 100

const CODEBLOCK_PREF_WRAP = 'weaver:codeblock:wrap'
const CODEBLOCK_PREF_LINE_NUMBERS = 'weaver:codeblock:line_numbers'

function readStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (raw === null) return fallback
    if (raw === '1' || raw === 'true') return true
    if (raw === '0' || raw === 'false') return false
    return fallback
  } catch {
    return fallback
  }
}

function writeStoredBoolean(key: string, value: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value ? '1' : '0')
  } catch {
    // Ignore; storage may be unavailable (privacy mode) and should not break UI.
  }
}

function extensionForLanguage(language: string): string {
  const lang = String(language || '').trim().toLowerCase()
  if (!lang || lang === 'text' || lang === 'plain') return 'txt'

  if (lang === 'ts' || lang === 'typescript') return 'ts'
  if (lang === 'tsx') return 'tsx'
  if (lang === 'js' || lang === 'javascript') return 'js'
  if (lang === 'jsx') return 'jsx'
  if (lang === 'py' || lang === 'python') return 'py'
  if (lang === 'sh' || lang === 'bash' || lang === 'shell') return 'sh'
  if (lang === 'json') return 'json'
  if (lang === 'yaml' || lang === 'yml') return 'yml'
  if (lang === 'md' || lang === 'markdown') return 'md'
  if (lang === 'html') return 'html'
  if (lang === 'css') return 'css'
  if (lang === 'sql') return 'sql'
  if (lang === 'go' || lang === 'golang') return 'go'
  if (lang === 'rs' || lang === 'rust') return 'rs'

  return 'txt'
}

function buildHighlightedParts(text: string, query: string) {
  const q = String(query || '')
  if (!q) return [{ text, match: false }]

  const lowerText = text.toLowerCase()
  const lowerQuery = q.toLowerCase()

  const parts: Array<{ text: string; match: boolean }> = []
  let cursor = 0
  while (cursor < text.length) {
    const idx = lowerText.indexOf(lowerQuery, cursor)
    if (idx === -1) break

    if (idx > cursor) {
      parts.push({ text: text.slice(cursor, idx), match: false })
    }

    parts.push({ text: text.slice(idx, idx + q.length), match: true })
    cursor = idx + q.length
  }

  if (cursor < text.length) {
    parts.push({ text: text.slice(cursor), match: false })
  }

  return parts.length > 0 ? parts : [{ text, match: false }]
}

// Memoized line component for virtual scrolling
const CodeLine = memo(function CodeLine({
  line,
  lineNumber,
  wrap,
  showLineNumbers,
  isMatch,
  isActiveMatch,
  highlightQuery,
}: {
  line: string
  lineNumber: number
  wrap: boolean
  showLineNumbers: boolean
  isMatch: boolean
  isActiveMatch: boolean
  highlightQuery?: string
}) {
  const query = String(highlightQuery || '').trim()
  const text = line || ' '
  const parts = query ? buildHighlightedParts(text, query) : null

  return (
    <div
      className={cn(
        "flex font-mono text-sm leading-6 rounded-sm px-2",
        isMatch && "bg-white/5",
        isActiveMatch && "bg-primary/20 ring-1 ring-primary/30"
      )}
      data-code-line={lineNumber}
    >
      {showLineNumbers ? (
        <span className="select-none text-white/30 w-12 pr-4 text-right shrink-0 tabular-nums">
          {lineNumber}
        </span>
      ) : null}
      <code
        className={cn(
          'flex-1 min-w-0 text-white/90',
          wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre',
        )}
      >
        {parts
          ? parts.map((p, idx) =>
            p.match ? (
              <mark
                // Mark has better semantics for "find highlight"
                key={idx}
                className="rounded-sm bg-primary/35 text-white/95 px-0.5"
              >
                {p.text}
              </mark>
            ) : (
              <span key={idx}>{p.text}</span>
            )
          )
          : text}
      </code>
    </div>
  )
})

export function CodeBlock({ language, value, defaultCollapsed = false }: CodeBlockProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const codeContainerRef = useRef<HTMLDivElement | null>(null)

  const [copied, setCopied] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)
  const [isFullscreenOpen, setIsFullscreenOpen] = useState(false)
  const [wrapLines, setWrapLines] = useState(() => readStoredBoolean(CODEBLOCK_PREF_WRAP, false))
  const [showLineNumbers, setShowLineNumbers] = useState(() => readStoredBoolean(CODEBLOCK_PREF_LINE_NUMBERS, false))
  const [findQuery, setFindQuery] = useState('')
  const [activeMatchCursor, setActiveMatchCursor] = useState(0)

  // Memoize line splitting
  const lines = useMemo(() => value.split('\n'), [value])
  const useVirtualization = lines.length > VIRTUAL_SCROLL_THRESHOLD
  const normalizedFindQuery = findQuery.trim()

  const matchLineIndexes = useMemo(() => {
    if (!normalizedFindQuery) return []
    const q = normalizedFindQuery.toLowerCase()
    const out: number[] = []
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (typeof line === 'string' && line.toLowerCase().includes(q)) {
        out.push(i)
      }
    }
    return out
  }, [lines, normalizedFindQuery])

  const matchLineSet = useMemo(() => new Set(matchLineIndexes), [matchLineIndexes])

  const matchCount = matchLineIndexes.length
  const safeActiveCursor = matchCount > 0 ? Math.min(activeMatchCursor, matchCount - 1) : 0
  const activeMatchLineIndex = matchCount > 0 ? matchLineIndexes[safeActiveCursor] ?? null : null

  // Memoized item renderer for Virtuoso
  const itemContent = useCallback((index: number) => (
    <CodeLine
      key={index}
      line={lines[index] ?? ''}
      lineNumber={index + 1}
      wrap={wrapLines}
      showLineNumbers={showLineNumbers}
      isMatch={matchLineSet.has(index)}
      isActiveMatch={activeMatchLineIndex === index}
      highlightQuery={normalizedFindQuery}
    />
  ), [lines, wrapLines, showLineNumbers, matchLineSet, activeMatchLineIndex, normalizedFindQuery])

  useEffect(() => {
    writeStoredBoolean(CODEBLOCK_PREF_WRAP, wrapLines)
  }, [wrapLines])

  useEffect(() => {
    writeStoredBoolean(CODEBLOCK_PREF_LINE_NUMBERS, showLineNumbers)
  }, [showLineNumbers])

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(value)
    setCopied(true)
    showSuccess('Code copied', 'code-copy')
    setTimeout(() => setCopied(false), 2000)
  }

  const handleCopyFenced = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const normalizedLang = String(language || '').trim().toLowerCase()
    const lang = normalizedLang && normalizedLang !== 'text' ? normalizedLang : ''
    const content = String(value || '').replace(/\n$/, '')
    const fenced = lang ? `\`\`\`${lang}\n${content}\n\`\`\`` : `\`\`\`\n${content}\n\`\`\``
    try {
      await navigator.clipboard.writeText(fenced)
      showSuccess('Copied as fenced block', 'code-copy-fenced')
    } catch {
      // Keep silent; clipboard may be blocked in some contexts.
    }
  }

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    const ext = extensionForLanguage(language)
    const filename = `snippet.${ext}`
    const blob = new Blob([value], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)

    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()

    URL.revokeObjectURL(url)
    showSuccess('Download started', 'code-download')
  }

  const toggleCollapse = () => {
    setIsCollapsed(!isCollapsed)
  }

  const toggleWrap = (e: React.MouseEvent) => {
    e.stopPropagation()
    setWrapLines(v => !v)
  }

  const openFullscreen = (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsFullscreenOpen(true)
  }

  const handleFindChange = (value: string) => {
    setFindQuery(value)
    setActiveMatchCursor(0)
  }

  const scrollToLineIndex = useCallback((lineIndex: number) => {
    if (lineIndex < 0) return
    if (useVirtualization) {
      virtuosoRef.current?.scrollToIndex({ index: lineIndex, align: 'center', behavior: 'smooth' })
      return
    }

    const el = codeContainerRef.current?.querySelector(
      `[data-code-line="${lineIndex + 1}"]`
    ) as HTMLElement | null
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [useVirtualization])

  const goToMatchCursor = useCallback((cursor: number) => {
    if (matchCount === 0) return
    const nextCursor = ((cursor % matchCount) + matchCount) % matchCount
    setActiveMatchCursor(nextCursor)
    const lineIndex = matchLineIndexes[nextCursor]
    if (typeof lineIndex === 'number') {
      scrollToLineIndex(lineIndex)
    }
  }, [matchCount, matchLineIndexes, scrollToLineIndex])

  const goToNextMatch = useCallback(() => {
    goToMatchCursor(safeActiveCursor + 1)
  }, [goToMatchCursor, safeActiveCursor])

  const goToPrevMatch = useCallback(() => {
    goToMatchCursor(safeActiveCursor - 1)
  }, [goToMatchCursor, safeActiveCursor])

  const virtualizationComponents = useMemo(() => {
    const Scroller = React.forwardRef<HTMLDivElement, ScrollerProps>(function ScrollerBase(
      { style, children, ...props },
      ref
    ) {
      return (
        <div
          ref={ref}
          {...props}
          style={{
            ...style,
            overflowX: wrapLines ? 'hidden' : 'auto',
          }}
          className="scrollbar-thin scrollbar-thumb-white/20"
        >
          {children}
        </div>
      )
    })

    return { Scroller }
  }, [wrapLines])

  const codeWrapStyle = useMemo(() => {
    return {
      whiteSpace: wrapLines ? 'pre-wrap' : 'pre',
      wordBreak: wrapLines ? 'break-word' : 'normal',
      overflowWrap: wrapLines ? 'anywhere' : 'normal',
    } as const
  }, [wrapLines])

  const codeViewportHeight = isFullscreenOpen ? '70vh' : '400px'
  const codeViewportClassName = cn(
    wrapLines ? 'overflow-x-hidden' : 'overflow-x-auto',
    isFullscreenOpen ? 'max-h-[70vh]' : 'max-h-[400px]',
  )

  const codeBody = useMemo(() => {
    if (useVirtualization) {
      return (
        <div className={codeViewportClassName}>
          <div className="px-4 py-4">
            <Virtuoso
              ref={virtuosoRef}
              style={{ height: codeViewportHeight }}
              totalCount={lines.length}
              itemContent={itemContent}
              components={virtualizationComponents}
            />
          </div>
        </div>
      )
    }

    if (normalizedFindQuery) {
      return (
        <div className={cn(codeViewportClassName, 'overflow-y-auto')}>
          <div className="px-4 py-4 space-y-0.5">
            {lines.map((line, idx) => (
              <CodeLine
                key={idx}
                line={line ?? ''}
                lineNumber={idx + 1}
                wrap={wrapLines}
                showLineNumbers={showLineNumbers}
                isMatch={matchLineSet.has(idx)}
                isActiveMatch={activeMatchLineIndex === idx}
                highlightQuery={normalizedFindQuery}
              />
            ))}
          </div>
        </div>
      )
    }

    return (
      <div className={cn(codeViewportClassName, 'overflow-y-auto')}>
        <div ref={codeContainerRef}>
          <SyntaxHighlighter
            language={language?.toLowerCase() || 'text'}
            style={oneDark}
            customStyle={{
              margin: 0,
              padding: '1.5rem',
              background: 'transparent',
              fontSize: '14px',
              lineHeight: '1.6',
              fontFamily: 'var(--font-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              whiteSpace: codeWrapStyle.whiteSpace,
              wordBreak: codeWrapStyle.wordBreak,
              overflowWrap: codeWrapStyle.overflowWrap,
            }}
            codeTagProps={{
              style: {
                whiteSpace: codeWrapStyle.whiteSpace,
                wordBreak: codeWrapStyle.wordBreak,
                overflowWrap: codeWrapStyle.overflowWrap,
              }
            }}
            showLineNumbers={showLineNumbers}
            wrapLongLines={wrapLines}
            lineProps={(lineNumber: number) => {
              const idx = lineNumber - 1
              const isMatch = matchLineSet.has(idx)
              const isActive = activeMatchLineIndex === idx
              return {
                'data-code-line': lineNumber,
                className: cn(
                  'block rounded-sm px-2',
                  isMatch && 'bg-white/5',
                  isActive && 'bg-primary/20 ring-1 ring-primary/30'
                )
              }
            }}
            PreTag="div"
          >
            {value}
          </SyntaxHighlighter>
        </div>
      </div>
    )
  }, [
    useVirtualization,
    codeViewportClassName,
    lines,
    itemContent,
    virtualizationComponents,
    codeViewportHeight,
    language,
    codeWrapStyle.whiteSpace,
    codeWrapStyle.wordBreak,
    codeWrapStyle.overflowWrap,
    showLineNumbers,
    wrapLines,
    normalizedFindQuery,
    matchLineSet,
    activeMatchLineIndex,
    value,
  ])

  return (
    <div className="relative w-full my-4 rounded-xl overflow-hidden border border-border/40 bg-[#282c34] shadow-sm group transition-shadow duration-200 hover:shadow-md">
      <Dialog open={isFullscreenOpen} onOpenChange={setIsFullscreenOpen}>
        <DialogContent
          className="max-w-5xl w-[calc(100vw-2rem)] p-0 overflow-hidden max-h-[calc(100dvh-2rem)]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex flex-col">
            <DialogHeader className="px-5 py-4 border-b border-border/60 bg-card">
              <div className="flex items-start justify-between gap-4">
                <div className="flex flex-col gap-1">
                  <DialogTitle className="font-mono text-sm">
                    {language || 'text'}
                  </DialogTitle>
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {lines.length} lines
                    {matchCount > 0 ? ` · ${safeActiveCursor + 1}/${matchCount} matches` : null}
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleCopyFenced}
                    aria-label="Copy as fenced block"
                    title="Copy fenced"
                  >
                    Copy fenced
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleDownload}
                    aria-label="Download code"
                    title="Download"
                  >
                    Download
                  </Button>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Wrap</span>
                  <Switch
                    checked={wrapLines}
                    onCheckedChange={setWrapLines}
                    aria-label="Toggle line wrap"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Line numbers</span>
                  <Switch
                    checked={showLineNumbers}
                    onCheckedChange={setShowLineNumbers}
                    aria-label="Toggle line numbers"
                  />
                </div>

                <span className="mx-1 h-4 w-px bg-border/60" aria-hidden="true" />

                <div className="flex items-center gap-2 flex-1 min-w-[240px]">
                  <Input
                    value={findQuery}
                    onChange={(e) => handleFindChange(e.target.value)}
                    placeholder="Find in code..."
                    className="h-9"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        if (e.shiftKey) goToPrevMatch()
                        else goToNextMatch()
                      } else if (e.key === 'Escape') {
                        e.preventDefault()
                        handleFindChange('')
                      }
                    }}
                    aria-label="Find in code"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    className="h-9 w-9"
                    onClick={(e) => {
                      e.stopPropagation()
                      goToPrevMatch()
                    }}
                    disabled={matchCount === 0}
                    aria-label="Previous match"
                    title="Previous"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    className="h-9 w-9"
                    onClick={(e) => {
                      e.stopPropagation()
                      goToNextMatch()
                    }}
                    disabled={matchCount === 0}
                    aria-label="Next match"
                    title="Next"
                  >
                    <ArrowDown className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </DialogHeader>

            <div className="p-5 bg-background">
              <div className="rounded-xl overflow-hidden border border-border/60 bg-[#282c34]">
                {codeBody}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <div
        className="flex items-center justify-between px-4 py-2 bg-white/5 border-b border-white/10 select-none cursor-pointer hover:bg-white/10 transition-colors duration-200"
        onClick={toggleCollapse}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-white/70 font-mono flex items-center gap-2">
            {language || 'text'}
            {isCollapsed && <span className="text-xs text-white/40">collapsed</span>}
            {wrapLines && !isCollapsed && <span className="text-xs text-white/40">wrap</span>}
            {showLineNumbers && !isCollapsed && <span className="text-xs text-white/40">lines</span>}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={handleCopy}
            aria-label="Copy code"
            title="Copy code"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={handleDownload}
            aria-label="Download code"
            title="Download"
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={openFullscreen}
            aria-label="Open code fullscreen"
            title="Fullscreen"
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
                onClick={(e) => e.stopPropagation()}
                aria-label="Code block actions"
                title="Actions"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              align="end"
              className="w-80 p-3"
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-muted-foreground uppercase">Code tools</div>
                  <div className="text-[10px] text-muted-foreground tabular-nums">
                    {lines.length} lines
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={handleCopyFenced}
                  >
                    Copy fenced
                  </Button>
                  <div className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2">
                    <span className="text-sm font-medium">Line numbers</span>
                    <Switch
                      checked={showLineNumbers}
                      onCheckedChange={setShowLineNumbers}
                      aria-label="Toggle line numbers"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-semibold text-muted-foreground uppercase">Find</div>
                    <div className="text-[10px] text-muted-foreground tabular-nums">
                      {matchCount > 0 ? `${safeActiveCursor + 1}/${matchCount}` : '0'}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Input
                      value={findQuery}
                      onChange={(e) => handleFindChange(e.target.value)}
                      placeholder="Find in code..."
                      className="h-9"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          if (e.shiftKey) goToPrevMatch()
                          else goToNextMatch()
                        } else if (e.key === 'Escape') {
                          e.preventDefault()
                          handleFindChange('')
                        }
                      }}
                      aria-label="Find in code"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      className="h-9 w-9"
                      onClick={(e) => {
                        e.stopPropagation()
                        goToPrevMatch()
                      }}
                      disabled={matchCount === 0}
                      aria-label="Previous match"
                      title="Previous"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      className="h-9 w-9"
                      onClick={(e) => {
                        e.stopPropagation()
                        goToNextMatch()
                      }}
                      disabled={matchCount === 0}
                      aria-label="Next match"
                      title="Next"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </PopoverContent>
          </Popover>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className={cn(
              "h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200",
              wrapLines && "text-white bg-white/10"
            )}
            onClick={toggleWrap}
            aria-label={wrapLines ? "Disable line wrap" : "Enable line wrap"}
            title={wrapLines ? "Disable wrap" : "Wrap lines"}
          >
            <WrapText className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={(e) => {
              e.stopPropagation()
              toggleCollapse()
            }}
            aria-label={isCollapsed ? "Expand code block" : "Collapse code block"}
            title={isCollapsed ? "Expand" : "Collapse"}
          >
            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Code Content */}
      {!isCollapsed && !isFullscreenOpen ? (
        codeBody
      ) : null}
    </div>
  )
}
