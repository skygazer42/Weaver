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
    <div className="relative w-full my-4 rounded-xl overflow-hidden border border-border/60 bg-card/40 backdrop-blur-sm shadow-sm group transition-all hover:shadow-md">
      {/* Header - Glassy MacOS Style */}
      <div className="flex items-center justify-between px-4 py-2 bg-muted/20 border-b border-border/50">
        <div className="flex items-center gap-3">
            <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/40 border border-red-500/20" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/40 border border-yellow-500/20" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-500/40 border border-green-500/20" />
            </div>
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest opacity-70">
                {language || 'TEXT'}
            </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground transition-all"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {/* Code Content - Unified Background */}
      <div className="overflow-x-auto p-4 bg-transparent selection:bg-primary/10">
        <code className="text-[13px] font-mono leading-relaxed text-foreground/90 whitespace-pre-wrap break-all">
          {value}
        </code>
      </div>
    </div>
  )
}
