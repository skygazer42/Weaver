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
      <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-sm border border-destructive/20">
        <p className="font-semibold mb-1">Chart rendering failed</p>
        <pre className="text-xs opacity-70 whitespace-pre-wrap">{error}</pre>
        <pre className="mt-2 text-xs bg-black/5 p-2 rounded">{code}</pre>
      </div>
    )
  }

  return (
    <div className="my-4 overflow-hidden rounded-lg border bg-white dark:bg-zinc-950 p-4 flex justify-center">
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Rendering chart...</span>
        </div>
      ) : (
        <div 
            className="w-full overflow-x-auto flex justify-center bg-white dark:bg-zinc-950/50"
            dangerouslySetInnerHTML={{ __html: svg }} 
        />
      )}
    </div>
  )
}
