'use client'

import React, { useState } from 'react'
import { Check, Copy, Terminal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
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
    <div className="relative w-full my-4 rounded-xl overflow-hidden border border-border bg-background shadow-sm group">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-muted/40 border-b border-border/50">
        <div className="flex items-center gap-2">
            <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/20 border border-red-500/50" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/20 border border-yellow-500/50" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-500/20 border border-green-500/50" />
            </div>
            <span className="ml-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider opacity-70">
                {language || 'TEXT'}
            </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground hover:bg-background/80 transition-all opacity-0 group-hover:opacity-100"
          onClick={handleCopy}
          title="Copy code"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {/* Code Content */}
      <div className="overflow-x-auto p-4 bg-zinc-50 dark:bg-[#09090b] selection:bg-primary/20">
        <code className="text-[13px] font-mono leading-relaxed text-zinc-800 dark:text-zinc-300 whitespace-pre-wrap break-all">
          {value}
        </code>
      </div>
    </div>
  )
}
