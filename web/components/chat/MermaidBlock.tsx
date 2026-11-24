'use client'

import React, { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { Loader2 } from 'lucide-react'

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'inherit',
})

interface MermaidBlockProps {
  code: string
}

export function MermaidBlock({ code }: MermaidBlockProps) {
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const id = useRef(`mermaid-${Math.random().toString(36).substr(2, 9)}`)

  useEffect(() => {
    const renderChart = async () => {
      setIsLoading(true)
      setError(null)
      try {
        // Mermaid needs the element to be in the DOM to render properly sometimes,
        // but render() returns an SVG string.
        const { svg } = await mermaid.render(id.current, code)
        setSvg(svg)
      } catch (err: any) {
        console.error('Mermaid render error:', err)
        setError('Failed to render chart')
      } finally {
        setIsLoading(false)
      }
    }

    renderChart()
  }, [code])

  if (error) {
    return (
      <div className="not-prose rounded-lg border border-destructive-border bg-destructive-surface p-4 text-sm text-destructive">
        <p className="font-semibold mb-1">Chart rendering failed</p>
        <pre className="whitespace-pre-wrap text-xs">{error}</pre>
        <pre className="mt-3 overflow-x-auto rounded-md border border-border/70 bg-card p-3 text-xs text-foreground">{code}</pre>
      </div>
    )
  }

  return (
    <div className="not-prose my-4 flex justify-center overflow-hidden rounded-lg border border-border/80 bg-card p-4 shadow-surface">
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Rendering chart...</span>
        </div>
      ) : (
        <div 
            className="flex w-full justify-center overflow-x-auto rounded bg-white p-3"
            dangerouslySetInnerHTML={{ __html: svg }} 
        />
      )}
    </div>
  )
}
