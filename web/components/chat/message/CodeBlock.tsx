'use client'

import React, { useState } from 'react'
import { Check, Copy, ChevronDown, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface CodeBlockProps {
  language: string
  value: string
  defaultCollapsed?: boolean
  showHeader?: boolean
}

export function CodeBlock({ language, value, defaultCollapsed = false, showHeader = true }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)

  const handleCopy = () => {
    navigator.clipboard.writeText(value)
    setCopied(true)
    toast.success('Code copied')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="not-prose relative my-4 w-full overflow-hidden rounded-lg border border-[#30363d] bg-[#0d1117] text-[#e6edf3] shadow-surface">
      {showHeader && <div className="flex items-center justify-between gap-3 border-b border-[#30363d] bg-[#161b22] px-3 py-1.5">
        <button
          type="button"
          onClick={() => setIsCollapsed(!isCollapsed)}
          aria-label={isCollapsed ? 'Expand code' : 'Collapse code'}
          aria-expanded={!isCollapsed}
          className="flex min-w-0 items-center gap-2 rounded px-1 py-1 text-xs text-[#9da7b3] transition-colors hover:text-[#e6edf3] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {isCollapsed ? <ChevronRight className="h-3.5 w-3.5 shrink-0" /> : <ChevronDown className="h-3.5 w-3.5 shrink-0" />}
          <span className="truncate rounded border border-[#30363d] bg-[#0d1117] px-1.5 py-0.5 font-mono text-[11px] font-medium lowercase text-[#e6edf3]">{language || 'text'}</span>
          <span className="whitespace-nowrap tabular-nums">{value.split('\n').length} lines</span>
        </button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={copied ? 'Code copied' : 'Copy code'}
          className="h-7 gap-1.5 px-2 text-xs text-[#9da7b3] hover:bg-white/10 hover:text-[#e6edf3]"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>}

      {!isCollapsed && (
        <div className="overflow-x-auto">
          <SyntaxHighlighter
            language={language?.toLowerCase() || 'text'}
            style={oneDark}
            customStyle={{
              margin: 0,
              padding: '1rem',
              background: 'transparent',
              fontSize: '13px',
              lineHeight: '1.7',
              fontFamily: 'var(--font-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              whiteSpace: 'pre-wrap',
              wordBreak: 'normal',
              overflowWrap: 'anywhere',
            }}
            codeTagProps={{
              style: {
                whiteSpace: 'pre-wrap',
                wordBreak: 'normal',
                overflowWrap: 'anywhere',
              },
            }}
            showLineNumbers={false}
            wrapLongLines={false}
            PreTag="div"
          >
            {value}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  )
}
