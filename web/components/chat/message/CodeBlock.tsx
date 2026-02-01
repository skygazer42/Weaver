'use client'

import React, { useState, useMemo, useCallback, memo } from 'react'
import { Check, Copy, ChevronDown, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Virtuoso } from 'react-virtuoso'
import { cn } from '@/lib/utils'

interface CodeBlockProps {
  language: string
  value: string
  defaultCollapsed?: boolean
}

// Threshold for enabling virtual scrolling
const VIRTUAL_SCROLL_THRESHOLD = 100

// Memoized line component for virtual scrolling
const CodeLine = memo(function CodeLine({
  line,
  lineNumber,
  language
}: {
  line: string
  lineNumber: number
  language: string
}) {
  return (
    <div className="flex font-mono text-sm leading-6">
      <span className="select-none text-white/30 w-12 pr-4 text-right shrink-0">
        {lineNumber}
      </span>
      <SyntaxHighlighter
        language={language?.toLowerCase() || 'text'}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: 0,
          background: 'transparent',
          fontSize: 'inherit',
          lineHeight: 'inherit',
          display: 'inline',
        }}
        PreTag="span"
        CodeTag="span"
      >
        {line || ' '}
      </SyntaxHighlighter>
    </div>
  )
})

export function CodeBlock({ language, value, defaultCollapsed = false }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)

  // Memoize line splitting
  const lines = useMemo(() => value.split('\n'), [value])
  const useVirtualization = lines.length > VIRTUAL_SCROLL_THRESHOLD

  // Memoized item renderer for Virtuoso
  const itemContent = useCallback((index: number) => (
    <CodeLine
      key={index}
      line={lines[index]}
      lineNumber={index + 1}
      language={language}
    />
  ), [lines, language])

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(value)
    setCopied(true)
    toast.success('Code copied')
    setTimeout(() => setCopied(false), 2000)
  }

  const toggleCollapse = () => {
    setIsCollapsed(!isCollapsed)
  }

  return (
    <div className="relative w-full my-4 rounded-xl overflow-hidden border border-border/40 bg-[#282c34] shadow-sm group transition-all hover:shadow-md">
      {/* Header - Glassy MacOS Style */}
      <div
        className="flex items-center justify-between px-4 py-2.5 bg-white/5 border-b border-white/10 backdrop-blur-sm select-none cursor-pointer hover:bg-white/10 transition-colors"
        onClick={toggleCollapse}
      >
        <div className="flex items-center gap-3">
            <div className="flex gap-1.5 opacity-80 group-hover:opacity-100 transition-opacity">
                <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
            </div>
            <span className="text-xs font-medium text-white/50 font-mono lowercase flex items-center gap-2">
                {language || 'text'}
                {isCollapsed && <span className="text-xs text-white/30 italic">- collapsed</span>}
            </span>
        </div>
        <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-white/50 hover:text-white hover:bg-white/10 transition-all"
              onClick={handleCopy}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
            <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-white/50 hover:text-white hover:bg-white/10 transition-all"
            >
                {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
        </div>
      </div>

      {/* Code Content */}
      {!isCollapsed && (
          <div className="overflow-x-auto animate-in slide-in-from-top-2 duration-200">
            {useVirtualization ? (
              // Virtual scrolling for large code blocks (>100 lines)
              <div className="px-4 py-4">
                <Virtuoso
                  style={{ height: '400px' }}
                  totalCount={lines.length}
                  itemContent={itemContent}
                  className="scrollbar-thin scrollbar-thumb-white/20"
                />
              </div>
            ) : (
              // Standard rendering for smaller code blocks
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
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'normal',
                  overflowWrap: 'anywhere',
                }}
                codeTagProps={{
                  style: {
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'normal',
                    overflowWrap: 'anywhere'
                  }
                }}
                showLineNumbers={false}
                wrapLongLines={false}
                PreTag="div"
              >
                {value}
              </SyntaxHighlighter>
            )}
          </div>
      )}
    </div>
  )
}
