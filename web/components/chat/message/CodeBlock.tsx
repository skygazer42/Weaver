'use client'

import React, { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { cn } from '@/lib/utils'

interface CodeBlockProps {
  language: string
  value: string
}

export function CodeBlock({ language, value }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(value)
    setCopied(true)
    toast.success('Code copied')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative w-full my-4 rounded-xl overflow-hidden border border-border/40 bg-[#282c34] shadow-sm group transition-all hover:shadow-md">
      {/* Header - Glassy MacOS Style */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-white/5 border-b border-white/10 backdrop-blur-sm select-none">
        <div className="flex items-center gap-3">
            <div className="flex gap-1.5 opacity-80 group-hover:opacity-100 transition-opacity">
                <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
            </div>
            <span className="text-xs font-medium text-white/50 font-mono lowercase">
                {language || 'text'}
            </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-white/50 hover:text-white hover:bg-white/10 transition-all"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {/* Code Content */}
      <div className="overflow-x-auto">
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
            }}
            showLineNumbers={true}
            wrapLongLines={false} // Enable horizontal scrolling
            PreTag="div"
         >
            {value}
         </SyntaxHighlighter>
      </div>
    </div>
  )
}
