'use client'

import React, { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

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
    <div className="relative w-full my-4 rounded-lg overflow-hidden border border-border/50 shadow-sm">
      <div className="flex items-center justify-between px-4 py-2 bg-muted/80 backdrop-blur border-b border-border/50">
        <span className="text-xs font-medium text-muted-foreground uppercase">{language}</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground hover:text-foreground hover:bg-background/50"
          onClick={handleCopy}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </Button>
      </div>
      <div className="overflow-x-auto p-4 bg-muted/30">
        <code className="text-sm font-mono text-foreground whitespace-pre">
          {value}
        </code>
      </div>
    </div>
  )
}
